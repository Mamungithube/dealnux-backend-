"""
tasks.py  —  Celery async tasks
Circular import fix: save_generic_product_to_db এখন db_helpers থেকে আসে।
Clickbank ও Shopify সরানো হয়েছে।
"""

from celery import shared_task, group
from .services.ebay_service import EbayRapidService
from .services.amazon_service import AmazonService
from .services.walmart_service import WalmartService
from .services.sephora_service import SephoraService
from .services.target_service import TargetService
from .services.wayfair_service import WayfairService
from .services.aliexpress_service import AliExpressService
from .services.bestbuy_service import BestBuyService
from .models import Platform
import logging

logger = logging.getLogger(__name__)


# ── shared save helper — circular import নেই ─────────────────────────────────
def _get_save_fn():
    from .db_helpers import save_generic_product_to_db
    return save_generic_product_to_db


@shared_task
def sync_ebay_task(query, limit=10):
    try:
        platform, _ = Platform.objects.get_or_create(
            code='ebay',
            defaults={'name': 'eBay', 'api_enabled': True}
        )
        if not platform.api_enabled:
            return {'platform': 'ebay', 'skipped': 'disabled'}

        service  = EbayRapidService()
        items    = service.search_products(query, limit=limit)
        save_fn  = _get_save_fn()
        synced   = 0

        for item in items:
            try:
                product_data = service.extract_product_data(item)
                # Non-USD skip
                if product_data.get('_is_non_usd'):
                    logger.info(f"eBay non-USD listing skipped: {product_data.get('title','')[:40]}")
                    continue
                result = save_fn(product_data, platform, query=query)
                if result[0]:
                    synced += 1
            except Exception as e:
                logger.error(f"eBay item sync failed: {e}")

        return {'platform': 'ebay', 'synced': synced}
    except Exception as e:
        logger.error(f"eBay sync task failed: {e}")
        return {'platform': 'ebay', 'error': str(e)}


@shared_task
def sync_amazon_task(query, limit=10):
    try:
        platform, _ = Platform.objects.get_or_create(
            code='amazon',
            defaults={'name': 'Amazon', 'api_enabled': True}
        )
        if not platform.api_enabled:
            return {'platform': 'amazon', 'skipped': 'disabled'}

        service = AmazonService()
        items   = service.search_products(query, limit=limit)
        save_fn = _get_save_fn()
        synced  = 0

        for item in items:
            try:
                product_data = service.extract_product_data(item)
                if save_fn(product_data, platform, query=query)[0]:
                    synced += 1
            except Exception as e:
                logger.error(f"Amazon item sync failed: {e}")

        return {'platform': 'amazon', 'synced': synced}
    except Exception as e:
        logger.error(f"Amazon sync task failed: {e}")
        return {'platform': 'amazon', 'error': str(e)}


@shared_task
def sync_walmart_task(query, limit=10):
    try:
        platform, _ = Platform.objects.get_or_create(
            code='walmart',
            defaults={'name': 'Walmart', 'api_enabled': True}
        )
        if not platform.api_enabled:
            return {'platform': 'walmart', 'skipped': 'disabled'}

        service = WalmartService()
        items   = service.search_products(query, limit=limit)
        save_fn = _get_save_fn()
        synced  = 0

        for item in items:
            try:
                product_data = service.extract_product_data(item)
                if save_fn(product_data, platform, query=query)[0]:
                    synced += 1
            except Exception as e:
                logger.error(f"Walmart item sync failed: {e}")

        return {'platform': 'walmart', 'synced': synced}
    except Exception as e:
        logger.error(f"Walmart sync task failed: {e}")
        return {'platform': 'walmart', 'error': str(e)}


@shared_task
def sync_sephora_task(query, limit=10):
    try:
        platform, _ = Platform.objects.get_or_create(
            code='sephora',
            defaults={'name': 'Sephora', 'api_enabled': True}
        )
        if not platform.api_enabled:
            return {'platform': 'sephora', 'skipped': 'disabled'}

        service = SephoraService()
        items   = service.search_products(query, limit=limit)
        save_fn = _get_save_fn()
        synced  = 0

        for item in items:
            try:
                product_data = service.extract_product_data(item)
                if save_fn(product_data, platform, query=query)[0]:
                    synced += 1
            except Exception as e:
                logger.error(f"Sephora item sync failed: {e}")

        return {'platform': 'sephora', 'synced': synced}
    except Exception as e:
        logger.error(f"Sephora sync task failed: {e}")
        return {'platform': 'sephora', 'error': str(e)}


@shared_task
def sync_target_task(query, limit=10):
    try:
        platform, _ = Platform.objects.get_or_create(
            code='target',
            defaults={'name': 'Target', 'api_enabled': True}
        )
        if not platform.api_enabled:
            return {'platform': 'target', 'skipped': 'disabled'}

        service = TargetService()
        items   = service.search_products(query, limit=limit)
        save_fn = _get_save_fn()
        synced  = 0

        for item in items:
            try:
                product_data = service.extract_product_data(item)
                if save_fn(product_data, platform, query=query)[0]:
                    synced += 1
            except Exception as e:
                logger.error(f"Target item sync failed: {e}")

        return {'platform': 'target', 'synced': synced}
    except Exception as e:
        logger.error(f"Target sync task failed: {e}")
        return {'platform': 'target', 'error': str(e)}


@shared_task
def sync_wayfair_task(query, limit=10):
    try:
        platform, _ = Platform.objects.get_or_create(
            code='wayfair',
            defaults={'name': 'Wayfair', 'api_enabled': True}
        )
        if not platform.api_enabled:
            return {'platform': 'wayfair', 'skipped': 'disabled'}

        service = WayfairService()
        items   = service.search_products(query, limit=limit)
        save_fn = _get_save_fn()
        synced  = 0

        for item in items:
            try:
                product_data = service.extract_product_data(item)
                if save_fn(product_data, platform, query=query)[0]:
                    synced += 1
            except Exception as e:
                logger.error(f"Wayfair item sync failed: {e}")

        return {'platform': 'wayfair', 'synced': synced}
    except Exception as e:
        logger.error(f"Wayfair sync task failed: {e}")
        return {'platform': 'wayfair', 'error': str(e)}


@shared_task
def sync_aliexpress_task(query, limit=10):
    try:
        platform, _ = Platform.objects.get_or_create(
            code='aliexpress',
            defaults={'name': 'AliExpress', 'api_enabled': True}
        )
        if not platform.api_enabled:
            return {'platform': 'aliexpress', 'skipped': 'disabled'}

        service = AliExpressService()
        items   = service.search_products(query, limit=limit)
        save_fn = _get_save_fn()
        synced  = 0

        for item in items:
            try:
                product_data = service.extract_product_data(item)
                if save_fn(product_data, platform, query=query)[0]:
                    synced += 1
            except Exception as e:
                logger.error(f"AliExpress item sync failed: {e}")

        return {'platform': 'aliexpress', 'synced': synced}
    except Exception as e:
        logger.error(f"AliExpress sync task failed: {e}")
        return {'platform': 'aliexpress', 'error': str(e)}


@shared_task
def sync_bestbuy_task(query, limit=10):
    try:
        platform, _ = Platform.objects.get_or_create(
            code='bestbuy',
            defaults={'name': 'BestBuy', 'api_enabled': True}
        )
        if not platform.api_enabled:
            return {'platform': 'bestbuy', 'skipped': 'disabled'}

        service = BestBuyService()
        items   = service.search_products(query, limit=limit)
        save_fn = _get_save_fn()
        synced  = 0

        for item in items:
            try:
                product_data = service.extract_product_data(item)
                if save_fn(product_data, platform, query=query)[0]:
                    synced += 1
            except Exception as e:
                logger.error(f"BestBuy item sync failed: {e}")

        return {'platform': 'bestbuy', 'synced': synced}
    except Exception as e:
        logger.error(f"BestBuy sync task failed: {e}")
        return {'platform': 'bestbuy', 'error': str(e)}


# ── Category routing ──────────────────────────────────────────────────────────

SEPHORA_CATEGORIES = {
    "Beauty & Makeup", "Skincare", "Hair Care", "Fragrances & Perfumes",
    "Personal Care & Hygiene", "Oral Care", "Men's Grooming",
}

WAYFAIR_CATEGORIES = {
    "Furniture", "Home Decor", "Kitchen & Dining", "Bedding & Bath",
    "Garden & Outdoor", "Lighting & Ceiling Fans", "Smart Home Devices",
}


@shared_task
def sync_all_platforms_task(query, limit=30):
    """সব active platform এ parallel sync।"""
    tasks = [
        sync_amazon_task.s(query, limit),
        sync_walmart_task.s(query, limit),
        sync_ebay_task.s(query, limit),
        sync_target_task.s(query, limit),
        sync_aliexpress_task.s(query, limit),
        sync_bestbuy_task.s(query, limit),
    ]
    if query in SEPHORA_CATEGORIES:
        tasks.append(sync_sephora_task.s(query, limit))
    if query in WAYFAIR_CATEGORIES:
        tasks.append(sync_wayfair_task.s(query, limit))

    job    = group(*tasks)
    result = job.apply_async()
    return result.id


@shared_task
def hourly_fixed_category_sync():
    """প্রতি ঘন্টায় fixed category sync।"""
    FIXED_CATEGORIES = [
        "Smartphones", "Laptops", "Tablets", "Audio & Headphones",
        "Smartwatches", "TV & Home Theater", "Video Games & Consoles",
        "Men's Clothing", "Men's Shoes", "Women's Clothing", "Women's Shoes",
        "Handbags & Wallets", "Fine Jewelry", "Men's Grooming",
        "Beauty & Makeup", "Skincare", "Hair Care", "Fragrances & Perfumes",
        "Personal Care & Hygiene",
        "Furniture", "Home Decor", "Kitchen & Dining", "Bedding & Bath",
        "Garden & Outdoor", "Smart Home Devices",
        "Exercise & Fitness Equipment", "Camping & Hiking", "Team Sports",
        "Baby Products & Accessories", "Toys & Games",
        "Car Electronics & GPS", "Pet Supplies", "Household Cleaning Supplies",
    ]

    for index, category_name in enumerate(FIXED_CATEGORIES):
        delay_seconds = index * 30
        sync_all_platforms_task.apply_async(
            args=[category_name, 10],
            countdown=delay_seconds
        )

    logger.info(f"Scheduled sync for {len(FIXED_CATEGORIES)} categories.")
    return f"Scheduled {len(FIXED_CATEGORIES)} categories."