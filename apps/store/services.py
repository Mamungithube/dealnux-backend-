import random
import string
import logging
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum, Avg, Count

import stripe
from config.email import send_dealnux_email
from payment.utils import process_referral_reward_for_user
from .models import Order, SellerProduct, ProductReview, SellerProfile, Dispute, SellerRequest

logger = logging.getLogger(__name__)


# ============================================================================
# Seller Profile & Dashboard Services
# ============================================================================

def get_seller_dashboard_overview_data(seller):
    """
    Computes dashboard overview statistics for a seller profile.
    """
    today = timezone.now()

    this_month_earned = Order.objects.filter(
        seller=seller, status='ACCEPTED',
        created_at__month=today.month, created_at__year=today.year
    ).aggregate(total=Sum('item_total'))['total'] or 0

    total_units = SellerProduct.objects.filter(
        seller=seller, status='APPROVED'
    ).aggregate(total=Sum('quantity'))['total'] or 0

    review_stats = ProductReview.objects.filter(product__seller=seller).aggregate(
        average_rating=Avg('rating'),
        total_reviews=Count('id')
    )

    return {
        "shop_name": seller.shop_name,
        "stats": {
            "total_products": SellerProduct.objects.filter(seller=seller).count(),
            "total_units_in_stock": total_units,
            "active_orders": Order.objects.filter(seller=seller, status__in=['PENDING', 'CONFIRMED', 'SHIPPED']).count(),
            "needs_action": Order.objects.filter(seller=seller, status='PENDING').count(),
            "this_month_earnings": float(this_month_earned),
            "total_earned": float(seller.total_earnings),
            "total_reviews": review_stats['total_reviews'],
            "average_rating": round(review_stats['average_rating'] or 0, 1),
        }
    }


def get_seller_shipping_settings(seller):
    """
    Returns structured dictionary of a seller's shipping settings.
    """
    return {
        "local_pickup": {
            "active": seller.local_pickup_active,
            "address_street": seller.pickup_address_street,
            "address_city": seller.pickup_address_city,
            "address_state": seller.pickup_address_state,
            "address_zip": seller.pickup_address_zip,
            "hours_start": seller.pickup_hours_start.strftime("%H:%M:%S") if seller.pickup_hours_start else None,
            "hours_end": seller.pickup_hours_end.strftime("%H:%M:%S") if seller.pickup_hours_end else None,
            "available_days": seller.pickup_available_days
        },
        "local_delivery": {
            "active": seller.local_delivery_active,
            "radius": seller.delivery_radius,
            "fee": float(seller.delivery_fee),
            "timeframe": seller.delivery_timeframe
        },
        "standard_shipping": {
            "active": seller.standard_shipping_active,
            "processing_time": seller.order_processing_time,
            "preferred_couriers": seller.preferred_couriers
        }
    }


def update_seller_shipping_settings(seller, data):
    """
    Updates seller shipping configuration from validated/received payload.
    """
    pickup_data = data.get('local_pickup', {})
    if pickup_data:
        seller.local_pickup_active = pickup_data.get('active', seller.local_pickup_active)
        seller.pickup_address_street = pickup_data.get('address_street', seller.pickup_address_street)
        seller.pickup_address_city = pickup_data.get('address_city', seller.pickup_address_city)
        seller.pickup_address_state = pickup_data.get('address_state', seller.pickup_address_state)
        seller.pickup_address_zip = pickup_data.get('address_zip', seller.pickup_address_zip)
        seller.pickup_hours_start = pickup_data.get('hours_start', seller.pickup_hours_start)
        seller.pickup_hours_end = pickup_data.get('hours_end', seller.pickup_hours_end)
        seller.pickup_available_days = pickup_data.get('available_days', seller.pickup_available_days)

    delivery_data = data.get('local_delivery', {})
    if delivery_data:
        seller.local_delivery_active = delivery_data.get('active', seller.local_delivery_active)
        seller.delivery_radius = delivery_data.get('radius', seller.delivery_radius)
        seller.delivery_fee = delivery_data.get('fee', seller.delivery_fee)
        seller.delivery_timeframe = delivery_data.get('timeframe', seller.delivery_timeframe)

    standard_data = data.get('standard_shipping', {})
    if standard_data:
        seller.standard_shipping_active = standard_data.get('active', seller.standard_shipping_active)
        seller.order_processing_time = standard_data.get('processing_time', seller.order_processing_time)
        seller.preferred_couriers = standard_data.get('preferred_couriers', seller.preferred_couriers)

    seller.save()
    return seller


# ============================================================================
# Seller Onboarding & Application Services
# ============================================================================

def approve_seller_request(seller_request: SellerRequest):
    """
    Business logic for approving an 11-step seller application:
    - Atomically updates status to APPROVED
    - Creates or activates the user's SellerProfile
    - Dispatches approval email
    """
    with transaction.atomic():
        seller_request.status = 'APPROVED'
        seller_request.reviewed_at = timezone.now()
        seller_request.save(update_fields=['status', 'reviewed_at'])

        profile, _ = SellerProfile.objects.get_or_create(
            user=seller_request.user,
            defaults={
                'shop_name': seller_request.trade_name,
                'shop_description': f"Primary Category: {seller_request.categories.first().name if seller_request.categories.exists() else 'N/A'}",
                'phone_number': seller_request.contact_phone,
                'legal_full_name': seller_request.contact_full_name,
                'business_address': seller_request.experience_description,
                'is_active': True
            }
        )
        if not profile.is_active:
            profile.is_active = True
            profile.save(update_fields=['is_active'])

    send_dealnux_email(
        "Marketplace Approved - DealNux",
        seller_request.user.email,
        "emails/seller_approved.html",
        {
            "user": seller_request.user,
            "shop_name": seller_request.trade_name
        }
    )
    return seller_request


def reject_seller_request(seller_request: SellerRequest, note: str):
    """
    Business logic for rejecting a seller application with reason note.
    """
    seller_request.status = 'REJECTED'
    seller_request.admin_note = note
    seller_request.reviewed_at = timezone.now()
    seller_request.save(update_fields=['status', 'admin_note', 'reviewed_at'])

    send_dealnux_email(
        "Application Update - DealNux",
        seller_request.user.email,
        "emails/seller_rejected.html",
        {
            "user": seller_request.user,
            "admin_note": note
        }
    )
    return seller_request


# ============================================================================
# Order Fulfillment & Refund Services
# ============================================================================

def create_store_order(serializer, user):
    """
    Business logic for creating a marketplace order:
    - Creates Order record
    - Credits seller's pending wallet
    - Triggers referral reward check for buyer
    - Sends buyer & seller email notifications
    """
    with transaction.atomic():
        order = serializer.save()

        seller_profile = order.seller
        amount_for_seller = order.item_total + order.shipping_fee
        seller_profile.pending_balance += amount_for_seller
        seller_profile.save(update_fields=['pending_balance'])

        process_referral_reward_for_user(user)

    try:
        send_dealnux_email(
            "Order Confirmed - DealNux",
            order.buyer.email,
            "emails/order_placed_buyer.html",
            {"order": order, "user": order.buyer}
        )
        send_dealnux_email(
            "New Order Received - DealNux",
            order.seller.user.email,
            "emails/order_placed_seller.html",
            {"order": order, "seller": order.seller}
        )
    except Exception as e:
        logger.error(f"Order email notification error: {str(e)}")

    return order


def update_order_tracking(order: Order, tracking_no: str, courier_name: str = None):
    """
    Business logic to record tracking and mark order as SHIPPED.
    """
    order.tracking_number = tracking_no
    if courier_name:
        order.courier_name = courier_name
    order.status = 'SHIPPED'
    order.save(update_fields=['tracking_number', 'courier_name', 'status', 'updated_at'])

    send_dealnux_email(
        "Your Order Has Been Shipped - DealNux",
        order.buyer.email,
        "emails/order_shipped.html",
        {"order": order, "tracking_number": tracking_no, "courier": courier_name}
    )
    return order


def confirm_order_by_buyer(order: Order):
    """
    Business logic when buyer confirms receiving product:
    - Sets order status to CONFIRMED
    - Releases funds: transfers money from seller's pending to available & total earnings
    - Creates PayoutRecord
    - Triggers Stripe Transfer to seller's Stripe Connect account (if connected)
    - Dispatches confirmation email
    """
    from payment.models import PayoutRecord

    with transaction.atomic():
        order.status = 'CONFIRMED'
        order.is_accepted_by_buyer = True
        order.accepted_at = timezone.now()
        order.save(update_fields=['status', 'is_accepted_by_buyer', 'accepted_at', 'updated_at'])

        seller_profile = order.seller
        amount = order.item_total + order.shipping_fee
        seller_profile.pending_balance -= amount
        seller_profile.available_balance += amount
        seller_profile.total_earnings += amount
        seller_profile.save(update_fields=['pending_balance', 'available_balance', 'total_earnings'])

        p_id = "PAY-" + "".join(random.choices(string.digits, k=4))
        PayoutRecord.objects.create(
            seller=seller_profile, payout_id=p_id,
            amount=amount, method="Stripe Transfer", status="Paid"
        )

        if seller_profile.stripe_account_id and seller_profile.stripe_onboarding_completed:
            try:
                stripe.api_key = settings.STRIPE_SECRET_KEY
                stripe.Transfer.create(
                    amount=int(amount * 100),
                    currency=order.currency.lower(),
                    destination=seller_profile.stripe_account_id,
                    transfer_group=f"ORDER_{order.order_number}",
                )
            except Exception as e:
                logger.error(f"Stripe Transfer Error on order {order.order_number}: {str(e)}")

    try:
        send_dealnux_email(
            "Order Confirmed by Buyer - DealNux",
            order.seller.user.email,
            "emails/order_confirmed_seller.html",
            {"order": order, "seller": order.seller}
        )
    except Exception as e:
        logger.error(f"Buyer confirm email error: {e}")

    return order


def process_order_refund(order: Order, fault: str) -> Decimal:
    """
    Core business logic to process refund for an order:
    - Sets status to REFUNDED, records fault party
    - Deducts money from seller pending balance
    - Calculates buyer refund amount (SELLER fault = full, BUYER fault = item price only)
    - Triggers Stripe refund & reverses any Stripe transfers
    - Refunds user wallet balance if applicable
    - Syncs payment record status
    """
    with transaction.atomic():
        order.status = 'REFUNDED'
        order.fault_party = fault

        seller_profile = order.seller
        amount_to_deduct = order.item_total + order.shipping_fee
        seller_profile.pending_balance -= amount_to_deduct
        seller_profile.save(update_fields=['pending_balance'])

        if fault == 'SELLER':
            refund_amount = order.total_price
        else:
            refund_amount = order.item_total

        order.refund_amount = refund_amount
        order.save(update_fields=['status', 'fault_party', 'refund_amount', 'updated_at'])

        payment = getattr(order, 'payment', None)
        if payment:
            payment.status = 'REFUNDED'
            payment.save(update_fields=['status'])

            stripe_intent_id = payment.stripe_payment_intent_id
            refunded_from_stripe = Decimal('0')

            if stripe_intent_id:
                try:
                    stripe.api_key = settings.STRIPE_SECRET_KEY
                    stripe_refund_amount = min(refund_amount, payment.final_amount)
                    if stripe_refund_amount > 0:
                        stripe.Refund.create(
                            payment_intent=stripe_intent_id,
                            amount=int(stripe_refund_amount * 100)
                        )
                        refunded_from_stripe = stripe_refund_amount

                        try:
                            transfers = stripe.Transfer.list(transfer_group=f"ORDER_{order.order_number}")
                            for transfer in transfers.auto_paging_iter():
                                stripe.Transfer.create_reversal(
                                    transfer.id,
                                    amount=min(int(refund_amount * 100), transfer.amount)
                                )
                        except Exception as trans_err:
                            logger.error(f"Failed to reverse Stripe Transfer: {str(trans_err)}")

                except Exception as stripe_err:
                    logger.error(f"Stripe Refund failed: {str(stripe_err)}")

            remaining_refund = refund_amount - refunded_from_stripe
            if remaining_refund > 0:
                buyer = order.buyer
                buyer.balance += remaining_refund
                buyer.save(update_fields=['balance'])
        else:
            buyer = order.buyer
            buyer.balance += refund_amount
            buyer.save(update_fields=['balance'])

    return refund_amount


# ============================================================================
# Dispute Management Services
# ============================================================================

def open_order_dispute(order: Order, reason: str, description: str, evidence_image=None):
    """
    Business logic for opening a customer dispute on an order.
    """
    with transaction.atomic():
        order.status = 'DISPUTED'
        order.save(update_fields=['status', 'updated_at'])

        dispute = Dispute.objects.create(
            order=order,
            reason=reason,
            description=description,
            evidence_image=evidence_image
        )
    return dispute


def resolve_order_dispute(order: Order, decision: str, fault: str = None):
    """
    Business logic for resolving an order dispute:
    - If REJECT: marks dispute REJECTED, reverts order to SHIPPED
    - If RESOLVE/APPROVE: marks dispute RESOLVED, runs process_order_refund
    """
    with transaction.atomic():
        dispute = order.dispute

        if decision == 'REJECT':
            dispute.status = 'REJECTED'
            order.status = 'SHIPPED'
            dispute.save(update_fields=['status', 'updated_at'])
            order.save(update_fields=['status', 'updated_at'])
            return None

        dispute.status = 'RESOLVED'
        dispute.save(update_fields=['status', 'updated_at'])
        refund_amount = process_order_refund(order, fault)
        return refund_amount
