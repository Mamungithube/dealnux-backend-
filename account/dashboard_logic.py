from django.db.models import Sum, Count, Q, F
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
from payment.models import Payment, SellerPayout, UserSubscription
from store.models import Order, SellerProfile, SellerRequest, SellerProduct
from account.models import User

def get_admin_dashboard_stats():
    # ১০ মিনিটের জন্য ডাটা ক্যাশ করে রাখা হবে যাতে CPU লোড না বাড়ে
    stats = cache.get('dealnux_admin_stats')
    if stats:
        return stats

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Database Aggregations (এক কুয়েরিতে অনেক ডাটা)
    revenue_data = Payment.objects.filter(status='PAID').aggregate(
        total_rev=Sum('final_amount'),
        total_fees=Sum('service_fee')
    )

    order_stats = Order.objects.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status='PENDING')),
        disputed=Count('id', filter=Q(status='DISPUTED'))
    )

    # KPI logic
    stats = {
        "kpi": {
            "total_revenue": revenue_data['total_rev'] or 0,
            "platform_fees": revenue_data['total_fees'] or 0,
            "total_orders": order_stats['total'],
            "active_users": User.objects.filter(is_active=True).count(),
            "total_sellers": SellerProfile.objects.filter(is_active=True).count(),
            "pending_payouts": SellerPayout.objects.filter(status='PENDING').count(),
            "open_disputes": order_stats['disputed'],
        },
        "performance": {
            "monthly_sales": Order.objects.filter(created_at__gte=month_start).count(),
            "monthly_revenue": Payment.objects.filter(status='PAID', created_at__gte=month_start).aggregate(s=Sum('final_amount'))['s'] or 0,
        },
        "seller_overview": {
            "pending_apps": SellerRequest.objects.filter(status='PENDING').count(),
        }
    }

    cache.set('dealnux_admin_stats', stats, 600) # ৬০০ সেকেন্ড বা ১০ মিনিট ক্যাশ
    return stats