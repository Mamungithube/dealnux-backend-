from django.utils import timezone
from django.db.models import Sum, Avg, Count
from .models import Order, SellerProduct, ProductReview


def get_seller_dashboard_overview_data(seller):
    """
    Computes dashboard overview statistics for a seller profile.
    """
    today = timezone.now()

    this_month_earned = Order.objects.filter(
        seller=seller, status='ACCEPTED',
        created_at__month=today.month, created_at__year=today.year
    ).aggregate(total=Sum('item_total'))['total'] or 0

    total_units = SellerProduct.objects.filter(
        seller=seller, status='APPROVED'
    ).aggregate(total=Sum('quantity'))['total'] or 0

    review_stats = ProductReview.objects.filter(product__seller=seller).aggregate(
        average_rating=Avg('rating'),
        total_reviews=Count('id')
    )

    return {
        "shop_name": seller.shop_name,
        "stats": {
            "total_products": SellerProduct.objects.filter(seller=seller).count(),
            "total_units_in_stock": total_units,
            "active_orders": Order.objects.filter(seller=seller, status__in=['PENDING', 'CONFIRMED', 'SHIPPED']).count(),
            "needs_action": Order.objects.filter(seller=seller, status='PENDING').count(),
            "this_month_earnings": float(this_month_earned),
            "total_earned": float(seller.total_earnings),
            "total_reviews": review_stats['total_reviews'],
            "average_rating": round(review_stats['average_rating'] or 0, 1),
        }
    }


def get_seller_shipping_settings(seller):
    """
    Returns structured dictionary of a seller's shipping settings.
    """
    return {
        "local_pickup": {
            "active": seller.local_pickup_active,
            "address_street": seller.pickup_address_street,
            "address_city": seller.pickup_address_city,
            "address_state": seller.pickup_address_state,
            "address_zip": seller.pickup_address_zip,
            "hours_start": seller.pickup_hours_start.strftime("%H:%M:%S") if seller.pickup_hours_start else None,
            "hours_end": seller.pickup_hours_end.strftime("%H:%M:%S") if seller.pickup_hours_end else None,
            "available_days": seller.pickup_available_days
        },
        "local_delivery": {
            "active": seller.local_delivery_active,
            "radius": seller.delivery_radius,
            "fee": float(seller.delivery_fee),
            "timeframe": seller.delivery_timeframe
        },
        "standard_shipping": {
            "active": seller.standard_shipping_active,
            "processing_time": seller.order_processing_time,
            "preferred_couriers": seller.preferred_couriers
        }
    }


def update_seller_shipping_settings(seller, data):
    """
    Updates seller shipping configuration from validated/received payload.
    """
    # Local Pickup Section
    pickup_data = data.get('local_pickup', {})
    if pickup_data:
        seller.local_pickup_active = pickup_data.get('active', seller.local_pickup_active)
        seller.pickup_address_street = pickup_data.get('address_street', seller.pickup_address_street)
        seller.pickup_address_city = pickup_data.get('address_city', seller.pickup_address_city)
        seller.pickup_address_state = pickup_data.get('address_state', seller.pickup_address_state)
        seller.pickup_address_zip = pickup_data.get('address_zip', seller.pickup_address_zip)
        seller.pickup_hours_start = pickup_data.get('hours_start', seller.pickup_hours_start)
        seller.pickup_hours_end = pickup_data.get('hours_end', seller.pickup_hours_end)
        seller.pickup_available_days = pickup_data.get('available_days', seller.pickup_available_days)

    # Local Delivery Section
    delivery_data = data.get('local_delivery', {})
    if delivery_data:
        seller.local_delivery_active = delivery_data.get('active', seller.local_delivery_active)
        seller.delivery_radius = delivery_data.get('radius', seller.delivery_radius)
        seller.delivery_fee = delivery_data.get('fee', seller.delivery_fee)
        seller.delivery_timeframe = delivery_data.get('timeframe', seller.delivery_timeframe)

    # Standard Shipping Section
    standard_data = data.get('standard_shipping', {})
    if standard_data:
        seller.standard_shipping_active = standard_data.get('active', seller.standard_shipping_active)
        seller.order_processing_time = standard_data.get('processing_time', seller.order_processing_time)
        seller.preferred_couriers = standard_data.get('preferred_couriers', seller.preferred_couriers)

    seller.save()
    return seller
