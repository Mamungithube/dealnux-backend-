# store/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver

from custom_ads.models import AdvertiserRequest
from .models import SellerRequest
from custom_ads.utils import send_dealnux_email
from .models import Order

@receiver(post_save, sender=SellerRequest)
def handle_seller_request_email(sender, instance, created, **kwargs):
    if created:
        send_dealnux_email(
            "Application Pending - DealNux Seller",
            instance.user.email,
            "emails/seller_pending.html",
            {"user": instance.user, "shop_name": instance.trade_name}
        )
        send_dealnux_email(
            "ACTION REQUIRED: New Seller Application",
            "info@dealnux.shop",
            "emails/admin_alert.html",
            {"seller_name": instance.contact_full_name}
        )



from django.db.models.signals import pre_save
from notifications.utils import send_order_notification

@receiver(pre_save, sender=Order)
def track_order_status_change(sender, instance, **kwargs):
    if instance.id:
        try:
            old_order = Order.objects.only('status').get(id=instance.id)
            instance._old_status = old_order.status
        except Order.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=Order)
def handle_order_notification(sender, instance, created, **kwargs):
    if created:
        send_dealnux_email(
            "Order Confirmed - #" + instance.order_number,
            instance.buyer.email,
            "emails/order_buyer.html",
            {"order": instance}
        )
        send_dealnux_email(
            "New Order Received - DealNux",
            instance.seller.user.email,
            "emails/order_seller.html",
            {"order": instance}
        )
        # Send push/in-app notification on placed order
        send_order_notification(instance.buyer, instance, 'Placed')
    else:
        old_status = getattr(instance, '_old_status', None)
        new_status = instance.status
        if old_status != new_status:
            status_labels = {
                'PENDING': 'Pending',
                'ACCEPTED': 'Accepted',
                'PROCESSING': 'Processing',
                'SHIPPED': 'Shipped',
                'DELIVERED': 'Delivered',
                'CONFIRMED': 'Confirmed',
                'CANCELLED': 'Cancelled',
                'REFUNDED': 'Refunded',
                'OUT_FOR_DELIVERY': 'Out for delivery',
            }
            label = status_labels.get(new_status, new_status.title())
            send_order_notification(instance.buyer, instance, label)



@receiver(post_save, sender=AdvertiserRequest)
def ad_application_notification(sender, instance, created, **kwargs):
    if created:
        send_dealnux_email(
            "Ad Application Status - Pending",
            instance.user.email,
            "emails/ad_pending.html",
            {"user": instance.user}
        )