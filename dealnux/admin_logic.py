# dealnux/admin_logic.py

from django.db.models import Sum, Avg, Count
from django.utils import timezone
from datetime import timedelta
from django.apps import apps
import logging

logger = logging.getLogger(__name__)

def dashboard_callback(request, context):
    try:
        User = apps.get_model('account', 'User')
        Payment = apps.get_model('payment', 'Payment')
        Payout = apps.get_model('payment', 'SellerPayout')
        Order = apps.get_model('store', 'Order')
        Listing = apps.get_model('api_integration', 'ProductListing')
        PriceAlert = apps.get_model('api_integration', 'PriceAlert')
        Favorite = apps.get_model('api_integration', 'Favorite')
    except Exception as e:
        logger.error(f"Dashboard Model Load Error: {e}")
        return context

    now = timezone.now()
    today = now.date()
    last_month = now - timedelta(days=30)

    daily_rev = Payment.objects.filter(status='PAID', created_at__date=today).aggregate(Sum('final_amount'))['final_amount__sum'] or 0
    monthly_rev = Payment.objects.filter(status='PAID', created_at__gte=last_month).aggregate(Sum('final_amount'))['final_amount__sum'] or 0
    platform_fees = Payout.objects.aggregate(Sum('platform_fee_amount'))['platform_fee_amount__sum'] or 0
    
    total_orders = Order.objects.count()
    aov = Order.objects.aggregate(Avg('total_price'))['total_price__avg'] or 0
    
    api_items = Listing.objects.filter(platform__api_enabled=True).count()
    active_users = User.objects.filter(is_active=True).count()
    alerts = PriceAlert.objects.filter(is_active=True).count()
    saves = Favorite.objects.count()

    context.update({
        "kpi_cards": [
            {"title": "Today's Revenue", "metric": f"${daily_rev:,.2f}", "footer": "Confirmed Sales", "icon": "payments"},
            {"title": "Platform Fees", "metric": f"${platform_fees:,.2f}", "footer": "Net Earnings", "icon": "account_balance_wallet"},
            {"title": "Monthly Revenue", "metric": f"${monthly_rev:,.2f}", "footer": "Last 30 Days", "icon": "trending_up"},
            {"title": "Avg Order (AOV)", "metric": f"${aov:,.2f}", "footer": f"Total Orders: {total_orders}", "icon": "analytics"},
            
            {"title": "Total API Data", "metric": f"{api_items:,}", "footer": "Synced Items", "icon": "api"},
            {"title": "Active Users", "metric": active_users, "footer": "Total Registered", "icon": "people"},
            {"title": "Price Alerts", "metric": alerts, "footer": "Active trackings", "icon": "notifications_active"},
            {"title": "Saved Deals", "metric": saves, "footer": "User Favorites", "icon": "favorite"},
        ],
    })
    return context