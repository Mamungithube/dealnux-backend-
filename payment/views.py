import stripe
from decimal import Decimal

from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.http import HttpResponse

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny

from django.db.models import F
from django.db import transaction
from .models import Payment, SellerPayout
from store.models import SellerProduct, Order, Coupon

stripe.api_key = settings.STRIPE_SECRET_KEY
PLATFORM_FEE_PERCENT = Decimal('10')  


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

class CreateCheckoutSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # ১. ডাটা কালেকশন ও ভ্যালিডেশন
        p_id = request.data.get('seller_product')
        qty = int(request.data.get('quantity', 1))
        
        try:
            seller_product = SellerProduct.objects.get(id=p_id, status='APPROVED')
        except SellerProduct.DoesNotExist:
            return Response({'error': 'Product not available.'}, status=404)

        # ২. ডক অনুযায়ী নতুন ক্যালকুলেশন
        amounts = _calculate_order_amounts(seller_product, qty, request.data.get('coupon_code', ''))

        # ৩. পেমেন্ট রেকর্ড তৈরি (মডেলের নতুন ফিল্ডসহ)
        payment = Payment.objects.create(
            buyer=request.user, seller_product=seller_product, quantity=qty,
            unit_price=amounts['unit_price'], item_total=amounts['item_total'],
            shipping_fee=amounts['shipping_fee'], service_fee=amounts['service_fee'],
            discount_amount=amounts['discount_amount'], final_amount=amounts['final_amount'],
            currency=seller_product.currency.lower(), status='PENDING'
        )

        try:
            # ৪. Embedded Mode Session তৈরি (ইউজার অ্যাপের ভেতরেই থাকবে)
            session = stripe.checkout.Session.create(
                ui_mode='embedded', 
                line_items=[
                    {
                        'price_data': {
                            'currency': payment.currency,
                            'unit_amount': int(amounts['item_total'] * 100),
                            'product_data': {'name': seller_product.title},
                        },
                        'quantity': 1,
                    },
                    {
                        'price_data': {
                            'currency': payment.currency,
                            'unit_amount': int(amounts['service_fee'] * 100),
                            'product_data': {'name': 'Dealnux Service Fee (Buyer Protection)'},
                        },
                        'quantity': 1,
                    }
                ],
                # ৫. শিপিং ফি আলাদাভাবে দেখানো
                shipping_options=[{
                    'shipping_rate_data': {
                        'type': 'fixed_amount',
                        'fixed_amount': {'amount': int(amounts['shipping_fee'] * 100), 'currency': payment.currency},
                        'display_name': 'Standard Shipping',
                    }
                }] if amounts['shipping_fee'] > 0 else [],
                mode='payment',
                return_url=settings.STRIPE_RETURN_URL + '?session_id={CHECKOUT_SESSION_ID}',
                metadata={'payment_id': payment.id, 'type': 'store_payment'},
                customer_email=request.user.email,
            )

            payment.stripe_checkout_session_id = session.id
            payment.save()

            return Response({
                'client_secret': session.client_secret, # এটি দিয়ে অ্যাপের ভেতর ফর্ম খুলবে
                'payment_id': payment.id,
                'breakdown': {
                    'item': float(amounts['item_total']),
                    'shipping': float(amounts['shipping_fee']),
                    'fee': float(amounts['service_fee']),
                    'total': float(amounts['final_amount'])
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
    """
    Stripe will POST here for payment events.
    POST /api/v1/store/webhook/stripe/
    """
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

        elif event['type'] == 'checkout.session.expired':
            self._handle_checkout_expired(event['data']['object'])

        return HttpResponse(status=200)

    def _handle_checkout_completed(self, session):
        payment_id = session.get('metadata', {}).get('payment_id')
        if not payment_id:
            return

        try:
            payment = Payment.objects.get(id=payment_id, status='PENDING')
        except Payment.DoesNotExist:
            return

        # Payment update
        payment.status = 'PAID'
        payment.stripe_payment_intent_id = session.get('payment_intent', '')
        payment.save(update_fields=['status', 'stripe_payment_intent_id'])

        seller_product = payment.seller_product
        if not seller_product:
            return

        # Order create
        order = Order.objects.create(
            buyer=payment.buyer,
            seller=seller_product.seller,
            seller_product=seller_product,
            listing=seller_product.linked_listing,
            quantity=payment.quantity,
            unit_price=payment.unit_price,
            total_price=payment.final_amount,
            currency=payment.currency,
            shipping_address=payment.shipping_address,
            note=payment.note,
            status='CONFIRMED',
        )

        # Link the order to payment.
        payment.order = order
        payment.save(update_fields=['order'])

        # Reduce stock
        seller_product.quantity -= payment.quantity
        seller_product.save(update_fields=['quantity'])

        # Increase coupon usage count
        if payment.coupon_code:
            Coupon.objects.filter(code=payment.coupon_code.upper()).update(
                used_count=F('used_count') + 1
            )

        # Seller stats update
        seller = seller_product.seller
        seller.total_orders += 1
        seller.total_earnings += payment.final_amount
        seller.save(update_fields=['total_orders', 'total_earnings'])

        # Seller payout created
        fee_amount = payment.final_amount * PLATFORM_FEE_PERCENT / 100
        seller_amount = payment.final_amount - fee_amount

        payout = SellerPayout.objects.create(
            seller=seller,
            payment=payment,
            order=order,
            gross_amount=payment.final_amount,
            platform_fee_percent=PLATFORM_FEE_PERCENT,
            platform_fee_amount=fee_amount,
            seller_amount=seller_amount,
            stripe_account_id=seller.stripe_account_id,
        )

        # Transfer money to the seller's Stripe account.
        if seller.stripe_account_id and seller.stripe_account_verified:
            try:
                transfer = stripe.Transfer.create(
                    amount=int(seller_amount * 100),
                    currency=payment.currency,
                    destination=seller.stripe_account_id,
                    transfer_group=f'ORDER_{order.id}',
                    metadata={
                        'order_id':   order.id,
                        'payment_id': payment.id,
                        'seller_id':  seller.id,
                    }
                )
                payout.stripe_transfer_id = transfer.id
                payout.status = 'COMPLETED'
                payout.save(update_fields=['stripe_transfer_id', 'status'])
            except stripe.error.StripeError as e:
                payout.status = 'FAILED'
                payout.failure_reason = str(e)
                payout.save(update_fields=['status', 'failure_reason'])

    def _handle_checkout_expired(self, session):
        payment_id = session.get('metadata', {}).get('payment_id')
        if payment_id:
            Payment.objects.filter(
                id=payment_id, status='PENDING').update(status='CANCELLED')


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
        except Exception:
            return Response({'error': 'Not a seller.'}, status=403)

        if not seller.stripe_account_id:
            return Response({
                'connected': False,
                'verified':  False,
                'message':   'No Stripe account connected. Please connect your Stripe account first.',
            })

        try:
            account = stripe.Account.retrieve(seller.stripe_account_id)
            verified = account.get('charges_enabled', False) and account.get(
                'payouts_enabled', False)

            if verified and not seller.stripe_account_verified:
                seller.stripe_account_verified = True
                seller.save(update_fields=['stripe_account_verified'])

            return Response({
                'connected':         True,
                'verified':          verified,
                'charges_enabled':   account.get('charges_enabled'),
                'payouts_enabled':   account.get('payouts_enabled'),
                'stripe_account_id': seller.stripe_account_id,
            })
        except stripe.error.StripeError as e:
            return Response({'error': str(e)}, status=500)


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
                'final_amount':    p.final_amount,
                'discount_amount': p.discount_amount,
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
                'gross_amount':       p.gross_amount,
                'platform_fee':       p.platform_fee_amount,
                'seller_amount':      p.seller_amount,
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


