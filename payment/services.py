from decimal import Decimal
from django.db import transaction
import logging

from store.models import Order, SellerProduct
from api_integration.models import CartItem
from .models import Payment
from .utils import process_referral_reward_for_user

logger = logging.getLogger(__name__)


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
                seller_product.save()

                # Update seller's pending balance
                seller = seller_product.seller
                amount_for_seller = Decimal(str(item_data['item_total'])) + Decimal(str(item_data['shipping']))
                seller.pending_balance += amount_for_seller
                seller.total_orders += 1
                seller.save()

            except Exception as e:
                logger.error(f"Error processing item in payment service: {str(e)}")

        # Link the first created order to the payment record
        if first_order:
            payment.order = first_order
            payment.save(update_fields=['order'])

        CartItem.objects.filter(user=buyer).delete()
        logger.info(f"✅ Cart cleared for user: {buyer.email}")

        process_referral_reward_for_user(buyer)