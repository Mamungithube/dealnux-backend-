from datetime import timedelta

from elasticsearch import logger
from redis import event
import stripe
from decimal import Decimal

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.http import HttpResponse

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny

from django.db.models import F
from django.db import transaction
from .models import Payment, SellerPayout, SubscriptionPlan, UserSubscription
from store.models import SellerProduct, Order, Coupon
from api_integration.models import ProductListing
from account.models import User
from . serializers import (
    SubscriptionPlanSerializer,
    
)

from django.utils import timezone
stripe.api_key = settings.STRIPE_SECRET_KEY
PLATFORM_FEE_PERCENT = Decimal('10')  

import json
# ============================================================================
# Helper function to calculate amounts based on product price, quantity, and coupon code.
# ================= ===========================================================

def _calculate_order_amounts(seller_product, quantity, coupon_code=''):
    """ডক অনুযায়ী: আইটেম প্রাইস + শিপিং + ৮% সার্ভিস ফি হিসেব করা"""
    unit_price = seller_product.price
    subtotal = unit_price * quantity
    discount = Decimal('0')

    # কুপন ডিসকাউন্ট
    if coupon_code:
        try:
            coupon = Coupon.objects.get(code=coupon_code.upper(), seller=seller_product.seller)
            if coupon.is_valid and subtotal >= coupon.min_order_amount:
                discount = (subtotal * (coupon.discount_value / 100)) if coupon.discount_type == 'PERCENTAGE' else min(coupon.discount_value, subtotal)
        except Coupon.DoesNotExist: pass

    item_total = subtotal - discount
    shipping = seller_product.shipping_cost if not seller_product.free_shipping else Decimal('0')
    
    # Dealnux সার্ভিস ফি (বায়ার প্রোটেকশন ফি)
    service_fee = (item_total + shipping) * Decimal('0.08') # ৮% ফি
    final_amount = item_total + shipping + service_fee

    return {
        'unit_price': unit_price,
        'item_total': item_total,
        'discount_amount': discount,
        'shipping_fee': shipping,
        'service_fee': service_fee,
        'final_amount': final_amount,
    }


# ============================================================================
# 1. Checkout — Create Embedded Checkout Session (returns client_secret)
# ============================================================================

# payment/views.py এর CreateCheckoutSessionView ক্লাসটি এভাবে আপডেট করুন

class CreateCheckoutSessionView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        items_data = request.data.get('items', [])
        shipping_address = request.data.get('shipping_address')

        if not items_data:
            return Response({'error': 'Items list is required.'}, status=400)
        if not shipping_address:
            return Response({'error': 'shipping_address is required.'}, status=400)

        total_item_price = Decimal('0')
        total_shipping_fee = Decimal('0')
        line_items = []
        validated_items = []

        # ১. সব আইটেম ভ্যালিডেশন এবং প্রাইস ক্যালকুলেশন
        for item in items_data:
            p_id = item.get('seller_product')
            qty = int(item.get('quantity', 1))
            c_code = item.get('coupon_code', '')

            try:
                product = SellerProduct.objects.get(id=p_id, status='APPROVED')
            except SellerProduct.DoesNotExist:
                return Response({'error': f'Product ID {p_id} not found or not approved.'}, status=404)

            # ডিসকাউন্ট ও ফি ক্যালকুলেশন (আমাদের হেল্পার ফাংশন দিয়ে)
            res = _calculate_order_amounts(product, qty, c_code)
            
            total_item_price += res['item_total']
            total_shipping_fee += res['shipping_fee']

            # স্ট্রাইপের জন্য লাইন আইটেম তৈরি
            line_items.append({
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': int(res['item_total'] / qty * 100), # পার ইউনিট প্রাইস
                    'product_data': {'name': product.title},
                },
                'quantity': qty,
            })
            
            validated_items.append({
                'id': p_id,
                'qty': qty,
                'c_code': c_code,
                'shipping': float(res['shipping_fee']),
                'item_total': float(res['item_total'])
            })

        # ২. ডক অনুযায়ী সার্ভিস ফি (৮%)
        service_fee = (total_item_price + total_shipping_fee) * Decimal('0.08')
        final_grand_total = total_item_price + total_shipping_fee + service_fee

        # ৩. মেইন পেমেন্ট রেকর্ড তৈরি (মাস্টার ট্রানজেকশন)
        payment = Payment.objects.create(
            buyer=request.user,
            payment_type='STORE',
            shipping_address=shipping_address,
            
            # এই ৩টি ফিল্ড ডাটাবেজে বাধ্যতামূলক, তাই ভ্যালু পাস করতে হবে
            unit_price=total_item_price,    # টোটাল আইটেম প্রাইস (কনস্ট্রেইন্ট ফিক্স করতে)
            total_amount=total_item_price, 
            quantity=len(items_data),       # মোট কত পদের প্রোডাক্ট
            
            # নতুন ব্রেকডাউন ফিল্ডগুলো
            item_total=total_item_price,
            shipping_fee=total_shipping_fee,
            service_fee=service_fee,
            final_amount=final_grand_total,
            currency='usd',
            status='PENDING'
        )

        try:
            # সার্ভিস ফি-কে আলাদা লাইন আইটেম হিসেবে যোগ করা
            line_items.append({
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': int(service_fee * 100),
                    'product_data': {'name': 'Dealnux Service Fee (Buyer Protection)'},
                },
                'quantity': 1,
            })

            # ৪. স্ট্রাইপ সেশন তৈরি
            session = stripe.checkout.Session.create(
                ui_mode='embedded',
                line_items=line_items,
                mode='payment',
                return_url=settings.STRIPE_RETURN_URL + '?session_id={CHECKOUT_SESSION_ID}',
                metadata={
                    'payment_id': payment.id,
                    'type': 'store_payment',
                    # মেটাডাটায় আইটেমগুলো কমা দিয়ে রাখছি যাতে ওয়েবহুক অর্ডার বানাতে পারে
                    'items_json': json.dumps(validated_items) 
                },
                customer_email=request.user.email,
            )

            payment.stripe_checkout_session_id = session.id
            payment.save()

            return Response({
                'client_secret': session.client_secret,
                'payment_id': payment.id,
                'breakdown': {
                    'subtotal': float(total_item_price),
                    'shipping': float(total_shipping_fee),
                    'service_fee': float(service_fee),
                    'grand_total': float(final_grand_total)
                }
            })
        except Exception as e:
            return Response({'error': str(e)}, status=500)

# ============================================================================
# 2. Session Status —> Frontend will call and confirm this after payment is complete.
# ============================================================================

class CheckoutSessionStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        payment_id = request.query_params.get(
            'payment_id')  # Instead of session_id

        if not payment_id:
            return Response({'error': 'payment_id is required.'}, status=400)

        try:
            payment = Payment.objects.get(id=payment_id, buyer=request.user)
        except Payment.DoesNotExist:
            return Response({'error': 'Payment not found.'}, status=404)

        return Response({
            'payment_status': payment.status,        # PAID / PENDING / FAILED
            'payment_id':     payment.id,
            'order_id':       payment.order.id if payment.order else None,
        })

# ============================================================================
# 3. Stripe Webhook — Order will be created upon payment (no changes)
# ============================================================================

@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhookView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except (ValueError, stripe.error.SignatureVerificationError):
            return HttpResponse(status=400)


        if event['type'] == 'checkout.session.completed':
            self._handle_checkout_completed(event['data']['object'])


        elif event['type'] == 'invoice.paid':
            self._handle_recurring_subscription(event['data']['object'])

        elif event['type'] == 'checkout.session.expired':
            self._handle_checkout_expired(event['data']['object'])

        elif event['type'] == 'customer.subscription.deleted':
            subscription = event['data']['object']
            self._handle_subscription_cancellation(subscription)

        return HttpResponse(status=200)
    
    def _handle_subscription_cancellation(self, stripe_sub):
        """
        Updates the database when a subscription is cancelled in Stripe.
        """
        stripe_sub_id = stripe_sub.get('id')
        from payment.models import UserSubscription
        
        # Update status to CANCELLED and set expiration to now
        UserSubscription.objects.filter(
            stripe_subscription_id=stripe_sub_id
        ).update(status='CANCELLED')
        
        # Optional: Log the event
        print(f"Subscription {stripe_sub_id} has been cancelled.")

    def _handle_checkout_completed(self, session):
        metadata = session.get('metadata', {})
        p_type = metadata.get('type') # 'store_payment', 'ad_payment', 'subscription_payment'
        payment_id = metadata.get('payment_id')

        # --- ১. সাবস্ক্রিপশন হ্যান্ডেলিং (এটির জন্য আলাদা পেমেন্ট আইডি লাগে না) ---
        if p_type == 'subscription_payment':
            self._handle_subscription_success(session)
            return # সাবস্ক্রিপশন হলে এখানেই কাজ শেষ

        # --- ২. স্টোর এবং অ্যাড পেমেন্ট হ্যান্ডেলিং (এগুলোর জন্য পেমেন্ট আইডি লাগে) ---
        if payment_id:
            try:
                from .models import Payment
                payment = Payment.objects.get(id=payment_id)
                payment.status = 'PAID'
                payment.stripe_payment_intent_id = session.get('payment_intent', '')
                payment.save()

                if p_type == 'store_payment':
                    self._process_store_orders(payment, metadata)
                elif p_type == 'ad_payment':
                    ad = payment.ad
                    if ad:
                        ad.status = 'pending'
                        ad.save()
            except Payment.DoesNotExist:
                print(f"Error: Payment ID {payment_id} not found in database.")

    def _process_store_orders(self, payment, metadata):
        """মেটাডাটা থেকে লুপ চালিয়ে প্রতিটি আইটেমের জন্য অর্ডার তৈরি করবে"""
        items_json = metadata.get('items_json', '[]')
        items = json.loads(items_json)

        for item_data in items:
            try:
                seller_product = SellerProduct.objects.get(id=item_data['id'])
                
                # ১. অর্ডার তৈরি (আপনার আগের অর্ডারের সব ফিল্ডসহ)
                order = Order.objects.create(
                    buyer=payment.buyer,
                    seller=seller_product.seller,
                    seller_product=seller_product,
                    listing=seller_product.linked_listing,
                    quantity=item_data['qty'],
                    unit_price=seller_product.price,
                    item_total=Decimal(str(item_data['item_total'])),
                    shipping_fee=Decimal(str(item_data['shipping'])),
                    # সার্ভিস ফি এই অর্ডারের অংশ হিসেবে বন্টন করা হলো
                    service_fee=(Decimal(str(item_data['item_total'])) + Decimal(str(item_data['shipping']))) * Decimal('0.08'),
                    total_price=payment.final_amount, # টোটালটা পেমেন্ট রেকর্ড থেকে আসবে
                    currency=payment.currency,
                    shipping_address=payment.shipping_address,
                    status='CONFIRMED',
                )

                # ২. স্টক কমানো
                seller_product.quantity -= item_data['qty']
                seller_product.save()

                # ৩. সেলার ওয়ালেট আপডেট (পেন্ডিং ব্যালেন্স যোগ)
                seller = seller_product.seller
                amount_for_seller = Decimal(str(item_data['item_total'])) + Decimal(str(item_data['shipping']))
                seller.pending_balance += amount_for_seller
                seller.total_orders += 1
                seller.save()

            except Exception as e:
                logger.error(f"Error processing item in webhook: {str(e)}")

    def _handle_subscription_success(self, session):
        """Activates the paid subscription plan for the user in the database."""
        metadata = session.get('metadata', {})
        user_id = metadata.get('user_id')
        plan_id = metadata.get('plan_id')
        stripe_sub_id = session.get('subscription')

        if not user_id or not plan_id:
            return

        try:
            from account.models import User
            from payment.models import SubscriptionPlan, UserSubscription
            from django.utils import timezone
            from datetime import timedelta

            user = User.objects.get(id=user_id)
            plan = SubscriptionPlan.objects.get(id=plan_id)

            # Define duration based on plan type
            days = 365 if 'YEARLY' in plan.plan_type else 30
            now = timezone.now()
            
            # Update or create the subscription record
            UserSubscription.objects.update_or_create(
                user=user,
                defaults={
                    'plan': plan,
                    'status': 'ACTIVE',
                    'stripe_subscription_id': stripe_sub_id,
                    'started_at': now,
                    'expires_at': now + timedelta(days=days),
                    'trial_ends_at': now # ✅ পেইড মেম্বারদের জন্য বর্তমান সময় দিয়ে দিন
                }
            )
            print(f"✅ Payment success! Subscription activated for: {user.email}")
            
        except Exception as e:
            print(f"❌ Error in _handle_subscription_success: {str(e)}")

    def _handle_recurring_subscription(self, invoice):
        """সাবস্ক্রিপশন রিনিউ হলে মেয়াদ বাড়িয়ে দিবে"""
        stripe_sub_id = invoice.get('subscription')
        try:
            sub = UserSubscription.objects.get(stripe_subscription_id=stripe_sub_id)
            days = 365 if 'YEARLY' in sub.plan.plan_type else 30
            sub.expires_at = timezone.now() + timedelta(days=days)
            sub.save()
        except UserSubscription.DoesNotExist: pass

    def _handle_checkout_expired(self, session):
        payment_id = session.get('metadata', {}).get('payment_id')
        if payment_id:
            Payment.objects.filter(id=payment_id, status='PENDING').update(status='CANCELLED')


# ============================================================================
# 4. Stripe Connect — Create a Seller's Stripe account (no changes)
# ============================================================================

# payment/views.py

class SellerStripeConnectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            seller = request.user.seller_profile
        except Exception:
            return Response({"success": False, "message": "You are not an approved seller."}, status=403)

        # ১. যদি সেলারের আইডি না থাকে, নতুন এক্সপ্রেস একাউন্ট তৈরি করা
        if not seller.stripe_account_id:
            account = stripe.Account.create(
                type='express',
                email=request.user.email,
                capabilities={'transfers': {'requested': True}},
                metadata={'seller_id': seller.id}
            )
            seller.stripe_account_id = account.id
            seller.save()
        
        # ২. অনবোর্ডিং লিঙ্ক জেনারেট করা
        account_link = stripe.AccountLink.create(
            account=seller.stripe_account_id,
            refresh_url=settings.STRIPE_CONNECT_REFRESH_URL,
            return_url=settings.STRIPE_CONNECT_RETURN_URL,
            type='account_onboarding',
        )

        return Response({
            "success": True,
            "code": 200,
            "message": "Onboarding link generated.",
            "data": {
                "onboarding_url": account_link.url,
                "stripe_account_id": seller.stripe_account_id
            }
        })


class RequestPayoutView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        seller = request.user.seller_profile
        amount = Decimal(request.data.get('amount', 0))

        # ভ্যালিডেশন
        if amount < Decimal('10.00'):
            return Response({"success": False, "message": "Minimum payout is $10.00"}, status=400)
        
        if amount > seller.available_balance:
            return Response({"success": False, "message": "Insufficient balance."}, status=400)

        try:
            # স্ট্রাইপ ড্যাশবোর্ড থেকে টাকা ব্যাংকে পাঠানোর জন্য পেমেন্ট ট্রিগার (Express account)
            # নোট: সাধারণত এক্সপ্রেস একাউন্টে স্ট্রাইপ অটোমেটিক পে-আউট করে, 
            # তবে আমরা এখানে ম্যানুয়ালি ট্রান্সফার রেকর্ড মেইনটেইন করছি।
            
            seller.available_balance -= amount
            seller.total_withdrawn += amount
            seller.save()

            # এখানে একটি PayoutRecord তৈরি করবেন (আপনার ড্যাশবোর্ডে হিস্ট্রি দেখানোর জন্য)
            return Response({
                "success": True, 
                "code": 200,
                "message": "Payout request processed successfully.",
                "data": {
                    "withdrawn_amount": float(amount),
                    "remaining_balance": float(seller.available_balance)
                }
            })
        except Exception as e:
            return Response({"success": False, "message": str(e)}, status=500)
        

class SellerStripeStatusView(APIView):
    """
    The seller's Stripe account status will be checked.
    GET /api/v1/store/seller/stripe-status/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            seller = request.user.seller_profile
        except AttributeError:
            return Response({"success": False, "message": "Seller profile not found."}, status=404)

        if not seller.stripe_account_id:
            return Response({
                "success": True,
                "data": {"connected": False, "verified": False}
            })

        try:
            account = stripe.Account.retrieve(seller.stripe_account_id)
            
            is_fully_verified = account.get('charges_enabled', False) and account.get('payouts_enabled', False)

            if is_fully_verified and not seller.stripe_onboarding_completed:
                seller.stripe_onboarding_completed = True
                seller.save(update_fields=['stripe_onboarding_completed'])

            return Response({
                "success": True,
                "code": 200,
                "data": {
                    "connected": True,
                    "verified": is_fully_verified,
                    "stripe_account_id": seller.stripe_account_id,
                    "details_submitted": account.get('details_submitted', False)
                }
            })
        except Exception as e:
            return Response({"success": False, "message": f"Stripe Error: {str(e)}"}, status=400)


# ============================================================================
# 5. Payment History
# ============================================================================

class PaymentHistoryView(APIView):
    """
    Buyer own payment history
    GET /api/v1/store/payments/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        payments = Payment.objects.filter(buyer=request.user).select_related(
            'seller_product', 'order'
        )
        data = []
        for p in payments:
            data.append({
                'id':              p.id,
                'product':         p.seller_product.title if p.seller_product else None,
                'quantity':        p.quantity,
                'final_amount':    float(p.final_amount) if p.final_amount is not None else None,
                'discount_amount': float(p.discount_amount) if p.discount_amount is not None else None,
                'currency':        p.currency,
                'status':          p.status,
                'order_id':        p.order.id if p.order else None,
                'order_status':    p.order.status if p.order else None,
                'created_at':      p.created_at,
            })
        return Response(data)


class SellerPayoutHistoryView(APIView):
    """
    Seller payout history
    GET /api/v1/store/seller/payouts/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            seller = request.user.seller_profile
        except Exception:
            return Response({'error': 'Not a seller.'}, status=403)

        payouts = SellerPayout.objects.filter(
            seller=seller).select_related('payment', 'order')
        data = []
        for p in payouts:
            data.append({
                'id':                 p.id,
                'order_id':           p.order.id if p.order else None,
                'gross_amount':       float(p.gross_amount) if p.gross_amount is not None else None,
                'platform_fee':       float(p.platform_fee_amount) if p.platform_fee_amount is not None else None,
                'seller_amount':      float(p.seller_amount) if p.seller_amount is not None else None,
                'currency':           p.payment.currency,
                'status':             p.status,
                'stripe_transfer_id': p.stripe_transfer_id,
                'failure_reason':     p.failure_reason,
                'created_at':         p.created_at,
            })
        return Response(data)


class CheckSessionStatusView(APIView):
    """When the user returns to the return_url, Friendend will call it."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        session_id = request.query_params.get('session_id')

        if not session_id:
            return Response({"error": "session_id is required"}, status=400)

        try:
            # Fetching session data from Stripe
            session = stripe.checkout.Session.retrieve(session_id)

            # Checking email and payment details securely
            customer_email = None
            if session.customer_details:
                customer_email = session.customer_details.get('email')
            elif session.customer_email:
                customer_email = session.customer_email

            return Response({
                "success": True,
                "status": session.status,                # 'complete', 'open', or 'expired'
                # 'paid', 'unpaid', or 'no_payment_required'
                "payment_status": session.payment_status,
                "customer_email": customer_email,
                "message": "Payment verified" if session.payment_status == 'paid' else "Payment process incomplete"
            }, status=200)

        except stripe.error.StripeError as e:
            return Response({"success": False, "error": str(e)}, status=400)
        except Exception as e:
            return Response({"success": False, "error": "An unexpected error occurred."}, status=500)


# payment/views.py

class SellerStripeLoginLinkView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            seller = request.user.seller_profile
        except AttributeError:
            return Response({
                "success": False, 
                "message": "Seller profile not found."
            }, status=404)

        if not seller.stripe_account_id or not seller.stripe_onboarding_completed:
            return Response({
                "success": False,
                "message": "Please complete Stripe onboarding first before accessing the dashboard."
            }, status=400)

        try:

            login_link = stripe.Account.create_login_link(seller.stripe_account_id)

            return Response({
                "success": True,
                "code": 200,
                "message": "Login link generated successfully.",
                "data": {
                    "url": login_link.url 
                }
            })
        except stripe.error.StripeError as e:
            return Response({
                "success": False, 
                "message": f"Stripe Error: {str(e)}"
            }, status=400)
        except Exception as e:
            return Response({
                "success": False, 
                "message": "An unexpected error occurred."
            }, status=500)


class ProductClickTrackerView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, listing_id):
        user = request.user
        sub = getattr(user, 'subscription', None)

        # ১. সাবস্ক্রিপশন চেক
        if not sub or not sub.is_valid:
            return Response({"error": "Please subscribe to a plan."}, status=403)

        plan = sub.plan
        today = timezone.now().date()

        # ২. দিন পরিবর্তন হলে ক্লিক রিসেট করা
        if user.last_click_date != today:
            user.daily_click_count = 0
            user.last_click_date = today

        # ৩. ক্লিক লিমিট চেক (৫, ৪০, ৬০ ইত্যাদি ডক অনুযায়ী)
        if user.daily_click_count >= plan.clicks_per_day:
            return Response({
                "error": "Daily click limit reached!",
                "limit": plan.clicks_per_day,
                "message": "Upgrade your plan for more access."
            }, status=429)

        # ৪. ক্লিক কাউন্ট বাড়ানো
        user.daily_click_count += 1
        user.save(update_fields=['daily_click_count', 'last_click_date'])

        # ৫. রিটেইল ইউআরএল এ পাঠিয়ে দেওয়া
        listing = get_object_or_404(ProductListing, id=listing_id)
        return Response({"redirect_url": listing.external_url})




class SubscriptionPlanListView(APIView):
    """ইউজারকে ৫টি প্ল্যান দেখানোর জন্য"""
    permission_classes = [AllowAny]

    def get(self, request):
        plans = SubscriptionPlan.objects.filter(is_active=True).order_by('price')
        serializer = SubscriptionPlanSerializer(plans, many=True)
        return Response({
            "success": True,
            "code": 200,
            "message": "Subscription plans fetched.",
            "data": serializer.data
        })

class CreateSubscriptionCheckoutView(APIView):
    """ইউজার যখন কোনো প্ল্যান (Free বা Paid) একটিভ/কিনতে চাবে"""
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        plan_id = request.data.get('plan_id')
        user = request.user
        
        try:
            plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            return Response({"error": "Invalid Plan selected."}, status=404)

        if plan.plan_type == 'FREE':

            if UserSubscription.objects.filter(user=user).exists():
                return Response({"error": "You have already used your free trial or have an active plan."}, status=400)

            UserSubscription.objects.create(
                user=user,
                plan=plan,
                status='TRIAL',
                trial_ends_at=timezone.now() + timedelta(days=plan.trial_days),
                expires_at=timezone.now() + timedelta(days=plan.trial_days)
            )
            return Response({
                "success": True,
                "message": f"Free trial activated for {plan.trial_days} days."
            }, status=201)

        try:
            session = stripe.checkout.Session.create(
                ui_mode='embedded',
                payment_method_types=['card'],
                line_items=[{'price': plan.stripe_price_id, 'quantity': 1}],
                mode='subscription',
                return_url=settings.STRIPE_RETURN_URL + '?session_id={CHECKOUT_SESSION_ID}',
                metadata={
                    'user_id': user.id,
                    'plan_id': plan.id,
                    'type': 'subscription_payment'
                },
                customer_email=user.email,
            )

            return Response({
                "client_secret": session.client_secret,
                "plan_name": plan.name,
                "amount": float(plan.price)
            }, status=201)

        except Exception as e:
            return Response({"error": str(e)}, status=500)

class UserSubscriptionStatusView(APIView):
    """ইউজারের বর্তমান প্ল্যান চেক করা (ড্যাশবোর্ড এবং এক্সেস কন্ট্রোলের জন্য)"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        sub = getattr(user, 'subscription', None)
        
        # যদি সাবস্ক্রিপশন না থাকে (সে শুধু লোকাল প্রোডাক্ট দেখবে)
        if not sub or not sub.is_active:
            return Response({
                "success": True,
                "data": {"plan_name": "None", "is_active": False, "access": "Local Products Only"}
            })

        return Response({
            "success": True,
            "data": {
                "plan_name": sub.plan.name,
                "status": sub.status,
                "is_active": sub.is_active,
                "expires_at": sub.expires_at,
                "clicks_left": sub.plan.clicks_per_day - sub.daily_click_count,
                "days_remaining": sub.days_remaining
            }
        })


class CreateSubscriptionCheckoutView(APIView):
    """ইউজার যখন কোনো প্ল্যান সাবস্ক্রাইব করতে চাবে"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        plan_id = request.data.get('plan_id')
        
        try:
            plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            return Response({"error": "Invalid Plan selected."}, status=404)

        if plan.plan_type == 'FREE':
            return Response({"error": "Free trial cannot be purchased."}, status=400)

        # ১. স্ট্রাইপ সেশন তৈরি (Subscription Mode)
        try:
            session = stripe.checkout.Session.create(
                ui_mode='embedded',
                payment_method_types=['card'],
                line_items=[{
                    'price': plan.stripe_price_id, # স্ট্রাইপ ড্যাশবোর্ড থেকে পাওয়া Price ID
                    'quantity': 1,
                }],
                mode='subscription', # ✅ এটি ওয়ান-টাইম পেমেন্ট থেকে আলাদা
                return_url=settings.STRIPE_RETURN_URL + '?session_id={CHECKOUT_SESSION_ID}',
                metadata={
                    'user_id': request.user.id,
                    'plan_id': plan.id,
                    'type': 'subscription_payment'
                },
                customer_email=request.user.email,
            )

            return Response({
                "client_secret": session.client_secret,
                "plan_name": plan.name,
                "amount": float(plan.price)
            }, status=201)

        except Exception as e:
            return Response({"error": str(e)}, status=500)


class ManageSubscriptionView(APIView):
    """
    Generates a Stripe Customer Portal link for the user.
    Users can manage their billing, change plans, or cancel subscriptions here.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        # Retrieve user subscription details
        sub = getattr(user, 'subscription', None)

        # 1. Check if the user has a valid Stripe Customer ID
        if not sub or not sub.stripe_customer_id:
            return Response({
                "success": False, 
                "message": "No active paid subscription or customer record found."
            }, status=404)

        try:
            # 2. Create a Billing Portal Session
            # return_url is where the user will be redirected after closing the portal
            session = stripe.billing_portal.Session.create(
                customer=sub.stripe_customer_id,
                return_url=settings.STRIPE_RETURN_URL, 
            )

            return Response({
                "success": True,
                "code": 200,
                "message": "Portal link generated successfully.",
                "data": {
                    "portal_url": session.url # Frontend should redirect user to this URL
                }
            })
        except stripe.error.StripeError as e:
            return Response({
                "success": False, 
                "message": f"Stripe Portal Error: {str(e)}"
            }, status=400)
        except Exception:
            return Response({
                "success": False, 
                "message": "An unexpected error occurred while accessing the portal."
            }, status=500)