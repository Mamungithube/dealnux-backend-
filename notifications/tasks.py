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


@shared_task
def send_daily_ai_recommendations():
    """Send personalized or hot product AI recommendations to active users."""
    from account.models import User
    from api_integration.models import ProductListing, Favorite
    from notifications.utils import send_ai_recommendation_notification
    import random

    users = User.objects.filter(is_active=True)
    sent_count = 0
    for user in users:
        try:
            # Try to get user's favorited categories
            fav_categories = list(Favorite.objects.filter(user=user).values_list('product__category', flat=True).distinct())
            
            # Find a deal/listing matching their interests, or a random hot deal
            listings_qs = ProductListing.objects.filter(is_available=True)
            if fav_categories:
                listings_qs = listings_qs.filter(product__category__in=fav_categories)
                
            # Grab a random high discount listing
            hot_deals = list(listings_qs.order_by('-discount_percentage')[:20])
            if not hot_deals:
                hot_deals = list(ProductListing.objects.filter(is_available=True).order_by('-discount_percentage')[:20])
                
            if hot_deals:
                deal = random.choice(hot_deals)
                product = deal.product
                send_ai_recommendation_notification(
                    user=user,
                    title="DEALNUX AI Recommendation ✨",
                    body=f"Based on your interests, we recommend checking out '{product.title}' now available on {deal.platform.name} for ${deal.price}!",
                    product_url=product.get_absolute_url() if hasattr(product, 'get_absolute_url') else None
                )
                sent_count += 1
        except Exception as e:
            logger.error(f"Failed to send AI recommendation for user {user.id}: {e}")

    return f"AI recommendation task completed. Sent to {sent_count} users."
