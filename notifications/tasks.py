from celery import shared_task
from django.utils import timezone
from .models import Notification
from .firebase_utils import send_push_notification
import logging

logger = logging.getLogger(__name__)

@shared_task
def send_scheduled_notifications():
    """Send all scheduled notifications whose scheduled time has passed."""
    now = timezone.now()
    pending_notifications = Notification.objects.filter(
        is_sent=False,
        scheduled_at__lte=now
    ).select_related('user')

    sent_count = 0
    for notification in pending_notifications:
        try:
            user = notification.user
            if user.fcm_tokens.exists():
                send_push_notification(
                    user=user,
                    title=notification.title,
                    body=notification.body,
                    data={
                        'cta_link': notification.cta_link or '',
                        'cta_text': notification.cta_text or '',
                    }
                )
            notification.is_sent = True
            notification.save(update_fields=['is_sent'])
            sent_count += 1
        except Exception as e:
            logger.error(f"Failed to send scheduled notification {notification.id}: {e}")

    return f"Sent {sent_count} scheduled notifications."


@shared_task
def send_subscription_reminders():
    """Send subscription reminders (renewal, free trial ending)."""
    from django.utils import timezone
    from payment.models import UserSubscription
    from notifications.utils import create_notification
    from datetime import timedelta

    today = timezone.now().date()
    now = timezone.now()

    # 1. Free Trial Ending (e.g., in exactly 3 days or 1 day)
    three_days_later = (now + timedelta(days=3)).date()
    one_day_later = (now + timedelta(days=1)).date()

    trial_ending_subs = list(UserSubscription.objects.filter(
        status='TRIAL',
        trial_ends_at__date__in=[three_days_later, one_day_later]
    ).select_related('user', 'plan'))

    for sub in trial_ending_subs:
        days_left = (sub.trial_ends_at.date() - today).days
        create_notification(
            user=sub.user,
            title="Your Free Trial is Ending Soon! ⏳",
            body=f"Your free trial of '{sub.plan.name}' is ending in {days_left} day(s). Upgrade now to keep accessing premium features!",
            notification_type="SUBSCRIPTION_REMINDER",
            channel="SYSTEM"
        )

    # 2. Subscription Renewal / Expiry (e.g., in 3 days)
    active_ending_subs = list(UserSubscription.objects.filter(
        status='ACTIVE',
        expires_at__date__in=[three_days_later, one_day_later]
    ).select_related('user', 'plan'))

    for sub in active_ending_subs:
        days_left = (sub.expires_at.date() - today).days
        create_notification(
            user=sub.user,
            title="Subscription Renewal Reminder! 💳",
            body=f"Your subscription to '{sub.plan.name}' expires/renews in {days_left} day(s). Please ensure your payment details are up-to-date.",
            notification_type="SUBSCRIPTION_REMINDER",
            channel="SYSTEM"
        )

    return f"Processed reminders for {len(trial_ending_subs) + len(active_ending_subs)} subscriptions."
