from celery import shared_task, group
from .services.ebay_service import EbayRapidService
from .services.clickbank_service import ClickBankService
from .services.amazon_service import AmazonService
from .services.walmart_service import WalmartService
from .services.sephora_service import SephoraService
from .services.target_service import TargetService
from .services.wayfair_service import WayfairService
from .services.aliexpress_service import AliExpressService
from .models import Platform
import logging

logger = logging.getLogger(__name__)

@shared_task
def sync_ebay_task(query, limit=10):
    try:
        platform, _ = Platform.objects.get_or_create(
            code='ebay',
            defaults={'name': 'eBay', 'api_enabled': True}
        )
        if not platform.api_enabled:
            return {'platform': 'ebay', 'skipped': 'disabled'}

        service = EbayRapidService()
        items   = service.search_products(query, limit=limit)

        synced = 0
        from .views import save_generic_product_to_db
        for item in items:
            try:
                product_data = service.extract_product_data(item)
                if save_generic_product_to_db(product_data, platform, query=query)[0]:
                    synced += 1
            except Exception as e:
                logger.error(f"eBay item sync failed: {e}")

        return {'platform': 'ebay', 'synced': synced}
    except Exception as e:
        logger.error(f"eBay sync task failed: {e}")
        return {'platform': 'ebay', 'error': str(e)}


@shared_task
def sync_clickbank_task(query, limit=10):
    try:
        platform, _ = Platform.objects.get_or_create(
            code='clickbank',
            defaults={'name': 'ClickBank', 'api_enabled': True}
        )
        if not platform.api_enabled:
            return {'platform': 'clickbank', 'skipped': 'disabled'}

        service = ClickBankService()
        items   = service.search_mock_products(query, limit)

        synced = 0
        for item in items:
            try:
                from .views import save_clickbank_product_to_db
                product_data = service.extract_product_data(item)
                save_clickbank_product_to_db(product_data, platform)
                synced += 1
            except Exception as e:
                logger.error(f"ClickBank item sync failed: {e}")

        return {'platform': 'clickbank', 'synced': synced}
    except Exception as e:
        logger.error(f"ClickBank sync task failed: {e}")
        return {'platform': 'clickbank', 'error': str(e)}


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

        synced = 0
        from .views import save_generic_product_to_db
        for item in items:
            try:
                product_data = service.extract_product_data(item)
                if save_generic_product_to_db(product_data, platform, query=query)[0]:
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

        synced = 0
        from .views import save_generic_product_to_db
        for item in items:
            try:
                product_data = service.extract_product_data(item)
                if save_generic_product_to_db(product_data, platform, query=query)[0]:
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

        synced = 0
        from .views import save_generic_product_to_db
        for item in items:
            try:
                product_data = service.extract_product_data(item)
                if save_generic_product_to_db(product_data, platform, query=query)[0]:
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

        synced = 0
        from .views import save_generic_product_to_db
        for item in items:
            try:
                product_data = service.extract_product_data(item)
                if save_generic_product_to_db(product_data, platform, query=query)[0]:
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

        synced = 0
        from .views import save_generic_product_to_db
        for item in items:
            try:
                product_data = service.extract_product_data(item)
                if save_generic_product_to_db(product_data, platform, query=query)[0]:
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

        synced = 0
        from .views import save_generic_product_to_db
        for item in items:
            try:
                product_data = service.extract_product_data(item)
                if save_generic_product_to_db(product_data, platform, query=query)[0]:
                    synced += 1
            except Exception as e:
                logger.error(f"AliExpress item sync failed: {e}")

        return {'platform': 'aliexpress', 'synced': synced}
    except Exception as e:
        logger.error(f"AliExpress sync task failed: {e}")
        return {'platform': 'aliexpress', 'error': str(e)}
    

@shared_task
def sync_all_platforms_task(query, limit=1000):
    """সব platform একসাথে parallel এ sync করে"""
    job = group(
        sync_amazon_task.s(query, limit),
        sync_walmart_task.s(query, limit),
        sync_ebay_task.s(query, limit),
        sync_clickbank_task.s(query, limit),
        sync_sephora_task.s(query, limit),
        sync_target_task.s(query, limit),
        sync_wayfair_task.s(query, limit),
        sync_aliexpress_task.s(query, limit),
    )
    result = job.apply_async()
    return result.id


@shared_task
def hourly_fixed_category_sync():
    """প্রতি ঘণ্টায় সব e-commerce category sync করে"""

    FIXED_CATEGORIES = [
        "Smartphones", "Laptops", "Desktop Computers", "Tablets",
        "Audio & Headphones", "Cameras & Photo", "Smartwatches",
        "TV & Home Theater", "Video Games & Consoles", "Computer Accessories",
        "Printers & Ink", "Drones & RC", "Wearable Technology",
        "Men's Clothing", "Men's Shoes", "Men's Watches",
        "Men's Accessories & Belts", "Men's Sunglasses", "Men's Grooming",
        "Women's Clothing", "Women's Shoes", "Handbags & Wallets",
        "Women's Watches", "Fine Jewelry", "Fashion Accessories",
        "Lingerie & Sleepwear", "Beauty & Makeup",
        "Furniture", "Home Decor", "Kitchen & Dining", "Bedding & Bath",
        "Garden & Outdoor", "Tools & Home Improvement", "Lighting & Ceiling Fans",
        "Smart Home Devices", "Pet Supplies",
        "Skincare", "Hair Care", "Fragrances & Perfumes",
        "Vitamins & Dietary Supplements", "Personal Care & Hygiene",
        "Medical Supplies & Equipment", "Oral Care",
        "Exercise & Fitness Equipment", "Cycling & Bicycles", "Camping & Hiking",
        "Fishing Equipment", "Water Sports", "Team Sports", "Golf Equipment",
        "Baby Products & Accessories", "Toys & Games", "Kids Clothing",
        "Puzzles & Board Games", "Baby Gear & Strollers",
        "Car Electronics & GPS", "Car Interior Accessories",
        "Motorcycle Parts & Accessories", "Automotive Tools & Equipment",
        "Fiction Books", "Non-Fiction & Educational Books",
        "Snack Foods", "Beverages & Coffee", "Household Cleaning Supplies",
    ]

    for index, category_name in enumerate(FIXED_CATEGORIES):
        delay_seconds = index * 10
        sync_all_platforms_task.apply_async(
            args=[category_name, 10],
            countdown=delay_seconds
        )

    logger.info(f"Scheduled sync for {len(FIXED_CATEGORIES)} categories.")
    return f"Scheduled {len(FIXED_CATEGORIES)} categories."