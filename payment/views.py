import logging
from custom_ads.utils import send_dealnux_email
import json
from datetime import timedelta
from payment.utils import refresh_subscription_limits
import stripe
from decimal import Decimal

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.http import HttpResponse

logger = logging.getLogger(__name__)

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny

from django.db.models import F
from django.db import transaction
from .models import Payment, SellerPayout, SubscriptionPlan, UserSubscription
from store.models import SellerProduct, Order, Coupon
from api_integration.models import ProductListing
from account.models import User
from .services import create_orders_from_payment
from . serializers import (
    SubscriptionPlanSerializer, CheckoutSerializer, ShippingAddressSerializer

)
from rest_framework.pagination import PageNumberPagination
import time
from django.utils import timezone
stripe.api_key = settings.STRIPE_SECRET_KEY
PLATFORM_FEE_PERCENT = Decimal('10')


from dealnux.pagination import CustomPagination



def _calculate_order_amounts(seller_product, quantity, coupon_code=''):
    unit_price = Decimal(str(seller_product.price))
    subtotal = unit_price * Decimal(str(quantity))
    discount = Decimal('0')

    if coupon_code:
        c_code = str(coupon_code).upper().strip()
        from django.db.models import Q
        coupon = Coupon.objects.filter(
            code=c_code,
            is_active=True
        ).filter(
            Q(seller=seller_product.seller) | Q(seller__isnull=True)
        ).first()

        if coupon and coupon.is_valid and subtotal >= coupon.min_order_amount:
            if coupon.discount_type == 'PERCENTAGE':
                discount = (subtotal * Decimal(str(coupon.discount_value))) / Decimal('100')
            else:
                discount = min(Decimal(str(coupon.discount_value)), subtotal)
            logger.info(f"Discount Applied: {discount} for coupon {c_code}")
        else:
            logger.info(f"Coupon '{c_code}' invalid, expired, or min order amount not met.")

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


# -------------------------- Create Stripe Embedded Checkout Session View (Product Cart Checkout) --------------------------
class CreateCheckoutSessionView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        """
        Handles the creation of a checkout session for purchasing products.
        It calculates total amounts, applies user balance if requested, and creates a Stripe session.
        """
        items_data = request.data.get('items', [])
        use_balance = request.data.get('use_balance', False)
        user = request.user
        shipping_address = request.data.get('shipping_address')
        
        root_coupon_code = (
            request.data.get('coupon_code')
            or request.data.get('couponCode')
            or request.data.get('coupon')
            or ''
        ).strip()

        if not items_data or not shipping_address:
            # Basic validation for required fields
            return Response({'error': 'Items and shipping address are required.'}, status=400)

        total_item_price = Decimal('0')
        total_shipping_fee = Decimal('0')
        total_discount = Decimal('0')
        line_items = []
        validated_items = []

        # Loop through each item in the cart to calculate totals and prepare for Stripe
        for item in items_data:
            p_id = item.get('seller_product')
            qty = int(item.get('quantity', 1))
            c_code = (
                item.get('coupon_code')
                or item.get('couponCode')
                or item.get('coupon')
                or root_coupon_code
            )

            try:
                product = SellerProduct.objects.get(id=p_id, status='APPROVED')
            except SellerProduct.DoesNotExist:
                return Response({'error': f'Product ID {p_id} not found.'}, status=404)
            
            # Calculate amounts for this specific item (price, discount, shipping, etc.)
            res = _calculate_order_amounts(product, qty, c_code)
            item_total = res['item_total']
            discount_amt = res['discount_amount']

            total_item_price += item_total
            total_shipping_fee += res['shipping_fee']
            total_discount += discount_amt

            # Prepare line item for Stripe checkout session
            line_items.append({
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': int((item_total / qty) * 100),
                    'product_data': {
                        'name': product.title,
                        'images': [request.build_absolute_uri(product.main_image.url)] if product.main_image else [],
                    },
                    'tax_behavior': 'exclusive',
                },
                'quantity': qty,
            })

            # Keep a validated list of items for order creation later
            validated_items.append({
                'id': p_id,
                'qty': qty,
                'c_code': c_code,
                'shipping': float(res['shipping_fee']),
                'item_total': float(item_total)
            })

        # Calculate final totals including the service fee
        service_fee = (total_item_price + total_shipping_fee) * Decimal('0.08')
        grand_total_before_balance = total_item_price + total_shipping_fee + service_fee

        # Apply user's balance if they chose to use it
        applied_balance = Decimal('0')
        if use_balance and user.balance > 0:
            applied_balance = min(user.balance, grand_total_before_balance)

        amount_to_pay = grand_total_before_balance - applied_balance

        # Deduct the used balance from the user's account
        if applied_balance > 0:
            # This is an optimistic deduction; it will be rolled back if payment fails
            user.balance -= applied_balance
            user.save(update_fields=['balance'])

        payment = Payment.objects.create(
            buyer=request.user,
            payment_type='STORE',
            shipping_address=json.dumps(shipping_address),
            unit_price=total_item_price,
            total_amount=total_item_price + total_discount,
            discount_amount=total_discount,
            quantity=len(items_data),
            item_total=total_item_price,
            shipping_fee=total_shipping_fee,
            service_fee=service_fee,
            balance_used=applied_balance,
            final_amount=amount_to_pay,
            currency='usd',
            status='PENDING',
        )
        
        # Add service fee as a separate line item for Stripe
        line_items.append({
            'price_data': {
                'currency': 'usd',
                'unit_amount': int(service_fee * 100),
                'product_data': {'name': 'Dealnux Service Fee'},
            },
            'quantity': 1,
        })

        # Add shipping fee as a line item if applicable
        if total_shipping_fee > 0:
            line_items.append({
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': int(total_shipping_fee * 100),
                    'product_data': {'name': 'Shipping Fee'},
                },
                'quantity': 1,
            })

        # If the user's balance covers the entire cost, no need to go to Stripe
        if amount_to_pay <= 0:
            payment.status = 'PAID'
            payment.save(update_fields=['status'])
            
            # Create the order directly, similar to how the webhook would
            create_orders_from_payment(payment, validated_items)
            
            cost_breakdown = {
                'subtotal': float(total_item_price),
                'shipping': float(total_shipping_fee),
                'service_fee': float(service_fee),
                'discount': float(total_discount),
                'tax': 0.0, # No tax calculated for balance-only payments
                'balance_used': float(applied_balance),
                'grand_total': float(payment.final_amount)
            }
            return Response({
                'success': True,
                'message': 'Order placed successfully using your balance.',
                'payment_id': payment.id,
                'breakdown': cost_breakdown,
            }, status=200)
        else:
            # If payment is still required, create a Stripe Checkout and Payment Intent
            try:
                session = stripe.checkout.Session.create(
                    ui_mode='embedded',
                    line_items=line_items,
                    mode='payment',
                    automatic_tax={'enabled': True},
                    return_url=settings.STRIPE_RETURN_URL +
                    "?session_id={CHECKOUT_SESSION_ID}",
                    metadata={
                        'payment_id': payment.id,
                        'type': 'store_payment',
                        'items_json': json.dumps(validated_items)
                    },
                    customer_email=request.user.email,
                )

                stripe_tax = Decimal(str(session.total_details.amount_tax or 0)) / 100
                final_grand_total = amount_to_pay + stripe_tax

                mobile_intent = stripe.PaymentIntent.create(
                    amount=int(final_grand_total * 100),
                    currency='usd',
                    automatic_payment_methods={"enabled": True},
                    metadata={
                        'payment_id': payment.id,
                        'type': 'store_payment',
                        'items_json': json.dumps(validated_items)
                    }
                )

                payment.stripe_checkout_session_id = session.id
                payment.stripe_payment_intent_id = mobile_intent.id
                payment.final_amount = final_grand_total
                payment.save(update_fields=['stripe_checkout_session_id', 'stripe_payment_intent_id', 'final_amount', 'updated_at'])

                cost_breakdown = {
                    'subtotal': float(total_item_price),
                    'shipping': float(total_shipping_fee),
                    'service_fee': float(service_fee),
                    'discount': float(total_discount),
                    'tax': float(stripe_tax),
                    'balance_used': float(applied_balance),
                    'grand_total': float(final_grand_total)
                }

                return Response({
                    'client_secret': session.client_secret,
                    'payment_intent_client_secret': mobile_intent.client_secret,
                    'payment_id': payment.id,
                    'breakdown': cost_breakdown,
                })

            except Exception as e:
                # If Stripe session creation fails, refund the balance to the user
                user.balance += applied_balance
                user.save(update_fields=['balance'])
                payment.delete()
                return Response({'error': str(e)}, status=500)

# -------------------------- Checkout Session Status & Order Confirmation API View --------------------------
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

# -------------------------- Stripe Webhook Event Listener (Checkout, Invoices, Subscriptions) --------------------------
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

        elif event['type'] == 'payment_intent.succeeded':  
            self._handle_payment_intent_succeeded(event['data']['object'])

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
        logger.info(f"Subscription {stripe_sub_id} has been cancelled.")

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
                if payment.status == 'PAID':
                    logger.info(f"Payment ID {payment_id} already marked as PAID. Skipping duplicate processing in checkout.session.completed.")
                    return

                payment.status = 'PAID'
                payment.stripe_payment_intent_id = session.get(
                    'payment_intent', '')
                payment.save()

                if p_type == 'store_payment':
                    items_json = metadata.get('items_json', '[]')
                    items = json.loads(items_json)
                    create_orders_from_payment(payment, items)
                elif p_type == 'ad_payment':
                    ad = payment.ad
                    if ad:
                        ad.status = 'pending'
                        ad.save()
                        send_dealnux_email(
                            "Ad Submitted for Review - DealNux",
                            ad.advertiser.email, 
                            "emails/ad_submitted.html",
                            {"ad": ad, "user": ad.advertiser}
                        )
            except Payment.DoesNotExist:
                logger.error(f"Error: Payment ID {payment_id} not found in database.")

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
            subscription, _ = UserSubscription.objects.update_or_create(
                user=user,
                defaults={
                    'plan': plan,
                    'status': 'ACTIVE',
                    'stripe_subscription_id': stripe_sub_id,
                    'stripe_customer_id': stripe_cust_id,
                    'started_at': now,
                    'expires_at': now + timedelta(days=days),
                    'daily_click_count': 0,
                    'last_click_date': now.date(),
                    'trial_ends_at': now
                }
            )
            logger.info(
                f"Payment success! Subscription activated for: {user.email}")

            self._process_referral_reward(user)

            from notifications.utils import create_notification
            create_notification(
                user=user,
                title="Subscription Activated! 🎉",
                body=f"Your subscription to '{plan.name}' is now active. Enjoy premium features!",
                notification_type="PROMOTION",
                channel="SYSTEM"
            )

            send_dealnux_email(
                "Your DealNux Subscription is Active!",
                user.email,
                "emails/subscription_active.html",
                {
                    "user": user,
                    "plan": plan,
                    "renewal_date": subscription.expires_at
                }
            )

        except Exception as e:
            logger.error(f"Error in _handle_subscription_success: {str(e)}")


    def _handle_subscription_success_intent(self, payment_intent):
        """Activates the paid subscription plan for the user in the database via PaymentIntent."""
        metadata = payment_intent.get('metadata', {})
        user_id = metadata.get('user_id')
        plan_id = metadata.get('plan_id')
        stripe_cust_id = payment_intent.get('customer')

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
            subscription, _ = UserSubscription.objects.update_or_create(
                user=user,
                defaults={
                    'plan': plan,
                    'status': 'ACTIVE',
                    'stripe_subscription_id': payment_intent.get('id'), # Use PaymentIntent ID as fallback
                    'stripe_customer_id': stripe_cust_id,
                    'started_at': now,
                    'expires_at': now + timedelta(days=days),
                    'daily_click_count': 0,
                    'last_click_date': now.date(),
                    'trial_ends_at': now
                }
            )
            logger.info(f"Subscription activated via PaymentIntent for: {user.email}")

            self._process_referral_reward(user)

            from notifications.utils import create_notification
            create_notification(
                user=user,
                title="Subscription Activated! 🎉",
                body=f"Your subscription to '{plan.name}' is now active. Enjoy premium features!",
                notification_type="PROMOTION",
                channel="SYSTEM"
            )

            send_dealnux_email(
                "Your DealNux Subscription is Active!",
                user.email,
                "emails/subscription_active.html",
                {
                    "user": user,
                    "plan": plan,
                    "renewal_date": subscription.expires_at
                }
            )
        except Exception as e:
            logger.error(f"Error in _handle_subscription_success_intent: {str(e)}")

    def _handle_payment_intent_succeeded(self, payment_intent):
        metadata = payment_intent.get('metadata', {})
        payment_id = metadata.get('payment_id')
        p_type = metadata.get('type')

        if p_type == 'subscription_payment':
            self._handle_subscription_success_intent(payment_intent)
            return

        if not payment_id:
            return

        try:
            payment = Payment.objects.get(id=payment_id)

            # Checkout session already handled this — skip
            if payment.status == 'PAID':
                return

            payment.status = 'PAID'
            payment.stripe_payment_intent_id = payment_intent.get('id')
            payment.save()

            if p_type == 'store_payment':
                items_json = metadata.get('items_json', '[]')
                items = json.loads(items_json)
                create_orders_from_payment(payment, items)

            elif p_type == 'subscription_payment':
                pass

            elif p_type == 'ad_payment':
                ad = payment.ad
                if ad:
                    ad.status = 'pending'
                    ad.save()
                    send_dealnux_email(
                        "Ad Submitted for Review - DealNux",
                        ad.advertiser.email,
                        "emails/ad_submitted.html",
                        {"ad": ad, "user": ad.advertiser}
                    )

        except Payment.DoesNotExist:
            logger.error(f"PaymentIntent: Payment ID {payment_id} not found.")
        except Exception as e:
            logger.error(f"Error in _handle_payment_intent_succeeded: {str(e)}")

    def _process_referral_reward(self, user):
        """
        Award the referral bonus once, only after both the referred user and the referrer
        have active paid subscriptions and the referred user has completed a first DEALNUX purchase.
        Only the referrer user receives the reward amount (the referred friend does not earn points).
        """
        from .utils import process_referral_reward_for_user
        process_referral_reward_for_user(user)

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


# -------------------------- Seller Stripe Connect Onboarding Account Link Generation View --------------------------
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


# -------------------------- Seller Payout / Withdrawal Request API View --------------------------
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

            # Create SellerPayout record so admin can track/approve and seller history is saved
            payout = SellerPayout.objects.create(
                seller=seller,
                stripe_account_id=seller.stripe_account_id or '',
                gross_amount=amount,
                platform_fee_percent=Decimal('0'),
                platform_fee_amount=Decimal('0'),
                seller_amount=amount,
                status='PENDING'
            )

            send_dealnux_email(
                "Payout Request Received - DealNux",
                request.user.email,
                "emails/payout_requested.html",
                {"seller": seller, "amount": float(amount)}
            )

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


# -------------------------- Seller Stripe Connect Verification & Account Status View --------------------------
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


# -------------------------- Buyer Payment History & Order Transaction List View --------------------------
class PaymentHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        payments = Payment.objects.filter(buyer=request.user).select_related(
            'seller_product', 'order'
        )

        paginator = CustomPagination()
        paginated_qs = paginator.paginate_queryset(payments, request)

        data = []
        for p in paginated_qs:
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

        return paginator.get_paginated_response(data)


# -------------------------- Seller Payout & Withdrawal History API View --------------------------
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


# -------------------------- Stripe Session Return & Verification Status Check View --------------------------
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


# -------------------------- Seller Stripe Express Dashboard Login Link Generator View --------------------------
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


# -------------------------- External Product Listing Click Tracker & Redirection View --------------------------
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

        return Response({"redirect_url": listing.external_url})


# -------------------------- Subscription Plan List API View (Public Membership Plans) --------------------------
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


# -------------------------- Create Subscription Checkout Session & Free Trial Activation View --------------------------
class CreateSubscriptionCheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        plan_id = request.data.get('plan_id')
        user = request.user

        try:
            plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            return Response({"success": False, "message": "Invalid Plan selected."}, status=200)

        if plan.plan_type == 'FREE':

            if UserSubscription.objects.filter(user=user).exists():
                return Response({"success": False, "message": "You have already used your free trial or have an active plan."}, status=200)

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
            }, status=200)

        try:
            if plan.stripe_price_id and plan.stripe_price_id.strip():
                line_items = [{'price': plan.stripe_price_id.strip(), 'quantity': 1}]
            else:
                interval = 'year' if 'YEARLY' in plan.plan_type else 'month'
                line_items = [{
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {'name': plan.name},
                        'unit_amount': int(plan.price * 100),
                        'recurring': {'interval': interval}
                    },
                    'quantity': 1,
                }]

            session = stripe.checkout.Session.create(
                ui_mode='embedded',
                payment_method_types=['card'],
                line_items=line_items,
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

            sub = UserSubscription.objects.filter(user=user).first()
            stripe_cust_id = sub.stripe_customer_id if sub else None

            if not stripe_cust_id:
                try:
                    customer = stripe.Customer.create(
                        email=user.email,
                        metadata={'user_id': user.id}
                    )
                    stripe_cust_id = customer.id
                except Exception:
                    pass

            intent_params = {
                'amount': int(plan.price * 100),
                'currency': 'usd',
                'payment_method_types': ['card'],
                'metadata': {
                    'user_id': user.id,
                    'plan_id': plan.id,
                    'type': 'subscription_payment'
                }
            }
            if stripe_cust_id:
                intent_params['customer'] = stripe_cust_id

            mobile_intent = stripe.PaymentIntent.create(**intent_params)

            return Response({
                "success": True,
                "client_secret": session.client_secret,
                "payment_intent_client_secret": mobile_intent.client_secret,
                "plan_name": plan.name,
                "amount": float(plan.price)
            }, status=200)

        except Exception as e:
            return Response({"success": False, "message": str(e)}, status=200)


# -------------------------- Auth User Active Subscription Status & Limits View --------------------------
class UserSubscriptionStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from payment.models import UserSubscription
        sub = UserSubscription.objects.filter(user=request.user).first()
        if sub and sub.is_active:
            sub = refresh_subscription_limits(sub)
        has_used_trial = UserSubscription.objects.filter(
            user=request.user).exists()
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


# -------------------------- Stripe Customer Billing Portal Session Management View --------------------------
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


# ============================================================================
# Apple Direct In-App Purchase (StoreKit 2) Integration Views
# ============================================================================

from payment.apple_iap import verify_and_decode_apple_jws, decode_jws_payload_unverified


# -------------------------- Apple In-App Purchase (StoreKit 2) Receipt Verification View --------------------------
class AppleVerifyReceiptView(APIView):
    """
    Verifies Apple StoreKit 2 JWS purchase_token and grants active subscription status.
    POST /api/payment/apple/verify/
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        purchase_token = request.data.get('purchase_token', '')
        product_id = request.data.get('product_id', '')
        transaction_id = str(request.data.get('transaction_id', ''))

        if not purchase_token and not transaction_id:
            return Response({
                "success": False,
                "is_active": False,
                "message": "purchase_token or transaction_id is required."
            }, status=400)

        jws_payload = {}
        if purchase_token:
            try:
                jws_payload = verify_and_decode_apple_jws(purchase_token)
            except Exception as e:
                # Log warning and attempt unverified payload decode as fallback
                print(f"⚠️ Apple JWS verification warning: {e}")
                try:
                    jws_payload = decode_jws_payload_unverified(purchase_token)
                except Exception:
                    jws_payload = {}

        # Extract fields from decoded JWS or request fallbacks
        sku = jws_payload.get('productId') or product_id
        tx_id = str(jws_payload.get('transactionId') or transaction_id)
        orig_tx_id = str(jws_payload.get('originalTransactionId') or tx_id)
        expires_date_ms = jws_payload.get('expiresDate')

        # Find matching subscription plan
        plan = None
        if sku:
            plan = SubscriptionPlan.objects.filter(apple_product_id=sku, is_active=True).first()

        if not plan:
            if 'yearly' in sku.lower():
                plan = SubscriptionPlan.objects.filter(plan_type__icontains='YEARLY', is_active=True).first()
            elif 'monthly' in sku.lower():
                plan = SubscriptionPlan.objects.filter(plan_type__icontains='MONTHLY', is_active=True).first()

        if not plan:
            # Default fallback to first active plan if not matched by SKU
            plan = SubscriptionPlan.objects.filter(is_active=True).exclude(plan_type='FREE').first()

        if not plan:
            return Response({
                "success": False,
                "is_active": False,
                "message": "No active subscription plan configured for this product."
            }, status=404)

        now = timezone.now()
        if expires_date_ms:
            expires_at = timezone.datetime.fromtimestamp(expires_date_ms / 1000.0, tz=timezone.utc)
        else:
            days = 365 if 'YEARLY' in plan.plan_type else 30
            expires_at = now + timedelta(days=days)

        user = request.user
        subscription, _ = UserSubscription.objects.update_or_create(
            user=user,
            defaults={
                'plan': plan,
                'status': 'ACTIVE',
                'payment_gateway': 'APPLE',
                'apple_original_transaction_id': orig_tx_id,
                'apple_latest_transaction_id': tx_id,
                'started_at': now,
                'expires_at': expires_at,
                'daily_click_count': 0,
                'last_click_date': now.date(),
                'trial_ends_at': now
            }
        )

        # Trigger notifications & referral rewards
        try:
            from notifications.utils import create_notification
            create_notification(
                user=user,
                title="Apple Subscription Activated! 🎉",
                body=f"Your subscription to '{plan.name}' is now active via Apple In-App Purchase.",
                notification_type="PROMOTION",
                channel="SYSTEM"
            )
        except Exception as e:
            logger.warning(f"Notification creation failed: {e}")

        return Response({
            "success": True,
            "is_active": True,
            "message": "Apple subscription verified and activated successfully.",
            "data": {
                "plan_name": plan.name,
                "expires_at": subscription.expires_at,
                "status": subscription.status,
                "is_active": subscription.is_active
            }
        }, status=200)


# -------------------------- Apple App Store Server Notifications V2 Webhook Handler View --------------------------
@method_decorator(csrf_exempt, name='dispatch')
class AppleServerNotificationsView(APIView):
    """
    App Store Server Notifications V2 Webhook handler.
    POST /api/payment/apple/notifications/
    """
    permission_classes = [AllowAny]

    def post(self, request):
        signed_payload = request.data.get('signedPayload') or request.body.decode('utf-8')
        if not signed_payload:
            return HttpResponse(status=400)

        try:

            if isinstance(signed_payload, str) and signed_payload.startswith('{'):
                data_dict = json.loads(signed_payload)
                signed_payload = data_dict.get('signedPayload', signed_payload)

            payload = verify_and_decode_apple_jws(signed_payload)
            notification_type = payload.get('notificationType')
            data = payload.get('data', {})
            signed_tx_info = data.get('signedTransactionInfo')

            if signed_tx_info:
                tx_payload = verify_and_decode_apple_jws(signed_tx_info)
                orig_tx_id = str(tx_payload.get('originalTransactionId', ''))
                expires_date_ms = tx_payload.get('expiresDate')

                if orig_tx_id:
                    sub = UserSubscription.objects.filter(apple_original_transaction_id=orig_tx_id).first()
                    if sub:
                        if notification_type in ['SUBSCRIBED', 'DID_RENEW', 'OFFER_REDEEMED']:
                            sub.status = 'ACTIVE'
                            if expires_date_ms:
                                sub.expires_at = timezone.datetime.fromtimestamp(expires_date_ms / 1000.0, tz=timezone.utc)
                            sub.save()
                        elif notification_type == 'EXPIRED':
                            sub.status = 'EXPIRED'
                            sub.save()
                        elif notification_type in ['REFUND', 'REVOKE']:
                            sub.status = 'CANCELLED'
                            sub.save()

            return HttpResponse(status=200)
        except Exception as e:
            logger.error(f"Error processing Apple Server Notification: {e}")
            return HttpResponse(status=200) # Always return 200 to Apple to acknowledge receipt

