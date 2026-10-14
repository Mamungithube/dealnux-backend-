# admin_dashboard.py (এটি আপনার অ্যাপের ভেতরে তৈরি করুন)

from django.db.models import Sum, Count, Avg, Q
from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache
from .models import Payment, User, Product, SellerPayout, ProductListing # আপনার মডেলগুলো

def get_dashboard_stats():
    # ৫ মিনিটের জন্য ডাটা ক্যাশ করে রাখা (CPU usage কমাতে)
    stats = cache.get('dealnux_admin_stats')
    if stats:
        return stats

    now = timezone.now()
    last_30_days = now - timedelta(days=30)

    # ১. KPI Cards ডাটা
    total_revenue = Payment.objects.filter(status='PAID').aggregate(Sum('final_amount'))['final_amount__sum'] or 0
    platform_fees = SellerPayout.objects.aggregate(Sum('platform_fee_amount'))['platform_fee_amount__sum'] or 0
    total_orders = Payment.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    pending_payouts = SellerPayout.objects.filter(status='PENDING').count()
    
    # ২. Revenue Graph (গত ৩০ দিন)
    revenue_chart = (
        Payment.objects.filter(status='PAID', created_at__gte=last_30_days)
        .extra(select={'day': "date(created_at)"})
        .values('day')
        .annotate(total=Sum('final_amount'))
        .order_by('day')
    )

    stats = {
        'total_revenue': total_revenue,
        'platform_fees': platform_fees,
        'total_orders': total_orders,
        'active_users': active_users,
        'pending_payouts': pending_payouts,
        'revenue_labels': [item['day'].strftime('%d %b') for item in revenue_chart],
        'revenue_values': [float(item['total']) for item in revenue_chart],
    }

    cache.set('dealnux_admin_stats', stats, 300) # ৩০০ সেকেন্ড বা ৫ মিনিট
    return stats