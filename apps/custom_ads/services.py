import logging
from decimal import Decimal
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone
from django.contrib.auth import get_user_model

from config.email import send_dealnux_email
from .models import CustomAd, AdSetting, AdDailyPerformance, AdvertiserRequest, AdReview

logger = logging.getLogger(__name__)
User = get_user_model()


# ============================================================================
# Advertiser Request Services
# ============================================================================

def approve_advertiser_request(advertiser_request: AdvertiserRequest):
    """
    Business logic for approving an advertiser application:
    - Sets user.ads_provided = True
    - Sets is_reviewed = True, reviewed_at
    - Sends approval email notification
    """
    with transaction.atomic():
        advertiser_request.approve()

    try:
        send_dealnux_email(
            "Advertiser Application Approved - DealNux",
            advertiser_request.user.email,
            "emails/advertiser_approved.html",
            {"user": advertiser_request.user}
        )
    except Exception as e:
        logger.warning(f"Failed to send advertiser approval email: {e}")

    return advertiser_request


def reject_advertiser_request(advertiser_request: AdvertiserRequest, reason: str = ""):
    """
    Business logic for rejecting an advertiser application with a reason.
    """
    with transaction.atomic():
        advertiser_request.reject(reason=reason)

    try:
        send_dealnux_email(
            "Advertiser Application Update - DealNux",
            advertiser_request.user.email,
            "emails/advertiser_rejected.html",
            {"user": advertiser_request.user, "reason": reason}
        )
    except Exception as e:
        logger.warning(f"Failed to send advertiser rejection email: {e}")

    return advertiser_request


# ============================================================================
# Ad Click & Budget Tracking Service
# ============================================================================

def record_ad_click(ad_id: int) -> dict:
    """
    Atomic business logic for CPC deduction on ad click:
    - Locks the ad row
    - Validates budget availability
    - Deducts CPC from budget and adds to spent_amount
    - Updates daily performance metrics
    - Marks ad as expired when budget runs out
    """
    with transaction.atomic():
        ad = CustomAd.objects.select_for_update().get(id=ad_id)

        setting = AdSetting.objects.first()
        cpc = setting.cpc_amount if setting else Decimal('0.50')

        if ad.status == 'expired' or ad.spent_amount >= ad.total_budget:
            raise ValueError("Ad budget already exhausted.")

        new_clicks = ad.clicks + 1
        new_spent = ad.spent_amount + cpc

        CustomAd.objects.filter(id=ad_id).update(
            clicks=new_clicks,
            spent_amount=new_spent
        )

        today = timezone.now().date()
        daily_stat, _ = AdDailyPerformance.objects.get_or_create(
            ad=ad,
            date=today,
            defaults={'impressions': 0, 'clicks': 0}
        )
        AdDailyPerformance.objects.filter(id=daily_stat.id).update(
            clicks=F('clicks') + 1
        )

        remaining = float(ad.total_budget - new_spent)

        if remaining <= 0:
            CustomAd.objects.filter(id=ad_id).update(status='expired')
            remaining = 0.0
            current_status = 'expired'
        else:
            current_status = ad.status

    return {
        "clicks": new_clicks,
        "spent_now": float(cpc),
        "total_spent": float(new_spent),
        "remaining": remaining,
        "status": current_status
    }


# ============================================================================
# Ad Approval & Lifecycle Services
# ============================================================================

def approve_custom_ad(ad: CustomAd, reviewer=None) -> CustomAd:
    """
    Business logic for approving an ad campaign:
    - Sets is_approved = True, status = 'active'
    - Creates AdReview record
    - Sends email notification to advertiser
    """
    with transaction.atomic():
        ad.is_approved = True
        ad.status = 'active'
        ad.save(update_fields=['is_approved', 'status'])

        AdReview.objects.create(
            ad=ad,
            reviewer=reviewer,
            status='approved',
            feedback='Ad approved by admin'
        )

    try:
        send_dealnux_email(
            "Your Ad is Approved! - DealNux",
            ad.advertiser.email,
            "emails/ad_approved.html",
            {"ad": ad, "user": ad.advertiser}
        )
    except Exception as e:
        logger.warning(f"Failed to send ad approval email: {e}")

    return ad


def reject_custom_ad(ad: CustomAd, reason: str = '', feedback: str = '', reviewer=None) -> CustomAd:
    """
    Business logic for rejecting an ad campaign:
    - Sets is_approved = False, status = 'rejected'
    - Creates AdReview record
    - Sends rejection email to advertiser
    """
    with transaction.atomic():
        ad.is_approved = False
        ad.status = 'rejected'
        ad.save(update_fields=['is_approved', 'status'])

        AdReview.objects.create(
            ad=ad,
            reviewer=reviewer,
            status='rejected',
            feedback=f"{reason}. {feedback}".strip('. ')
        )

    try:
        send_dealnux_email(
            "Ad Review Update - DealNux",
            ad.advertiser.email,
            "emails/ad_rejected.html",
            {"ad": ad, "user": ad.advertiser, "reason": reason, "feedback": feedback}
        )
    except Exception as e:
        logger.warning(f"Failed to send ad rejection email: {e}")

    return ad


def pause_or_unpause_ad(ad: CustomAd, action: str) -> tuple[CustomAd, str]:
    """
    Business logic to pause or unpause an active ad campaign.
    """
    if action == 'pause':
        if not ad.is_approved:
            raise ValueError("Only approved ads can be paused.")
        ad.status = 'paused'
        ad.save(update_fields=['status'])
        return ad, f"Ad '{ad.title}' has been paused."

    elif action == 'unpause':
        if not ad.is_approved:
            raise ValueError("Only approved ads can be unpaused.")
        ad.status = 'active'
        ad.save(update_fields=['status'])
        return ad, f"Ad '{ad.title}' is now active."

    else:
        raise ValueError("Invalid action. Use 'pause' or 'unpause'.")


def bulk_approve_ads(ad_ids: list, reviewer=None) -> list[CustomAd]:
    """
    Bulk approves multiple pending ads atomically.
    """
    with transaction.atomic():
        ads = list(CustomAd.objects.filter(id__in=ad_ids, is_approved=False))
        if not ads:
            return []

        CustomAd.objects.filter(id__in=[ad.id for ad in ads]).update(
            is_approved=True, status='active'
        )

        AdReview.objects.bulk_create([
            AdReview(
                ad=ad,
                reviewer=reviewer,
                status='approved',
                feedback='Bulk approved by admin'
            )
            for ad in ads
        ])

        return ads


def bulk_reject_ads(ad_ids: list, reason: str, reviewer=None) -> list[CustomAd]:
    """
    Bulk rejects multiple ads atomically.
    """
    with transaction.atomic():
        ads = list(CustomAd.objects.filter(id__in=ad_ids))
        if not ads:
            return []

        CustomAd.objects.filter(id__in=[ad.id for ad in ads]).update(
            is_approved=False, status='rejected'
        )

        AdReview.objects.bulk_create([
            AdReview(
                ad=ad,
                reviewer=reviewer,
                status='rejected',
                feedback=reason
            )
            for ad in ads
        ])

        return ads


def get_admin_dashboard_stats() -> dict:
    """
    Calculates comprehensive statistics for the Ads Admin Dashboard.
    """
    total_advertisers = User.objects.filter(ads_provided=True).count()
    pending_requests = AdvertiserRequest.objects.filter(is_reviewed=False).count()

    total_ads = CustomAd.objects.count()
    pending_ads = CustomAd.objects.filter(is_approved=False, status='pending').count()
    active_ads = CustomAd.objects.filter(is_approved=True, status='active').count()

    total_revenue = CustomAd.objects.aggregate(total=Sum('spent_amount'))['total'] or 0

    recent_requests = AdvertiserRequest.objects.filter(
        is_reviewed=False
    ).order_by('-applied_at')[:5]

    recent_ads = CustomAd.objects.filter(
        is_approved=False, status='pending'
    ).order_by('-created_at')[:5]

    return {
        'advertisers': {
            'total': total_advertisers,
            'pending_requests': pending_requests
        },
        'ads': {
            'total': total_ads,
            'pending': pending_ads,
            'active': active_ads
        },
        'revenue': {
            'total': float(total_revenue),
            'currency': 'USD'
        },
        'recent_requests': recent_requests,
        'recent_ads': recent_ads
    }
