from .firebase_utils import send_push_notification
from .models import Notification, NotificationPreference


def create_notification(user, title, body, notification_type, channel='SYSTEM', recipient_type='USER',
                       image_url=None, cta_text='', cta_link='', scheduled_at=None, is_sent=True):
    if not user:
        return None

    prefs = NotificationPreference.get_for_user(user)
    category_enabled = True
    if notification_type in {'PRICE_DROP', 'TARGET_PRICE_REACHED', 'NEW_LOWEST_PRICE', 'BACK_IN_STOCK',
                             'FLASH_SALE', 'WISHLIST_SALE', 'LOCAL_DEAL'}:
        category_enabled = prefs.shopping_price_alerts
    elif notification_type in {'ORDER_UPDATE'}:
        category_enabled = prefs.orders
    elif notification_type in {'REFERRAL_REWARD'}:
        category_enabled = prefs.referral_rewards
    elif notification_type in {'PROMOTION', 'MAINTENANCE', 'SECURITY_UPDATE'}:
        category_enabled = prefs.promotions
    elif notification_type in {'ACCOUNT_SECURITY'}:
        category_enabled = prefs.account_security
    elif notification_type in {'AI_RECOMMENDATION'}:
        category_enabled = prefs.ai_recommendations
    elif notification_type in {'PRICE_INCREASE'}:
        category_enabled = prefs.price_increase_alerts

    if not category_enabled and channel == 'SYSTEM':
        return None

    from django.utils import timezone
    is_future = scheduled_at and scheduled_at > timezone.now()
    if is_future:
        is_sent = False

    notification = Notification.objects.create(
        user=user,
        title=title,
        body=body,
        notification_type=notification_type,
        channel=channel,
        recipient_type=recipient_type,
        image_url=image_url or None,
        cta_text=cta_text,
        cta_link=cta_link,
        is_sent=is_sent,
        scheduled_at=scheduled_at,
    )

    if not is_future and user.fcm_tokens.exists():
        send_push_notification(user=user, title=title, body=body)

    return notification


def send_order_notification(user, order, status_label):
    return create_notification(
        user=user,
        title=f'Order {status_label}',
        body=f'Your order {order.order_number} is now {status_label}.',
        notification_type='ORDER_UPDATE',
        channel='SYSTEM',
        recipient_type='USER',
    )


def send_referral_reward_notification(user, amount):
    return create_notification(
        user=user,
        title='Referral reward earned',
        body=f'You earned a referral reward of {amount}.',
        notification_type='REFERRAL_REWARD',
        channel='SYSTEM',
        recipient_type='USER',
    )


def send_price_drop_notification(user, product_title, product_url=None):
    return create_notification(
        user=user,
        title='Price drop alert',
        body=f'{product_title} is now available at a lower price.',
        notification_type='PRICE_DROP',
        channel='SYSTEM',
        recipient_type='USER',
        cta_text='View Product',
        cta_link=product_url or '',
    )


def send_target_price_reached_notification(user, product_title, product_url=None):
    return create_notification(
        user=user,
        title='Target price reached',
        body=f'{product_title} reached your target price.',
        notification_type='TARGET_PRICE_REACHED',
        channel='SYSTEM',
        recipient_type='USER',
        cta_text='View Product',
        cta_link=product_url or '',
    )


def send_back_in_stock_notification(user, product_title, product_url=None):
    return create_notification(
        user=user,
        title='Back in stock',
        body=f'{product_title} is back in stock.',
        notification_type='BACK_IN_STOCK',
        channel='SYSTEM',
        recipient_type='USER',
        cta_text='View Product',
        cta_link=product_url or '',
    )


def send_flash_sale_notification(user, title, body, product_url=None):
    return create_notification(
        user=user,
        title=title,
        body=body,
        notification_type='FLASH_SALE',
        channel='SYSTEM',
        recipient_type='USER',
        cta_text='View Product',
        cta_link=product_url or '',
    )


def send_ai_recommendation_notification(user, title, body, product_url=None):
    return create_notification(
        user=user,
        title=title,
        body=body,
        notification_type='AI_RECOMMENDATION',
        channel='SYSTEM',
        recipient_type='USER',
        cta_text='View Product',
        cta_link=product_url or '',
    )
