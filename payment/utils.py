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

from django.utils import timezone

def validate_and_increment_click(user):
    """
    ১. সাবস্ক্রিপশন চেক করবে।
    ২. দিন পরিবর্তন হলে কাউন্টার রিসেট করবে।
    ৩. লিমিট শেষ হলে False দিবে।
    ৪. সব ঠিক থাকলে ক্লিক ১ বাড়াবে এবং True দিবে।
    """
    sub = getattr(user, 'subscription', None)
    
    # সাবস্ক্রিপশন না থাকলে বা ইন-একটিভ থাকলে (লোকাল বাদে গ্লোবাল এক্সেস ব্লক)
    if not sub or not sub.is_active:
        return False, "Active subscription required for global retailer data."

    today = timezone.now().date()

    # দিন পরিবর্তন হলে ক্লিক রিসেট করা
    if sub.last_click_date != today:
        sub.daily_click_count = 0
        sub.last_click_date = today

    # লিমিট চেক (ডক অনুযায়ী ৫, ৪০, ৬০ ইত্যাদি)
    if sub.daily_click_count >= sub.plan.clicks_per_day:
        return False, f"Daily limit of {sub.plan.clicks_per_day} clicks reached. Upgrade your plan!"

    # সব ঠিক থাকলে ক্লিক ১ বাড়ানো
    sub.daily_click_count += 1
    sub.save(update_fields=['daily_click_count', 'last_click_date'])
    return True, "Success"