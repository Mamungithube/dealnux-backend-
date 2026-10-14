import json
import logging
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.db.models import Q
import stripe

from store.models import Order, SellerProduct, Coupon
from api_integration.models import CartItem
from .models import Payment, SellerPayout, SubscriptionPlan, UserSubscription
from .utils import process_referral_reward_for_user

logger = logging.getLogger(__name__)


# ============================================================================
# Order Amount & Coupon Calculation
# ============================================================================

def calculate_order_amounts(seller_product: SellerProduct, quantity: int, coupon_code: str = '') -> dict:
    """
    Calculates subtotal, discounts, shipping, service fees and final amounts for a product purchase.
    """
    unit_price = Decimal(str(seller_product.price))
    subtotal = unit_price * Decimal(str(quantity))
    discount = Decimal('0')

    if coupon_code:
        c_code = str(coupon_code).upper().strip()
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
    shipping = seller_product.shipping_cost if not seller_product.free_shipping else Decimal('0')

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
# Checkout Session Services
# ============================================================================

def create_orders_from_payment(payment: Payment, items: list):
    """
    Creates one or more orders from a successful payment object.
    This service is used by both zero-payment (balance) checkouts and Stripe webhooks.
    """
    buyer = payment.buyer
    with transaction.atomic():
        first_order = None
        for item_data in items:
            try:
                seller_product = SellerProduct.objects.get(id=item_data['id'])

                order = Order.objects.create(
                    buyer=buyer,
                    seller=seller_product.seller,
                    seller_product=seller_product,
                    listing=seller_product.linked_listing,
                    quantity=item_data['qty'],
                    unit_price=seller_product.price,
                    item_total=Decimal(str(item_data['item_total'])),
                    shipping_fee=Decimal(str(item_data['shipping'])),
                    service_fee=(Decimal(str(item_data['item_total'])) + Decimal(str(item_data['shipping']))) * Decimal('0.08'),
                    total_price=payment.final_amount + payment.balance_used,
                    currency=payment.currency,
                    shipping_address=payment.shipping_address,
                    status='PENDING',
                )

                if not first_order:
                    first_order = order

                # Decrease stock
                seller_product.quantity -= item_data['qty']
                seller_product.save(update_fields=['quantity'])

                # Update seller's pending balance
                seller = seller_product.seller
                amount_for_seller = Decimal(str(item_data['item_total'])) + Decimal(str(item_data['shipping']))
                seller.pending_balance += amount_for_seller
                seller.total_orders += 1
                seller.save(update_fields=['pending_balance', 'total_orders'])

            except Exception as e:
                logger.error(f"Error processing item in payment service: {str(e)}")

        # Link the first created order to the payment record
        if first_order:
            payment.order = first_order
            payment.save(update_fields=['order'])

        CartItem.objects.filter(user=buyer).delete()
        logger.info(f"✅ Cart cleared for user: {buyer.email}")

        process_referral_reward_for_user(buyer)


def create_product_checkout_session(user, items_data: list, shipping_address: dict, use_balance: bool = False, root_coupon_code: str = '', base_url: str = '') -> dict:
    """
    Business logic for product cart checkout:
    - Validates products and computes item & shipping totals
    - Applies user wallet balance if requested
    - If balance covers 100%, creates Payment + Orders directly without Stripe
    - Otherwise, creates Stripe Checkout Session & Payment Intent
    """
    stripe.api_key = settings.STRIPE_SECRET_KEY

    total_item_price = Decimal('0')
    total_shipping_fee = Decimal('0')
    total_discount = Decimal('0')
    line_items = []
    validated_items = []

    for item in items_data:
        p_id = item.get('seller_product')
        qty = int(item.get('quantity', 1))
        c_code = (
            item.get('coupon_code')
            or item.get('couponCode')
            or item.get('coupon')
            or root_coupon_code
        )

        product = SellerProduct.objects.get(id=p_id, status='APPROVED')
        res = calculate_order_amounts(product, qty, c_code)
        item_total = res['item_total']
        discount_amt = res['discount_amount']

        total_item_price += item_total
        total_shipping_fee += res['shipping_fee']
        total_discount += discount_amt

        image_urls = []
        if product.main_image:
            image_url = product.main_image.url
            if base_url and not image_url.startswith('http'):
                image_url = f"{base_url.rstrip('/')}{image_url}"
            image_urls.append(image_url)

        line_items.append({
            'price_data': {
                'currency': 'usd',
                'unit_amount': int((item_total / qty) * 100),
                'product_data': {
                    'name': product.title,
                    'images': image_urls,
                },
                'tax_behavior': 'exclusive',
            },
            'quantity': qty,
        })

        validated_items.append({
            'id': p_id,
            'qty': qty,
            'c_code': c_code,
            'shipping': float(res['shipping_fee']),
            'item_total': float(item_total)
        })

    service_fee = (total_item_price + total_shipping_fee) * Decimal('0.08')
    grand_total_before_balance = total_item_price + total_shipping_fee + service_fee

    applied_balance = Decimal('0')
    if use_balance and user.balance > 0:
        applied_balance = min(user.balance, grand_total_before_balance)

    amount_to_pay = grand_total_before_balance - applied_balance

    if applied_balance > 0:
        user.balance -= applied_balance
        user.save(update_fields=['balance'])

    payment = Payment.objects.create(
        buyer=user,
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

    line_items.append({
        'price_data': {
            'currency': 'usd',
            'unit_amount': int(service_fee * 100),
            'product_data': {'name': 'Dealnux Service Fee'},
        },
        'quantity': 1,
    })

    if total_shipping_fee > 0:
        line_items.append({
            'price_data': {
                'currency': 'usd',
                'unit_amount': int(total_shipping_fee * 100),
                'product_data': {'name': 'Shipping Fee'},
            },
            'quantity': 1,
        })

    # Zero-amount checkout via balance
    if amount_to_pay <= 0:
        payment.status = 'PAID'
        payment.save(update_fields=['status'])
        create_orders_from_payment(payment, validated_items)

        cost_breakdown = {
            'subtotal': float(total_item_price),
            'shipping': float(total_shipping_fee),
            'service_fee': float(service_fee),
            'discount': float(total_discount),
            'tax': 0.0,
            'balance_used': float(applied_balance),
            'grand_total': float(payment.final_amount)
        }
        return {
            'is_zero_payment': True,
            'payment_id': payment.id,
            'breakdown': cost_breakdown,
        }

    # Stripe checkout session
    session = stripe.checkout.Session.create(
        ui_mode='embedded',
        line_items=line_items,
        mode='payment',
        automatic_tax={'enabled': True},
        return_url=settings.STRIPE_RETURN_URL + "?session_id={CHECKOUT_SESSION_ID}",
        metadata={
            'payment_id': payment.id,
            'type': 'store_payment',
            'items_json': json.dumps(validated_items)
        },
        customer_email=user.email,
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
    payment.save(update_fields=['stripe_checkout_session_id', 'stripe_payment_intent_id'])

    cost_breakdown = {
        'subtotal': float(total_item_price),
        'shipping': float(total_shipping_fee),
        'service_fee': float(service_fee),
        'discount': float(total_discount),
        'tax': float(stripe_tax),
        'balance_used': float(applied_balance),
        'grand_total': float(final_grand_total)
    }

    return {
        'is_zero_payment': False,
        'clientSecret': session.client_secret,
        'payment_intent_client_secret': mobile_intent.client_secret,
        'session_id': session.id,
        'payment_id': payment.id,
        'breakdown': cost_breakdown,
    }


def create_subscription_checkout_session(user, plan_id: int, billing_cycle: str = 'MONTHLY') -> dict:
    """
    Business logic for creating a recurring subscription checkout session via Stripe.
    """
    stripe.api_key = settings.STRIPE_SECRET_KEY
    plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)

    price = plan.price_annual if billing_cycle.upper() == 'YEARLY' else plan.price_monthly

    payment = Payment.objects.create(
        buyer=user,
        payment_type='SUBSCRIPTION',
        subscription_plan=plan,
        final_amount=price,
        currency='usd',
        status='PENDING',
    )

    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'unit_amount': int(price * 100),
                'recurring': {
                    'interval': 'year' if billing_cycle.upper() == 'YEARLY' else 'month',
                },
                'product_data': {
                    'name': f"Dealnux {plan.name} Subscription",
                    'description': plan.description,
                },
            },
            'quantity': 1,
        }],
        mode='subscription',
        success_url=settings.STRIPE_SUCCESS_URL + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=settings.STRIPE_CANCEL_URL,
        customer_email=user.email,
        metadata={
            'user_id': user.id,
            'plan_id': plan.id,
            'payment_id': payment.id,
            'type': 'subscription_checkout'
        }
    )

    payment.stripe_checkout_session_id = session.id
    payment.save(update_fields=['stripe_checkout_session_id'])

    return {
        'session_id': session.id,
        'checkout_url': session.url,
        'payment_id': payment.id
    }


def cancel_user_subscription(user) -> dict:
    """
    Business logic for cancelling a user's active subscription.
    """
    stripe.api_key = settings.STRIPE_SECRET_KEY
    active_sub = UserSubscription.objects.filter(user=user, is_active=True).first()
    if not active_sub:
        raise ValueError("No active subscription found.")

    if active_sub.stripe_subscription_id:
        try:
            stripe.Subscription.delete(active_sub.stripe_subscription_id)
        except Exception as e:
            logger.error(f"Error cancelling stripe subscription: {e}")

    active_sub.is_active = False
    active_sub.save(update_fields=['is_active'])

    return {'message': 'Subscription cancelled successfully.'}


# ============================================================================
# Seller Payout Service
# ============================================================================

def process_seller_payout_request(seller, amount: Decimal, method: str = 'Stripe Transfer') -> SellerPayout:
    """
    Business logic for seller payout request:
    - Validates seller available balance
    - Atomically creates SellerPayout record and deducts available balance
    """
    with transaction.atomic():
        if seller.available_balance < amount:
            raise ValueError("Insufficient available balance.")

        platform_fee = amount * Decimal('0.05')
        net_amount = amount - platform_fee

        payout = SellerPayout.objects.create(
            seller=seller,
            amount=amount,
            platform_fee_amount=platform_fee,
            net_amount=net_amount,
            payout_method=method,
            status='PENDING'
        )

        seller.available_balance -= amount
        seller.save(update_fields=['available_balance'])

    return payout