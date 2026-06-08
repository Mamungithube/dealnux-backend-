from django.utils import timezone


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
            return False, "Daily click limit reached!"

        subscription.daily_click_count += 1
        subscription.save(update_fields=['daily_click_count', 'last_click_date'])
        return True, "Click recorded."
    except Exception as e:
        return False, f"Unable to validate click: {e}"


def process_referral_reward_for_user(user):
    """Process referral rewards for a referred user once subscription and first purchase criteria are met."""
    from decimal import Decimal
    from store.models import Order

    try:
        if not getattr(user, 'referred_by', None) or user.has_referral_reward_awarded:
            return False

        if not Order.objects.filter(buyer=user).exists():
            return False

        referrer = user.referred_by
        user_subscription = getattr(user, 'subscription', None)
        referrer_subscription = getattr(referrer, 'subscription', None)

        if (
            user_subscription is None or user_subscription.status != 'ACTIVE' or
            referrer_subscription is None or referrer_subscription.status != 'ACTIVE'
        ):
            return False

        referrer.balance += Decimal('10')
        referrer.save(update_fields=['balance'])

        user.has_referral_reward_awarded = True
        user.save(update_fields=['has_referral_reward_awarded'])
        print(f"Referral reward paid to {referrer.email} for referred user {user.email}")
        return True
    except Exception as e:
        print(f"Error processing referral reward in helper: {str(e)}")
        return False
