import time
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Notification, NotificationPreference, DeviceToken
from .utils import create_notification

User = get_user_model()


def get_user_notifications_summary(user) -> dict:
    """
    Returns unread count and latest 20 notifications for the user.
    """
    notifications = Notification.objects.filter(user=user).order_by('-created_at')[:20]
    unread_count = Notification.objects.filter(user=user, is_read=False).count()

    return {
        'unread_count': unread_count,
        'notifications': [
            {
                'id': n.id,
                'title': n.title,
                'body': n.body,
                'channel': n.channel,
                'recipient_type': n.recipient_type,
                'image_url': n.image_url,
                'cta_text': n.cta_text,
                'cta_link': n.cta_link,
                'is_read': n.is_read,
                'created_at': n.created_at,
            } for n in notifications
        ]
    }


def mark_all_notifications_as_read(user) -> int:
    """
    Marks all notifications for the given user as read.
    """
    return Notification.objects.filter(user=user, is_read=False).update(is_read=True)


def delete_all_user_notifications(user) -> tuple[int, dict]:
    """
    Deletes all notifications for the given user.
    """
    return Notification.objects.filter(user=user).delete()


def broadcast_admin_notification(data: dict) -> int:
    """
    Business logic for broadcasting an admin notification to targeted user groups.
    """
    title = data.get('title')
    body = data.get('body')
    recipient_type = data.get('recipient_type', 'ALL_USERS')
    notification_type = data.get('notification_type', 'ADMIN_MESSAGE')
    image_url = data.get('image_url', '')
    cta_text = data.get('cta_text', '')
    cta_link = data.get('cta_link', '')
    scheduled_at = data.get('scheduled_at')

    if not title or not body:
        raise ValueError('title and body are required.')

    user_queryset = User.objects.filter(is_active=True)
    if recipient_type == 'PREMIUM_USERS':
        user_queryset = user_queryset.filter(subscription__is_active=True)
    elif recipient_type == 'FREE_USERS':
        user_queryset = user_queryset.filter(subscription__isnull=True)
    elif recipient_type == 'ALL_SELLERS':
        user_queryset = user_queryset.filter(seller_profile__is_active=True)
    elif recipient_type == 'SELECTED_USERS':
        selected_ids = data.get('user_ids', [])
        if not selected_ids:
            raise ValueError('user_ids are required for SELECTED_USERS.')
        user_queryset = user_queryset.filter(id__in=selected_ids)

    users = list(user_queryset.distinct())
    if not users:
        raise LookupError('No matching users found.')

    scheduled_datetime = None
    if scheduled_at:
        try:
            scheduled_datetime = timezone.datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
        except Exception:
            scheduled_datetime = None

    for user in users:
        create_notification(
            user=user,
            title=title,
            body=body,
            notification_type=notification_type,
            channel='ADMIN',
            recipient_type=recipient_type,
            image_url=image_url or None,
            cta_text=cta_text,
            cta_link=cta_link,
            scheduled_at=scheduled_datetime,
            is_sent=True,
        )

    return len(users)
