import stripe
from django.utils import timezone

def release_funds_to_seller(order):
    """অর্ডার একসেপ্ট হলে এসক্রো থেকে টাকা সেলারের স্ট্রাইপ একাউন্টে পাঠানো"""
    seller = order.seller
    if not seller.stripe_account_id or not seller.stripe_onboarding_completed:
        return False, "Seller bank not connected."

    try:
        # সেলার পাবে: Item Total + Shipping
        amount_to_transfer = int((order.item_total + order.shipping_fee) * 100) # Cents এ রূপান্তর

        transfer = stripe.Transfer.create(
            amount=amount_to_transfer,
            currency=order.currency.lower(),
            destination=seller.stripe_account_id,
            transfer_group=f"ORDER_{order.order_number}",
            metadata={'order_id': order.id}
        )
        return True, transfer.id
    except stripe.error.StripeError as e:
        return False, str(e)


def can_user_click(user):
    # ১. ইউজারের একটিভ সাবস্ক্রিপশন চেক
    sub = getattr(user, 'subscription', None)
    if not sub or not sub.is_active:
        return False, "No active subscription found."

    plan = sub.plan
    today = timezone.now().date()

    # ২. দিন পরিবর্তন হলে কাউন্টার রিসেট করা
    if user.last_click_date != today:
        user.daily_click_count = 0
        user.last_click_date = today
        user.save(update_fields=['daily_click_count', 'last_click_date'])

    # ৩. লিমিট চেক
    if user.daily_click_count >= plan.clicks_per_day:
        return False, f"Daily limit of {plan.clicks_per_day} clicks reached. Upgrade your plan!"

    return True, "Success"


from django.core.cache import cache
from django.utils import timezone

def validate_and_increment_click(user, product_id=None):
    sub = getattr(user, 'subscription', None)
    if not sub or not sub.is_active:
        return False, "Active subscription required."

    today = timezone.now().date()
    if product_id:
        cache_key = f"user_click_{user.id}_{product_id}_{today}"
        if cache.get(cache_key):
            return True, "Already counted for today"
        
    if sub.last_click_date != today:
        sub.daily_click_count = 0
        sub.last_click_date = today

    if sub.daily_click_count >= sub.plan.clicks_per_day:
        return False, "Daily limit reached!"

    sub.daily_click_count += 1
    sub.save(update_fields=['daily_click_count', 'last_click_date'])
    
    if product_id:
        cache.set(cache_key, True, 86400) 

    return True, "Success"