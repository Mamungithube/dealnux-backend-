from celery import shared_task, group
from .services.ebay_service import EbayService
from .services.clickbank_service import ClickBankService
from .services.amazon_service import AmazonService
from .services.shopify_service import ShopifyService
from .services.homedepot_service import HomeDepotService
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

        service = EbayService()
        results = service.search_products(query, limit=limit)
        items = results.get('itemSummaries', []) if results else []

        synced = 0
        for item in items:
            try:
                from .views import save_ebay_product_to_db
                save_ebay_product_to_db(item, platform, query=query)  # ✅ query
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
        items = service.search_products(query, limit=limit)
        if not items:
            items = service.search_mock_products(query, limit)

        synced = 0
        for item in items:
            try:
                from .views import save_clickbank_product_to_db
                product_data = service.extract_product_data(item)
                save_clickbank_product_to_db(product_data, platform, query=query)  # ✅ query
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
        items = service.search_products(query, limit=limit)

        synced = 0
        from .views import save_generic_product_to_db
        for item in items:
            try:
                product_data = service.extract_product_data(item)
                if save_generic_product_to_db(product_data, platform, query=query)[0]:  # ✅ query
                    synced += 1
            except Exception as e:
                logger.error(f"Amazon item sync failed: {e}")

        return {'platform': 'amazon', 'synced': synced}
    except Exception as e:
        logger.error(f"Amazon sync task failed: {e}")
        return {'platform': 'amazon', 'error': str(e)}


@shared_task
def sync_shopify_task(query, limit=10):
    try:
        platform, _ = Platform.objects.get_or_create(
            code='shopify',
            defaults={'name': 'Shopify', 'api_enabled': True}
        )
        if not platform.api_enabled:
            return {'platform': 'shopify', 'skipped': 'disabled'}

        service = ShopifyService()
        items = service.search_products(query, limit)

        synced = 0
        from .views import save_generic_product_to_db
        for item in items:
            try:
                product_data = service.extract_product_data(item)
                if save_generic_product_to_db(product_data, platform, query=query)[0]:  # ✅ query
                    synced += 1
            except Exception as e:
                logger.error(f"Shopify item sync failed: {e}")

        return {'platform': 'shopify', 'synced': synced}
    except Exception as e:
        logger.error(f"Shopify sync task failed: {e}")
        return {'platform': 'shopify', 'error': str(e)}


@shared_task
def sync_homedepot_task(query, limit=10):
    try:
        platform, _ = Platform.objects.get_or_create(
            code='homedepot',
            defaults={'name': 'Home Depot', 'api_enabled': True}
        )
        if not platform.api_enabled:
            return {'platform': 'homedepot', 'skipped': 'disabled'}

        service = HomeDepotService()
        items = service.search_products(query, limit)

        synced = 0
        from .views import save_generic_product_to_db
        for item in items:
            try:
                if item:
                    product_data = service.extract_product_data(item)
                    if save_generic_product_to_db(product_data, platform, query=query)[0]:  # ✅ query
                        synced += 1
            except Exception as e:
                logger.error(f"HomeDepot item sync failed: {e}")

        return {'platform': 'homedepot', 'synced': synced}
    except Exception as e:
        logger.error(f"HomeDepot sync task failed: {e}")
        return {'platform': 'homedepot', 'error': str(e)}


@shared_task
def sync_all_platforms_task(query, limit=10):
    """সব platform একসাথে parallel এ sync করে"""
    job = group(
        sync_ebay_task.s(query, limit),
        sync_clickbank_task.s(query, limit),
        sync_amazon_task.s(query, limit),
        sync_shopify_task.s(query, limit),
        sync_homedepot_task.s(query, limit),
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
        "Action Figures & Collectibles", "Puzzles & Board Games", "Baby Gear & Strollers",
        "Car Electronics & GPS", "Car Interior Accessories", "Car Exterior Accessories",
        "Motorcycle Parts & Accessories", "Automotive Tools & Equipment",
        "Fiction Books", "Non-Fiction & Educational Books", "Movies & TV Shows",
        "Music & Vinyl Records", "Musical Instruments",
        "Snack Foods", "Beverages & Coffee", "Pantry Staples", "Household Cleaning Supplies",
        "E-Business & E-Marketing", "Self-Help & Personal Development",
        "Software & Services", "Online Courses",
    ]

    for index, category_name in enumerate(FIXED_CATEGORIES):
        delay_seconds = index * 30
        sync_all_platforms_task.apply_async(
            args=[category_name, 10],
            countdown=delay_seconds
        )

    logger.info(f"Scheduled sync for {len(FIXED_CATEGORIES)} categories.")
    return f"Scheduled {len(FIXED_CATEGORIES)} categories."