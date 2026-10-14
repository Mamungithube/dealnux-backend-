import logging
from django.utils import timezone

logger = logging.getLogger(__name__)


def validate_and_increment_click(user, product_id=None):
    """Validate and increment a user's daily click quota for API-backed product details."""
    try:
        subscription = getattr(user, 'subscription', None)
        if not subscription or not subscription.is_active:
            return False, "Please subscribe to a plan."

        today = timezone.now().date()
        if subscription.last_click_date != today:
            subscription.daily_click_count = 0
            subscription.last_click_date = today

        if subscription.daily_click_count >= subscription.plan.clicks_per_day:
            try:
                from notifications.utils import create_notification
                create_notification(
                    user=user,
                    title="Retailer Click Limit Reached! ⚠️",
                    body="You have reached your daily click limit for retailer links. Upgrade your plan to continue browsing unlimited deals!",
                    notification_type="SUBSCRIPTION_REMINDER",
                    channel="SYSTEM"
                )
            except Exception:
                pass
            return False, "Daily click limit reached!"

        subscription.daily_click_count += 1
        subscription.save(update_fields=['daily_click_count', 'last_click_date'])
        return True, "Click recorded."
    except Exception as e:
        return False, f"Unable to validate click: {e}"


def process_referral_reward_for_user(user):
    """
    Process referral rewards for:
    1. If `user` is a referred user who now meets criteria (user sub active, referrer sub active, has order).
    2. If `user` is a referrer whose subscription just activated, check all referred friends who have orders.
    """
    if not user:
        return False

    from account.models import User, SiteSettings
    from store.models import Order
    from django.db import transaction

    reward_count = 0

    def _try_award(referred_user):
        nonlocal reward_count
        if not referred_user or getattr(referred_user, 'has_referral_reward_awarded', False):
            return False

        referrer = getattr(referred_user, 'referred_by', None)
        if not referrer:
            return False

        # 1. Order check for referred user
        if not Order.objects.filter(buyer=referred_user).exists():
            return False

        # 2. Subscription check for referred user
        user_sub = getattr(referred_user, 'subscription', None)
        user_active = (
            user_sub is not None and 
            (user_sub.status == 'ACTIVE' or getattr(user_sub, 'is_active', False))
        )
        if not user_active:
            return False

        # 3. Subscription check for referrer
        referrer_sub = getattr(referrer, 'subscription', None)
        referrer_active = (
            referrer_sub is not None and 
            (referrer_sub.status == 'ACTIVE' or getattr(referrer_sub, 'is_active', False))
        )
        if not referrer_active:
            return False

        # All criteria met! Award reward atomically to the referrer only
        try:
            with transaction.atomic():
                amount = SiteSettings.get().referral_reward_amount

                # 1. Credit balance ONLY to the referrer (the friend does not earn points/balance)
                referrer.refresh_from_db()
                referrer.balance += amount
                referrer.save(update_fields=['balance'])

                # 2. Mark reward as awarded on referred friend to prevent duplicate processing
                referred_user.refresh_from_db()
                referred_user.has_referral_reward_awarded = True
                referred_user.save(update_fields=['has_referral_reward_awarded'])

                reward_count += 1
                logger.info(f"Referral reward awarded: {referrer.email} received ${amount} for referring {referred_user.email}")

                # 3. Notification ONLY to referrer
                try:
                    from notifications.utils import send_referral_reward_notification
                    send_referral_reward_notification(referrer, amount)
                except Exception as e:
                    logger.warning(f"Notification warning: {e}")

                # 4. Email notification ONLY to referrer
                try:
                    from custom_ads.utils import send_dealnux_email
                    send_dealnux_email(
                        "You've earned a referral reward! - DealNux",
                        referrer.email,
                        "emails/referrer_reward.html",
                        {"referrer": referrer, "referred_user": referred_user, "amount": amount}
                    )
                except Exception as e:
                    logger.warning(f"Email warning: {e}")
            return True
        except Exception as e:
            logger.error(f"Error awarding referral bonus: {e}", exc_info=True)
            return False

    try:
        # Case A: Check if `user` is the referred user
        _try_award(user)

        # Case B: Check if `user` is a referrer with referred friends pending reward
        referred_friends = User.objects.filter(referred_by=user, has_referral_reward_awarded=False)
        for friend in list(referred_friends):
            _try_award(friend)

        return reward_count > 0
    except Exception as e:
        logger.error(f"Error in process_referral_reward_for_user: {e}", exc_info=True)
        return False



def refresh_subscription_limits(sub):
    from django.utils import timezone
    today = timezone.now().date()
    
    if sub.last_click_date != today:
        sub.daily_click_count = 0
        sub.last_click_date = today
        sub.save(update_fields=['daily_click_count', 'last_click_date'])
    return sub