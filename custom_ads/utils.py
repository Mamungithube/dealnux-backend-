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
    
    # 1. Cache থেকে অ্যাক্টিভ অ্যাড পুল আনা
    active_ads = cache.get(cache_key)
    
    if active_ads is None:
        now = timezone.now()
        # শুধু বৈধ অ্যাডগুলো ফিল্টার করা
        active_ads = list(CustomAd.objects.filter(
            Q(is_approved=True) &
            Q(status='active') &
            Q(start_date__lte=now) &
            Q(end_date__gte=now) &
            Q(total_budget__gt=F('spent_amount'))
        ).select_related('advertiser'))
        
        # 60 সেকেন্ডের জন্য Cache-এ রাখা
        cache.set(cache_key, active_ads, 60)

    if not active_ads:
        return[]

    # 2. Pure Random Selection (লটারি)
    # k_val হচ্ছে আমরা কয়টি অ্যাড দেখাতে চাই (যেটা count থেকে আসে, তবে পুলের চেয়ে বেশি হতে পারবে না)
    k_val = min(len(active_ads), count)
    
    # random.sample ব্যবহার করলে ডুপ্লিকেট অ্যাড আসবে না, এবং সবার সমান সুযোগ থাকবে
    selected_ads = random.sample(active_ads, k_val)

    # 3. Impression আপডেট করা
    if selected_ads:
        ad_ids = [ad.id for ad in selected_ads]
        
        # Main Ad মডেলে ইম্প্রেশন আপডেট
        CustomAd.objects.filter(id__in=ad_ids).update(impressions=F('impressions') + 1)
        
        # Daily Performance মডেলেও ইম্প্রেশন আপডেট (Figma গ্রাফের জন্য)
        today = timezone.now().date()
        from .models import AdDailyPerformance # import here to avoid circular dependency
        
        for ad in selected_ads:
            ad.impressions += 1 # Update Python object for the current request
            daily_stat, _ = AdDailyPerformance.objects.get_or_create(ad=ad, date=today)
            daily_stat.impressions = F('impressions') + 1
            daily_stat.save()
            
    return selected_ads