import random
from django.utils import timezone
from django.db.models import F, Q
from .models import CustomAd
from django.core.cache import cache

def get_weighted_ads(count=3):
    cache_key = f'active_ads_{count}'
    final_ads = cache.get(cache_key)
    
    if not final_ads:
        now = timezone.now()
        active_ads = list(CustomAd.objects.filter(
            Q(is_approved=True) &
            Q(status='active') &
            Q(start_date__lte=now) &
            Q(end_date__gte=now) &
            Q(total_budget__gt=F('spent_amount'))
        ).select_related('advertiser'))

        if not active_ads:
            return []

        weights = [ad.priority_weight * (5 if ad.is_premium else 1) for ad in active_ads]
        k_val = min(len(active_ads), count)
        selected_ads = random.choices(active_ads, weights=weights, k=k_val)
        
        seen = set()
        final_ads = []
        for ad in selected_ads:
            if ad.id not in seen:
                seen.add(ad.id)
                final_ads.append(ad)
        
        cache.set(cache_key, final_ads, 60)

    if final_ads:
        ad_ids = [ad.id for ad in final_ads]
        CustomAd.objects.filter(id__in=ad_ids).update(
            impressions=F('impressions') + 1
        )
        for ad in final_ads:
            ad.impressions += 1
            
    return final_ads