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
                    product_url=f"/product/{product.id}"
                )
                sent_count += 1
        except Exception as e:
            logger.error(f"Failed to send AI recommendation for user {user.id}: {e}")

    return f"AI recommendation task completed. Sent to {sent_count} users."


@shared_task
def send_policy_update_emails_task(policy_name, cta_link=None):
    """Send email notifications to all active users when a policy is updated."""
    from account.models import User
    from django.conf import settings
    from django.core.mail import EmailMultiAlternatives

    active_users = User.objects.filter(is_active=True).exclude(email='').values_list('email', flat=True)
    emails_list = list(set(active_users))
    if not emails_list:
        return "No active users with email addresses found."

    site_url = getattr(settings, 'SITE_URL', 'https://www.dealnux.shop') or 'https://www.dealnux.shop'
    relative_link = cta_link or f"/policy/{policy_name.lower().replace(' ', '-')}/"
    full_url = f"{site_url.rstrip('/')}{relative_link}" if not relative_link.startswith('http') else relative_link
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', 'noreply@dealnux.shop')

    subject = f"[DealNux Notice] Updated Policy: {policy_name}"
    
    text_content = (
        f"Important Policy Update Notice\n\n"
        f"Our {policy_name} has been updated.\n"
        f"Please take a moment to review the updated policy terms to stay informed about your rights and how we handle data and services on DealNux.\n\n"
        f"Review Policy: {full_url}\n\n"
        f"If you have questions, please contact info@dealnux.shop.\n"
        f"DealNux Platform"
    )

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #ffffff;">
        <h2 style="color: #1a202c; margin-top: 0;">Important Policy Update Notice</h2>
        <p style="color: #4a5568; font-size: 15px; line-height: 1.6;">Dear Valued DealNux User,</p>
        <p style="color: #4a5568; font-size: 15px; line-height: 1.6;">We are writing to inform you that we have updated our <strong>{policy_name}</strong>.</p>
        <p style="color: #4a5568; font-size: 15px; line-height: 1.6;">Please take a moment to review the updated policy terms to stay informed about your rights and how we handle data and services on the DealNux Platform.</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{full_url}" style="background-color: #2563eb; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Review {policy_name}</a>
        </div>
        <p style="color: #718096; font-size: 13px;">If you have any questions or concerns regarding these changes, please contact us at <a href="mailto:info@dealnux.shop" style="color: #2563eb;">info@dealnux.shop</a>.</p>
        <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 20px 0;" />
        <p style="color: #a0aec0; font-size: 12px; text-align: center; margin: 0;">&copy; DealNux Platform - Brightway Consult & HR Recruiting Solutions LLC</p>
    </div>
    """

    sent_count = 0
    batch_size = 50
    for i in range(0, len(emails_list), batch_size):
        batch = emails_list[i:i + batch_size]
        for recipient in batch:
            try:
                msg = EmailMultiAlternatives(
                    subject=subject,
                    body=text_content,
                    from_email=from_email,
                    to=[recipient]
                )
                msg.attach_alternative(html_content, "text/html")
                msg.send(fail_silently=True)
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send policy update email to {recipient}: {e}")

    return f"Sent policy update email for {policy_name} to {sent_count} users."


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_async_task(self, subject, recipient_email, html_content):
    """
    Asynchronous email sending task via Celery.
    Retries up to 3 times on temporary network/SMTP failures.
    """
    from django.core.mail import EmailMessage
    from django.conf import settings

    try:
        msg = EmailMessage(
            subject=subject,
            body=html_content,
            from_email=settings.EMAIL_HOST_USER,
            to=[recipient_email],
        )
        msg.content_subtype = "html"
        msg.send()
        return True
    except Exception as exc:
        logger.error(f"Async email sending failed to {recipient_email}: {exc}")
        raise self.retry(exc=exc)

