import random
from django.utils import timezone
from django.db.models import F, Q
from .models import CustomAd
from django.core.cache import cache

def get_weighted_ads(count=3):
    """
    Smart weighted ad selection algorithm
    - Premium ads get 5x weight boost
    - Higher priority_weight = higher chance
    - Only active, approved, budgeted ads
    - Tracks impressions automatically
    """
    
    # Cache key for performance
    cache_key = f'active_ads_{count}'
    cached_ads = cache.get(cache_key)
    
    if cached_ads:
        return cached_ads

    
    
    now = timezone.now()
    
    # Query active ads
    active_ads = list(CustomAd.objects.filter(
        Q(is_approved=True) &
        Q(status='active') &
        Q(start_date__lte=now) &
        Q(end_date__gte=now) &
        Q(total_budget__gt=F('spent_amount'))
    ).select_related('advertiser'))

    if not active_ads:
        return []

    # Calculate weights
    weights = []
    for ad in active_ads:
        base_weight = ad.priority_weight
        premium_multiplier = 5 if ad.is_premium else 1
        final_weight = base_weight * premium_multiplier
        weights.append(final_weight)
    
    # Select ads based on weights
    k_val = min(len(active_ads), count)
    
    try:
        selected_ads = random.choices(active_ads, weights=weights, k=k_val)
    except ValueError:
        # Fallback if weights are invalid
        selected_ads = random.sample(active_ads, k_val)
    
    # Remove duplicates while maintaining order
    seen = set()
    final_ads = []
    for ad in selected_ads:
        if ad.id not in seen:
            seen.add(ad.id)
            final_ads.append(ad)
    
    # Update impressions (bulk update for performance)
    if final_ads:
        ad_ids = [ad.id for ad in final_ads]
        CustomAd.objects.filter(id__in=ad_ids).update(
            impressions=F('impressions') + 1
        )
        
        # Refresh from DB to get updated values
        for ad in final_ads:
            ad.refresh_from_db()
    
    # Cache result for 60 seconds
    cache.set(cache_key, final_ads, 60)
    
    return final_ads