import json
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
    SubscriptionPlanSerializer, CheckoutSerializer, ShippingAddressSerializer

)

from django.utils import timezone
stripe.api_key = settings.STRIPE_SECRET_KEY
PLATFORM_FEE_PERCENT = Decimal('10')

# ============================================================================
# Helper function to calculate amounts based on product price, quantity, and coupon code.
# ================= ===========================================================

# payment/views.py


def _calculate_order_amounts(seller_product, quantity, coupon_code=''):
    unit_price = seller_product.price
    subtotal = unit_price * quantity
    discount = Decimal('0')

    if coupon_code:
        try:
            coupon = Coupon.objects.get(
                code=coupon_code.upper().strip(), seller=seller_product.seller)
            if coupon.is_valid and subtotal >= coupon.min_order_amount:
                if coupon.discount_type == 'PERCENTAGE':
                    discount = subtotal * (coupon.discount_value / 100)
                else:
                    discount = min(coupon.discount_value, subtotal)
                print(
                    f"✅ Discount Applied: {discount} for coupon {coupon_code}")
            else:
                print(f"⚠️ Coupon invalid or min amount not met.")
        except Coupon.DoesNotExist:
            print(
                f"❌ Coupon {coupon_code} not found for seller {seller_product.seller.shop_name}")

    item_total = subtotal - discount
    shipping = seller_product.shipping_cost if not seller_product.free_shipping else Decimal(
        '0')

    # service fee is 8% of (item total + shipping)
    service_fee = (item_total + shipping) * Decimal('0.08')
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


class CreateCheckoutSessionView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        items_data = request.data.get('items', [])
        shipping_address_data = request.data.get('shipping_address')
        root_coupon_code = request.data.get('coupon_code', '').strip()

        if not items_data:
            return Response({'error': 'Items list is required.'}, status=400)
        if not shipping_address_data:
            return Response({'error': 'shipping_address is required.'}, status=400)

        # Validate structured shipping address
        address_serializer = ShippingAddressSerializer(data=shipping_address_data)
        if not address_serializer.is_valid():
            return Response({'error': address_serializer.errors}, status=400)
        addr = address_serializer.validated_data

        total_item_price = Decimal('0')
        total_shipping_fee = Decimal('0')
        total_discount = Decimal('0')

        line_items = []
        validated_items = []

        for item in items_data:
            p_id = item.get('seller_product')
            qty = int(item.get('quantity', 1))
            c_code = item.get('coupon_code', '') or root_coupon_code

            try:
                product = SellerProduct.objects.get(id=p_id, status='APPROVED')
            except SellerProduct.DoesNotExist:
                return Response({'error': f'Product ID {p_id} not found or not approved.'}, status=404)

            res = _calculate_order_amounts(product, qty, c_code)

            total_item_price += res['item_total']
            total_shipping_fee += res['shipping_fee']
            total_discount += res['discount_amount']

            line_items.append({
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': int((res['item_total'] / qty) * 100),
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

        # Service fee calculation (8% of item total + shipping)
        service_fee = (total_item_price + total_shipping_fee) * Decimal('0.08')
        final_grand_total = total_item_price + total_shipping_fee + service_fee

        # Build human-readable address string for legacy field
        address_line2_part = f", {addr['address_line2']}" if addr.get('address_line2') else ''
        shipping_address_str = (
            f"{addr['first_name']} {addr['last_name']}, "
            f"{addr['address_line1']}{address_line2_part}, "
            f"{addr['city']}, {addr['state']} {addr['zip_code']}, "
            f"{addr['country']}"
        )

        # Create payment record
        payment = Payment.objects.create(
            buyer=request.user,
            payment_type='STORE',

            # Legacy plain-text field
            shipping_address=shipping_address_str,

            # Structured address fields
            shipping_first_name=addr['first_name'],
            shipping_last_name=addr['last_name'],
            shipping_address_line1=addr['address_line1'],
            shipping_address_line2=addr.get('address_line2', ''),
            shipping_city=addr['city'],
            shipping_state=addr['state'],
            shipping_zip_code=addr['zip_code'],
            shipping_country=addr['country'],

            unit_price=total_item_price,
            total_amount=total_item_price + total_shipping_fee + total_discount,
            item_total=total_item_price,
            shipping_fee=total_shipping_fee,
            service_fee=service_fee,
            discount_amount=total_discount,
            final_amount=final_grand_total,
            currency='usd',
            status='PENDING'
        )

        try:
            line_items.append({
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': int(service_fee * 100),
                    'product_data': {'name': 'Dealnux Service Fee (Buyer Protection)'},
                },
                'quantity': 1,
            })

            session = stripe.checkout.Session.create(
                ui_mode='embedded',
                line_items=line_items,
                mode='payment',
                return_url=settings.STRIPE_RETURN_URL,
                automatic_tax={'enabled': True},
                metadata={
                    'payment_id': payment.id,
                    'type': 'store_payment',
                    'items_json': json.dumps(validated_items)
                },
                customer_email=request.user.email,
            )

            payment.stripe_checkout_session_id = session.id
            payment.save()
            tax_amount = Decimal(session.total_details.amount_tax or 0) / 100
            return Response({
                'client_secret': session.client_secret,
                'payment_id': payment.id,
                'breakdown': {
                    'subtotal': float(total_item_price),
                    'shipping': float(total_shipping_fee),
                    'service_fee': float(service_fee),
                    'tax': float(tax_amount),        
                    'grand_total': float(final_grand_total + tax_amount)
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
            'payment_id') 

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
        # 'store_payment', 'ad_payment', 'subscription_payment'
        p_type = metadata.get('type')
        payment_id = metadata.get('payment_id')

        if p_type == 'subscription_payment':
            self._handle_subscription_success(session)
            return 

        if payment_id:
            try:
                from .models import Payment
                payment = Payment.objects.get(id=payment_id)
                payment.status = 'PAID'
                payment.stripe_payment_intent_id = session.get(
                    'payment_intent', '')
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
        
        buyer = payment.buyer

        with transaction.atomic():
            for item_data in items:
                try:
                    seller_product = SellerProduct.objects.get(id=item_data['id'])
                    
                    Order.objects.create(
                        buyer=buyer,
                        seller=seller_product.seller,
                        seller_product=seller_product,
                        listing=seller_product.linked_listing,
                        quantity=item_data['qty'],
                        unit_price=seller_product.price,
                        item_total=Decimal(str(item_data['item_total'])),
                        shipping_fee=Decimal(str(item_data['shipping'])),
                        service_fee=(Decimal(str(item_data['item_total'])) + Decimal(str(item_data['shipping']))) * Decimal('0.08'),
                        total_price=payment.final_amount,
                        currency=payment.currency,
                        shipping_address=payment.shipping_address,
                        status='PENDING',
                    )

                    seller_product.quantity -= item_data['qty']
                    seller_product.save()

                    seller = seller_product.seller
                    amount_for_seller = Decimal(str(item_data['item_total'])) + Decimal(str(item_data['shipping']))
                    seller.pending_balance += amount_for_seller
                    seller.total_orders += 1
                    seller.save()

                except Exception as e:
                    logger.error(f"Error processing item in webhook: {str(e)}")

            from api_integration.models import CartItem
            CartItem.objects.filter(user=buyer).delete()
            print(f"✅ Cart cleared for user: {buyer.email}")

            # If this was the buyer's first purchase, and they already have an active subscription,
            # perform referral reward processing now.
            self._process_referral_reward(buyer)

    def _handle_subscription_success(self, session):
        """Activates the paid subscription plan for the user in the database."""
        metadata = session.get('metadata', {})
        user_id = metadata.get('user_id')
        plan_id = metadata.get('plan_id')
        stripe_sub_id = session.get('subscription')
        stripe_cust_id = session.get('customer')

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
                    'stripe_customer_id': stripe_cust_id,
                    'started_at': now,
                    'expires_at': now + timedelta(days=days),
                    'trial_ends_at': now 
                }
            )
            print(
                f"✅ Payment success! Subscription activated for: {user.email}")

            self._process_referral_reward(user)

        except Exception as e:
            print(f"❌ Error in _handle_subscription_success: {str(e)}")

    def _process_referral_reward(self, user):
        """
        Award the referral bonus once, only after both the referred user and the referrer
        have active paid subscriptions and the referred user has completed a first DEALNUX purchase.
        """
        from decimal import Decimal
        from store.models import Order

        try:
            # Only process if the referred user has made at least one order.
            if not Order.objects.filter(buyer=user).exists():
                return

            # Only pay the referrer once per referred user.
            if user.referred_by and not user.has_referral_reward_awarded:
                referrer = user.referred_by
                user_subscription = getattr(user, 'subscription', None)
                referrer_subscription = getattr(referrer, 'subscription', None)

                if (
                    user_subscription is not None and user_subscription.status == 'ACTIVE' and
                    referrer_subscription is not None and referrer_subscription.status == 'ACTIVE'
                ):
                    referrer.balance += Decimal('10')
                    referrer.save(update_fields=['balance'])

                    user.has_referral_reward_awarded = True
                    user.save(update_fields=['has_referral_reward_awarded'])
                    print(f"✅ Referral reward paid to {referrer.email} for referred user {user.email}")

            # If the current user is a referrer, check for any referred users who already have active subscriptions
            # and have completed their first purchase.
            current_subscription = getattr(user, 'subscription', None)
            if current_subscription is not None and current_subscription.status == 'ACTIVE':
                pending_referred_users = user.referrals.filter(
                    has_claimed_referral=True,
                    has_referral_reward_awarded=False
                )
                for referred_user in pending_referred_users:
                    referred_subscription = getattr(referred_user, 'subscription', None)
                    if referred_subscription is not None and referred_subscription.status == 'ACTIVE':
                        if Order.objects.filter(buyer=referred_user).exists():
                            user.balance += Decimal('10')
                            user.save(update_fields=['balance'])

                            referred_user.has_referral_reward_awarded = True
                            referred_user.save(update_fields=['has_referral_reward_awarded'])
                            print(f"✅ Deferred referral reward paid to {user.email} for referred user {referred_user.email}")

        except Exception as e:
            print(f"❌ Error processing referral reward: {str(e)}")

    def _handle_recurring_subscription(self, invoice):
        stripe_sub_id = invoice.get('subscription')
        try:
            sub = UserSubscription.objects.get(
                stripe_subscription_id=stripe_sub_id)
            days = 365 if 'YEARLY' in sub.plan.plan_type else 30
            sub.expires_at = timezone.now() + timedelta(days=days)
            sub.save()
        except UserSubscription.DoesNotExist:
            pass

    def _handle_checkout_expired(self, session):
        payment_id = session.get('metadata', {}).get('payment_id')
        if payment_id:
            Payment.objects.filter(
                id=payment_id, status='PENDING').update(status='CANCELLED')


# ============================================================================
# 4. Stripe Connect — Create a Seller's Stripe account (no changes)
# ============================================================================

class SellerStripeConnectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            seller = request.user.seller_profile
        except Exception:
            return Response({"success": False, "message": "You are not an approved seller."}, status=403)

        if not seller.stripe_account_id:
            account = stripe.Account.create(
                type='express',
                email=request.user.email,
                capabilities={'transfers': {'requested': True}},
                metadata={'seller_id': seller.id}
            )
            seller.stripe_account_id = account.id
            seller.save()

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

        if amount < Decimal('10.00'):
            return Response({"success": False, "message": "Minimum payout is $10.00"}, status=400)

        if amount > seller.available_balance:
            return Response({"success": False, "message": "Insufficient balance."}, status=400)

        try:

            seller.available_balance -= amount
            seller.total_withdrawn += amount
            seller.save()

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

            is_fully_verified = account.get(
                'charges_enabled', False) and account.get('payouts_enabled', False)

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

            login_link = stripe.Account.create_login_link(
                seller.stripe_account_id)

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
        try:
            listing = ProductListing.objects.select_related('platform').get(
                id=listing_id,
                is_available=True
            )
        except ProductListing.DoesNotExist:
            return Response({"error": "Listing not found."}, status=404)

        # Local seller products should be accessible without subscription.
        if listing.platform.api_enabled:
            from payment.utils import validate_and_increment_click
            success, message = validate_and_increment_click(user, product_id=listing.id)
            if not success:
                return Response({
                    "error": message,
                    "message": message
                }, status=429 if "limit" in message.lower() else 403)

        return Response({"redirect_url": listing.external_url})


class SubscriptionPlanListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        plans = SubscriptionPlan.objects.filter(
            is_active=True).order_by('price')
        serializer = SubscriptionPlanSerializer(plans, many=True)
        return Response({
            "success": True,
            "code": 200,
            "message": "Subscription plans fetched.",
            "data": serializer.data
        })


class CreateSubscriptionCheckoutView(APIView):
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
                return_url=settings.STRIPE_RETURN_URL +
                '?session_id={CHECKOUT_SESSION_ID}',
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
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from payment.models import UserSubscription
        sub = UserSubscription.objects.filter(user=request.user).first()
        has_used_trial = UserSubscription.objects.filter(user=request.user).exists()
        if not sub or not sub.is_active:
            return Response({
                "success": True,
                "data": {
                    "plan_name": "None",
                    "price": 0.0,
                    "status": "INACTIVE",
                    "is_active": False,
                    "has_used_trial": has_used_trial,
                    "access": "Local Products Only",
                    "features": [] 
                }
            })

        return Response({
            "success": True,
            "data": {
                "plan_name": sub.plan.name,
                "price": float(sub.plan.price),    
                "renews_at": sub.expires_at,  
                "status": sub.status,
                "is_active": sub.is_active,
                "has_used_trial": True,
                "days_remaining": sub.days_remaining,
                "clicks_left": sub.plan.clicks_per_day - sub.daily_click_count,
                "features": sub.plan.features  
            }
        })


class ManageSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from payment.models import UserSubscription
        sub = UserSubscription.objects.filter(user=request.user).first()

        if not sub or not sub.stripe_customer_id:
            return Response({
                "success": False, 
                "message": "No active paid subscription or billing record found."
            }, status=404)

        try:
            session = stripe.billing_portal.Session.create(
                customer=sub.stripe_customer_id,
                return_url=settings.STRIPE_RETURN_URL, 
            )
            return Response({
                "success": True,
                "code": 200,
                "data": {"portal_url": session.url}
            })
        except Exception as e:
            return Response({"success": False, "message": str(e)}, status=500)
