# store/tasks.py

from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from django.conf import settings
from .models import Order
from payment.models import PayoutRecord
import stripe
import logging
stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)

@shared_task
def auto_accept_shipped_orders():
    """
    যে অর্ডারগুলো SHIPPED অবস্থায় ৭ দিন পার হয়েছে, সেগুলোকে অটো DELIVERED/ACCEPTED করবে।
    """
    # বর্তমানে আমরা টেস্ট করার জন্য সময়টা কমিয়েও দেখতে পারি
    threshold_days = 7 
    cutoff_time = timezone.now() - timedelta(days=threshold_days)
    
    # টার্গেট অর্ডারগুলো খুঁজে বের করা
    orders_to_release = Order.objects.filter(
        status='SHIPPED',
        updated_at__lte=cutoff_time,
        is_accepted_by_buyer=False
    )
    
    count = 0
    for order in orders_to_release:
        try:
            with transaction.atomic():
                # ১. স্ট্যাটাস আপডেট
                order.status = 'DELIVERED'
                order.is_accepted_by_buyer = True
                order.accepted_at = timezone.now()
                order.save()

                # ২. ওয়ালেট ট্রান্সফার
                seller = order.seller
                amount = order.item_total + order.shipping_fee
                seller.pending_balance -= amount
                seller.available_balance += amount
                seller.total_earnings += amount
                seller.save()

                # ৩. পayout রেকর্ড তৈরি (টেবিলের ডাটার জন্য)
                import uuid
                PayoutRecord.objects.create(
                    seller=seller,
                    payout_id=f"AUTO-{uuid.uuid4().hex[:4].upper()}",
                    amount=amount,
                    method="Auto Release",
                    status="Paid"
                )

                # ৪. রিয়েল স্ট্রাইপ ট্রান্সফার (সেলার কানেক্টেড থাকলে)
                if seller.stripe_account_id and seller.stripe_onboarding_completed:
                    stripe.Transfer.create(
                        amount=int(amount * 100),
                        currency=order.currency.lower(),
                        destination=seller.stripe_account_id,
                        transfer_group=f"ORDER_{order.order_number}",
                    )
                
                count += 1
                logger.info(f"Auto-accepted Order: {order.order_number}")
        except Exception as e:
            logger.error(f"Error auto-accepting order {order.id}: {str(e)}")

    return f"Successfully auto-accepted {count} orders."