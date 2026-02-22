from celery import shared_task, group
from .services.ebay_service import EbayService
from .services.clickbank_service import ClickBankService
from .models import Platform
import logging

logger = logging.getLogger(__name__)


@shared_task
def sync_ebay_task(query, limit=10):
    """Background এ eBay sync"""
    try:
        platform, _ = Platform.objects.get_or_create(
            code='ebay',
            defaults={'name': 'eBay', 'api_enabled': True}
        )
        service = EbayService()
        results = service.search_products(query, limit=limit)
        items = results.get('itemSummaries', []) if results else []
        
        synced = 0
        for item in items:
            try:
                from .views import save_ebay_product_to_db
                save_ebay_product_to_db(item, platform)
                synced += 1
            except Exception as e:
                logger.error(f"eBay item sync failed: {e}")
        
        return {'platform': 'ebay', 'synced': synced}
    except Exception as e:
        return {'platform': 'ebay', 'error': str(e)}


@shared_task
def sync_clickbank_task(query, limit=10):
    """Background এ ClickBank sync"""
    try:
        platform, _ = Platform.objects.get_or_create(
            code='clickbank',
            defaults={'name': 'ClickBank', 'api_enabled': True}
        )
        service = ClickBankService()
        items = service.search_mock_products(query, limit)
        
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
        return {'platform': 'clickbank', 'error': str(e)}


@shared_task
def sync_all_platforms_task(query, limit=10):
    """সব platform একসাথে parallel এ sync"""
    # group দিয়ে সব task একসাথে চালাও
    job = group(
        sync_ebay_task.s(query, limit),
        sync_clickbank_task.s(query, limit),
        # ভবিষ্যতে আরো platform:
        # sync_amazon_task.s(query, limit),
        # sync_aliexpress_task.s(query, limit),
    )
    result = job.apply_async()
    return result.id  # task_id return করো