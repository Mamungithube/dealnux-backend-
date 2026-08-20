import random
from django.utils import timezone
from django.db.models import F, Q
from .models import CustomAd
from django.core.cache import cache

def get_weighted_ads(count=3):
    """
    Pure Random Ad Selection Algorithm.
    - All approved, active, and budgeted ads have an equal chance.
    - Automatically updates impressions.
    """
    cache_key = 'active_ads_pool'
    active_ad_ids = cache.get(cache_key)

    if active_ad_ids is None:
        now = timezone.now()
        active_ad_ids = list(CustomAd.objects.filter(
            Q(is_approved=True) &
            Q(status='active') &
            Q(start_date__lte=now) &
            Q(end_date__gte=now) &
            Q(total_budget__gt=F('spent_amount'))
        ).values_list('id', flat=True))
        cache.set(cache_key, active_ad_ids, 60)

    # Fresh query after cache
    active_ads = list(CustomAd.objects.filter(
        id__in=active_ad_ids,
        status='active',
        end_date__gte=timezone.now(),
        total_budget__gt=F('spent_amount')
    ).select_related('advertiser'))

    if not active_ads:
        return[]

    # Pure Random Selection (Lottery)
    # k_val is how many ads we want to show (which comes from count, but cannot be greater than pool)
    k_val = min(len(active_ads), count)
    
    # Using random.sample will prevent duplicate ads, and everyone will have an equal chance.
    selected_ads = random.sample(active_ads, k_val)

    # Impression update
    if selected_ads:
        ad_ids = [ad.id for ad in selected_ads]
        
        # Impression update in Main Ad model
        CustomAd.objects.filter(id__in=ad_ids).update(impressions=F('impressions') + 1)
        
        # Impression update in Daily Performance model (for Figma graphs)
        today = timezone.now().date()
        from .models import AdDailyPerformance # import here to avoid circular dependency
        
        for ad in selected_ads:
            daily_stat, _ = AdDailyPerformance.objects.get_or_create(ad=ad, date=today)
            daily_stat.impressions = F('impressions') + 1
            daily_stat.save()
            
    return selected_ads


# Re-export central email sender for backward compatibility
from dealnux.email import send_dealnux_email
