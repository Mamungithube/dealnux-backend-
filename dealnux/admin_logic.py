from django.db.models import Sum
from django.apps import apps

def dashboard_callback(request, context):
    """Admin Dashboard KPI Cards & Stats Logic"""
    # রানটাইমে মডেল ইম্পোর্ট (যাতে সেটিংস এরর না দেয়)
    try:
        Payment = apps.get_model('payment', 'Payment')
        SellerPayout = apps.get_model('payment', 'SellerPayout')
        UserSubscription = apps.get_model('payment', 'UserSubscription')
        Order = apps.get_model('store', 'Order')
    except (LookupError, RuntimeError):
        return context

    # ডাটা ক্যালকুলেশন
    revenue = Payment.objects.filter(status='PAID').aggregate(Sum('final_amount'))['final_amount__sum'] or 0
    fees = SellerPayout.objects.aggregate(Sum('platform_fee_amount'))['platform_fee_amount__sum'] or 0
    active_subs = UserSubscription.objects.filter(status='ACTIVE').count()

    context.update({
        "kpi_cards": [
            {"title": "Total Revenue", "metric": f"${revenue:,.2f}", "footer": "Marketplace Sales", "icon": "payments"},
            {"title": "Platform Fees", "metric": f"${fees:,.2f}", "footer": "DealNux Earnings", "icon": "account_balance_wallet"},
            {"title": "Active Subs", "metric": active_subs, "footer": "Paid Subscribers", "icon": "subscriptions"},
            {"title": "Open Orders", "metric": Order.objects.filter(status='PENDING').count(), "footer": "Need Action", "icon": "shopping_cart"},
        ],
    })
    return context