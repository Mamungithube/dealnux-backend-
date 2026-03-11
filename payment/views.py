import stripe
import json
from decimal import Decimal

from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.http import HttpResponse

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status

from django.db.models import F
from .models import Payment, SellerPayout
from store.models import SellerProduct, Order, Coupon

stripe.api_key = settings.STRIPE_SECRET_KEY
PLATFORM_FEE_PERCENT = Decimal('10')  # 10% platform fee


# ============================================================================
# Helper
# ============================================================================

def _calculate_amounts(seller_product, quantity, coupon_code=''):
    """Calculate price and return dict"""
    unit_price      = seller_product.price
    total_amount    = unit_price * quantity
    discount_amount = Decimal('0')

    if coupon_code:
        try:
            coupon = Coupon.objects.get(code=coupon_code.upper(), seller=seller_product.seller)
            if coupon.is_valid and total_amount >= coupon.min_order_amount:
                if coupon.discount_type == 'PERCENTAGE':
                    discount_amount = total_amount * (coupon.discount_value / 100)
                else:
                    discount_amount = min(coupon.discount_value, total_amount)
        except Coupon.DoesNotExist:
            pass

    final_amount = total_amount - discount_amount
    return {
        'unit_price':       unit_price,
        'total_amount':     total_amount,
        'discount_amount':  discount_amount,
        'final_amount':     final_amount,
    }


# ============================================================================
# 1. Checkout — create Stripe Session
# ============================================================================

class CreateCheckoutSessionView(APIView):
    """
    When buyer POSTs here, they will get a Stripe Checkout URL.

    POST /api/v1/store/checkout/
    {
        "seller_product": 1,
        "quantity": 2,
        "shipping_address": "Dhaka, Bangladesh",
        "coupon_code": "SAVE50",   (optional)
        "note": "Handle carefully"  (optional)
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        seller_product_id = request.data.get('seller_product')
        quantity          = int(request.data.get('quantity', 1))
        shipping_address  = request.data.get('shipping_address', '')
        coupon_code       = request.data.get('coupon_code', '')
        note              = request.data.get('note', '')

        # Validate
        if not seller_product_id:
            return Response({'error': 'seller_product is required.'}, status=400)

        try:
            seller_product = SellerProduct.objects.get(id=seller_product_id, status='APPROVED')
        except SellerProduct.DoesNotExist:
            return Response({'error': 'Product not found or not available.'}, status=404)

        if seller_product.quantity < quantity:
            return Response({'error': f'Only {seller_product.quantity} items available.'}, status=400)

        if not shipping_address:
            return Response({'error': 'shipping_address is required.'}, status=400)

        # Amounts
        amounts = _calculate_amounts(seller_product, quantity, coupon_code)

        # Stripe amount (cents)
        amount_cents = int(amounts['final_amount'] * 100)

        # Create payment record (PENDING)
        payment = Payment.objects.create(
            buyer               = request.user,
            seller_product      = seller_product,
            quantity            = quantity,
            shipping_address    = shipping_address,
            coupon_code         = coupon_code,
            note                = note,
            unit_price          = amounts['unit_price'],
            total_amount        = amounts['total_amount'],
            discount_amount     = amounts['discount_amount'],
            final_amount        = amounts['final_amount'],
            currency            = seller_product.currency.lower(),
        )

        # Stripe Checkout Session
        try:
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency':     seller_product.currency.lower(),
                        'unit_amount':  int(amounts['unit_price'] * 100),
                        'product_data': {
                            'name':         seller_product.title,
                            'description':  seller_product.description[:500] if seller_product.description else '',
                            'images':       [request.build_absolute_uri(seller_product.main_image.url)] if seller_product.main_image else [],
                        },
                    },
                    'quantity': quantity,
                }],
                discounts=[{
                    'coupon': stripe.Coupon.create(
                        amount_off  = int(amounts['discount_amount'] * 100),
                        currency    = seller_product.currency.lower(),
                        duration    = 'once',
                        name        = coupon_code,
                    ).id
                }] if amounts['discount_amount'] > 0 else [],
                mode='payment',
                success_url = settings.STRIPE_SUCCESS_URL + f'?session_id={{CHECKOUT_SESSION_ID}}',
                cancel_url  = settings.STRIPE_CANCEL_URL,
                metadata={
                    'payment_id':       payment.id,
                    'buyer_id':         request.user.id,
                    'seller_product_id': seller_product.id,
                    'quantity':         quantity,
                },
                customer_email = request.user.email,
            )

            # Save session id to payment
            payment.stripe_checkout_session_id = session.id
            payment.stripe_checkout_url        = session.url
            payment.save(update_fields=['stripe_checkout_session_id', 'stripe_checkout_url'])

        except stripe.error.StripeError as e:
            payment.status = 'FAILED'
            payment.save(update_fields=['status'])
            return Response({'error': str(e)}, status=500)

        return Response({
            'payment_id':       payment.id,
            'checkout_url':     session.url,
            'amount':           amounts['final_amount'],
            'discount':         amounts['discount_amount'],
            'currency':         seller_product.currency,
        }, status=201)


# ============================================================================
# 2. Stripe Webhook — Create Order when payment succeeds
# ============================================================================

@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhookView(APIView):
    """
    Stripe will POST here for payment events.
    POST /api/v1/store/webhook/stripe/
    """
    permission_classes = [AllowAny]

    def post(self, request):
        payload     = request.body
        sig_header  = request.META.get('HTTP_STRIPE_SIGNATURE', '')

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
        payment.status                   = 'PAID'
        payment.stripe_payment_intent_id = session.get('payment_intent', '')
        payment.save(update_fields=['status', 'stripe_payment_intent_id'])

        seller_product = payment.seller_product
        if not seller_product:
            return

        # Create order
        order = Order.objects.create(
            buyer            = payment.buyer,
            seller           = seller_product.seller,
            seller_product   = seller_product,
            listing          = seller_product.linked_listing,
            quantity         = payment.quantity,
            unit_price       = payment.unit_price,
            total_price      = payment.final_amount,
            currency         = payment.currency,
            shipping_address = payment.shipping_address,
            note             = payment.note,
            status           = 'CONFIRMED',  # payment done so directly set to CONFIRMED
        )

        # Link order to payment
        payment.order = order
        payment.save(update_fields=['order'])

        # Reduce stock
        seller_product.quantity -= payment.quantity
        seller_product.save(update_fields=['quantity'])

        # Increase coupon used count
        if payment.coupon_code:
            Coupon.objects.filter(code=payment.coupon_code.upper()).update(
                used_count=F('used_count') + 1
            )

        # Seller stats update
        seller = seller_product.seller
        seller.total_orders   += 1
        seller.total_earnings += payment.final_amount
        seller.save(update_fields=['total_orders', 'total_earnings'])

        # Create seller payout
        fee_amount    = payment.final_amount * PLATFORM_FEE_PERCENT / 100
        seller_amount = payment.final_amount - fee_amount

        payout = SellerPayout.objects.create(
            seller               = seller,
            payment              = payment,
            order                = order,
            gross_amount         = payment.final_amount,
            platform_fee_percent = PLATFORM_FEE_PERCENT,
            platform_fee_amount  = fee_amount,
            seller_amount        = seller_amount,
            stripe_account_id    = seller.stripe_account_id,
        )

        # Stripe Connect Transfer — send to seller's stripe account
        if seller.stripe_account_id and seller.stripe_account_verified:
            try:
                transfer = stripe.Transfer.create(
                    amount      = int(seller_amount * 100),
                    currency    = payment.currency,
                    destination = seller.stripe_account_id,
                    transfer_group = f'ORDER_{order.id}',
                    metadata={
                        'order_id':   order.id,
                        'payment_id': payment.id,
                        'seller_id':  seller.id,
                    }
                )
                payout.stripe_transfer_id = transfer.id
                payout.status             = 'COMPLETED'
                payout.save(update_fields=['stripe_transfer_id', 'status'])
            except stripe.error.StripeError as e:
                payout.status         = 'FAILED'
                payout.failure_reason = str(e)
                payout.save(update_fields=['status', 'failure_reason'])

    def _handle_checkout_expired(self, session):
        payment_id = session.get('metadata', {}).get('payment_id')
        if payment_id:
            Payment.objects.filter(id=payment_id, status='PENDING').update(status='CANCELLED')


# ============================================================================
# 3. Stripe Connect — Create seller's Stripe account
# ============================================================================

class SellerStripeConnectView(APIView):
    """
    Will give seller's Stripe Connect onboarding URL.
    POST /api/v1/store/seller/stripe-connect/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            seller = request.user.seller_profile
        except Exception:
            return Response({'error': 'You are not an approved seller.'}, status=403)

        if not seller.is_active:
            return Response({'error': 'Your seller account is inactive.'}, status=403)

        # Create Stripe Connect account or use existing account
        if not seller.stripe_account_id:
            account = stripe.Account.create(
                type    = 'express',
                email   = request.user.email,
                capabilities={
                    'transfers': {'requested': True},
                },
                metadata={'seller_id': seller.id}
            )
            seller.stripe_account_id = account.id
            seller.save(update_fields=['stripe_account_id'])
        
        # Create onboarding link
        account_link = stripe.AccountLink.create(
            account     = seller.stripe_account_id,
            refresh_url = settings.STRIPE_CONNECT_REFRESH_URL,
            return_url  = settings.STRIPE_CONNECT_RETURN_URL,
            type        = 'account_onboarding',
        )

        return Response({
            'onboarding_url':   account_link.url,
            'stripe_account_id': seller.stripe_account_id,
        })


class SellerStripeStatusView(APIView):
    """
    Will check seller's Stripe account status.
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
                'connected':    False,
                'verified':     False,
                'message':      'No Stripe account connected. POST /store/seller/stripe-connect/ to connect.',
            })

        # Get account details from Stripe
        try:
            account = stripe.Account.retrieve(seller.stripe_account_id)
            verified = account.get('charges_enabled', False) and account.get('payouts_enabled', False)

            if verified and not seller.stripe_account_verified:
                seller.stripe_account_verified = True
                seller.save(update_fields=['stripe_account_verified'])

            return Response({
                'connected':            True,
                'verified':             verified,
                'charges_enabled':      account.get('charges_enabled'),
                'payouts_enabled':      account.get('payouts_enabled'),
                'stripe_account_id':    seller.stripe_account_id,
            })
        except stripe.error.StripeError as e:
            return Response({'error': str(e)}, status=500)


# ============================================================================
# 4. Payment History
# ============================================================================

class PaymentHistoryView(APIView):
    """
    Buyer's own payment history.
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
                'id':               p.id,
                'product':          p.seller_product.title if p.seller_product else None,
                'quantity':         p.quantity,
                'final_amount':     p.final_amount,
                'discount_amount':  p.discount_amount,
                'currency':         p.currency,
                'status':           p.status,
                'order_id':         p.order.id if p.order else None,
                'order_status':     p.order.status if p.order else None,
                'checkout_url':     p.stripe_checkout_url if p.status == 'PENDING' else None,
                'created_at':       p.created_at,
            })
        return Response(data)


class SellerPayoutHistoryView(APIView):
    """
    Seller's payout history.
    GET /api/v1/store/seller/payouts/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            seller = request.user.seller_profile
        except Exception:
            return Response({'error': 'Not a seller.'}, status=403)

        payouts = SellerPayout.objects.filter(seller=seller).select_related('payment', 'order')
        data = []
        for p in payouts:
            data.append({
                'id':                   p.id,
                'order_id':             p.order.id if p.order else None,
                'gross_amount':         p.gross_amount,
                'platform_fee':         p.platform_fee_amount,
                'seller_amount':        p.seller_amount,
                'currency':             p.payment.currency,
                'status':               p.status,
                'stripe_transfer_id':   p.stripe_transfer_id,
                'failure_reason':       p.failure_reason,
                'created_at':           p.created_at,
            })
        return Response(data)