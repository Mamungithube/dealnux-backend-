from django.utils import timezone
from datetime import timedelta
import time
import logging
import math
import re
from decimal import Decimal
from difflib import SequenceMatcher

from django.db import transaction
from django.db.models import Q, F, Min, Count, Sum, Avg, Value, Case, When, FloatField
from django.db.models.functions import TruncDate
from django.core.cache import cache
from django.contrib.postgres.search import TrigramSimilarity

from rest_framework import viewsets, generics, permissions as drf_permissions
from rest_framework.views import APIView
from rest_framework.decorators import api_view, action, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import ValidationError

from rapidfuzz import fuzz

from api_integration.product_matcher import calculate_match_score, get_product_fingerprint
from api_integration.models import (
    Product, ProductListing, Platform, Category,
    CartItem, SavingsActivity, Favorite, PriceAlert
)
from api_integration.serializers import (
    ProductSerializer, ProductDetailSerializer,
    ProductListingSerializer, PlatformSerializer,
    CategorySerializer, PriceHistorySerializer,
    CartItemSerializer, FavoriteSerializer,
    CategoryTreeSerializer, CategoryChildSerializer, PriceAlertSerializer
)
from notifications.models import Notification
from notifications.serializers import NotificationSerializer
from store.serializers import SellerProductSerializer
from api_integration.db_helpers import save_generic_product_to_db

from dealnux.responses import success_response, error_response

logger = logging.getLogger(__name__)

from api_integration.services.walmart_service import WalmartService
from api_integration.services.amazon_service import AmazonService
from api_integration.services.sephora_service import SephoraService
from api_integration.services.ebay_service import EbayRapidService
from api_integration.services.target_service import TargetService
from api_integration.services.wayfair_service import WayfairService
from api_integration.services.aliexpress_service import AliExpressService
from api_integration.services.bestbuy_service import BestBuyService
from api_integration.tasks import (
    sync_amazon_task, sync_ebay_task, sync_walmart_task,
    sync_all_platforms_task
)


def clean_display_title(title):
    title = re.sub(r'\d+%?\s*opens?\s+in\s+a\s+new\s+(window|tab)(\s+or\s+(tab|window))?',
                   '', title, flags=re.IGNORECASE)
    title = re.sub(r'opens?\s+in\s+a\s+new\s+(window|tab)(\s+or\s+(tab|window))?',
                   '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+', ' ', title).strip(' -')
    return title


def normalize_title(title):
    """Title will be normalized for comparison."""
    title = title.lower().strip()
    title = re.sub(r'[^\w\s]', '', title)
    title = re.sub(r'\s+', ' ', title)
    return title


def similarity_score(title1, title2):
    """Title will be compared and a similarity score will be returned (0-100)"""
    t1 = normalize_title(title1)
    t2 = normalize_title(title2)
    score = SequenceMatcher(None, t1, t2).ratio() * 100
    return round(score, 2)


def extract_keywords(title):
    """Extract important keywords from the title"""
    normalized = normalize_title(title)
    # common stop words বাদ দেবে
    stop_words = {'the', 'a', 'an', 'and', 'or',
                  'for', 'with', 'in', 'on', 'at', 'by'}
    words = [w for w in normalized.split(
    ) if w not in stop_words and len(w) > 1]
    return words


def token_similarity(title1, title2):
    t1 = re.sub(r'[^\w\s]', ' ', title1.lower())
    t2 = re.sub(r'[^\w\s]', ' ', title2.lower())
    t1 = re.sub(r'\s+', ' ', t1).strip()
    t2 = re.sub(r'\s+', ' ', t2).strip()
    return round(SequenceMatcher(None, t1, t2).ratio() * 100, 2)



def _build_result_template(query, platform_code, limit):
    return {
        'query':        query,
        'platform':     platform_code,
        'limit':        limit,
        'synced':       0,
        'updated':      0,
        'failed':       0,
        'products':     [],
        'external_ids': [],
    }


def _generic_sync_loop(items, platform, external_id_key, save_callable, query=None, category_slug=None):
    result = _build_result_template('', platform.code, 0)
    cat_cache = list(Category.objects.all())

    for item in items:
        external_id = item.get(external_id_key)
        if not external_id:
            continue
        result['external_ids'].append(external_id)

        try:
            with transaction.atomic():
                product, listing, created = save_callable(
                    item,
                    platform,
                    query=query,
                    category_slug=category_slug,
                    all_categories=cat_cache
                )
                if product and listing:
                    if created:
                        result['synced'] += 1
                    else:
                        result['updated'] += 1
                    result['products'].append({
                        'product_id':   product.id,
                        'title':        product.title,
                        'brand':        product.brand,
                        'main_image':   product.main_image,
                        'external_url': listing.external_url,
                        'price':        float(listing.price),
                        'currency':     listing.currency,
                        'slug':         product.slug,
                        'status':       'created' if created else 'updated',
                    })
                else:
                    result['failed'] += 1
        except Exception as e:
            result['failed'] += 1
            logger.error(f"Sync failed for {external_id}: {e}")

    return result


def _normalize_and_sync_generic(service, platform, query, limit, success_msg, not_found_msg, category_slug=None):
    items = service.search_products(query, limit=limit)
    if not items:
        return error_response(not_found_msg, code=404)

    normalized = []
    query_words = set(query.replace('-', ' ').lower().split())

    for item in items:
        try:
            product_data = service.extract_product_data(item)
            title_lower = (product_data.get('title') or '').lower()
            brand_lower = (product_data.get('brand') or '').lower()

            is_relevant = any(
                word in title_lower or word in brand_lower
                for word in query_words if len(word) > 2
            )
            if not is_relevant:
                continue
            normalized.append(product_data)
        except Exception:
            continue

    if not normalized:
        return error_response(not_found_msg, code=404)

    result = _generic_sync_loop(
        normalized, platform, 'external_id', save_generic_product_to_db,
        query=query,
        category_slug=category_slug
    )
    result['query'] = query
    result['limit'] = limit
    return success_response(result, message=success_msg)


# ── Platform-specific sync functions ─────────────────────────────────────────

def sync_ebay_products(platform, query, limit, category_slug=None):
    """eBay timeout is high so it is a background task."""
    task = sync_ebay_task.delay(query, limit, category_slug)
    return success_response({
        'query':        query,
        'platform':     'ebay',
        'task_id':      task.id,
        'message':      'eBay sync started in background (~60s)',
        'check_status': f'fetch-products/task-status/{task.id}/',
    }, message="eBay sync started")


def sync_amazon_products(platform, query, limit, category_slug=None):
    service = AmazonService()
    items = service.search_products(query, limit=limit)

    if items is None:
        return error_response("Amazon search failed", code=500)
    if not items:
        return success_response(
            _build_result_template(query, 'amazon', limit),
            message="No Amazon products found"
        )

    query_words = set(query.replace('-', ' ').lower().split())

    normalized = []
    for item in items:
        try:
            product_data = service.extract_product_data(item)
            title_lower = (product_data.get('title') or '').lower()
            brand_lower = (product_data.get('brand') or '').lower()

            is_relevant = any(
                word in title_lower or word in brand_lower
                for word in query_words if len(word) > 2
            )
            if not is_relevant:
                continue

            normalized.append(product_data)
        except Exception:
            continue

    result = _generic_sync_loop(
        normalized, platform, 'external_id', save_generic_product_to_db,
        query=query,
        category_slug=category_slug
    )
    result['query'] = query
    result['limit'] = limit
    return success_response(result, message="Amazon sync completed")


def sync_walmart_products(platform, query, limit, category_slug=None):
    service = WalmartService()
    items = service.search_products(query, limit=limit)

    if not items:
        return error_response("No Walmart products found", code=404)

    query_words = set(query.replace('-', ' ').lower().split())

    normalized = []
    for item in items:
        try:
            product_data = service.extract_product_data(item)
            title_lower = (product_data.get('title') or '').lower()
            brand_lower = (product_data.get('brand') or '').lower()

            is_relevant = any(
                word in title_lower or word in brand_lower
                for word in query_words if len(word) > 2
            )
            if not is_relevant:
                continue

            normalized.append(product_data)
        except Exception:
            continue

    result = _generic_sync_loop(
        normalized, platform, 'external_id', save_generic_product_to_db,
        query=query,
        category_slug=category_slug
    )
    result['query'] = query
    result['limit'] = limit
    return success_response(result, message="Walmart sync completed")


def sync_sephora_products(platform, query, limit, category_slug=None):
    return _normalize_and_sync_generic(
        SephoraService(), platform, query, limit,
        success_msg="Sephora sync completed",
        not_found_msg="No Sephora products found",
        category_slug=category_slug,
    )


def sync_target_products(platform, query, limit, category_slug=None):
    return _normalize_and_sync_generic(
        TargetService(), platform, query, limit,
        success_msg="Target sync completed",
        not_found_msg="No Target products found",
        category_slug=category_slug,
    )


def sync_wayfair_products(platform, query, limit, category_slug=None):
    return _normalize_and_sync_generic(
        WayfairService(), platform, query, limit,
        success_msg="Wayfair sync completed",
        not_found_msg="No Wayfair products found",
        category_slug=category_slug,
    )


def sync_aliexpress_products(platform, query, limit, category_slug=None):
    return _normalize_and_sync_generic(
        AliExpressService(), platform, query, limit,
        success_msg="AliExpress sync completed",
        not_found_msg="No AliExpress products found",
        category_slug=category_slug,
    )


def sync_bestbuy_products(platform, query, limit, category_slug=None):
    return _normalize_and_sync_generic(
        BestBuyService(), platform, query, limit,
        success_msg="BestBuy sync completed",
        not_found_msg="No BestBuy products found",
        category_slug=category_slug,
    )


PLATFORM_SYNC_CONFIG = {
    'ebay':       {'sync_func': sync_ebay_products,       'name': 'eBay'},
    'amazon':     {'sync_func': sync_amazon_products,     'name': 'Amazon'},
    'walmart':    {'sync_func': sync_walmart_products,    'name': 'Walmart'},
    'sephora':    {'sync_func': sync_sephora_products,    'name': 'Sephora'},
    'target':     {'sync_func': sync_target_products,     'name': 'Target'},
    'wayfair':    {'sync_func': sync_wayfair_products,    'name': 'Wayfair'},
    'aliexpress': {'sync_func': sync_aliexpress_products, 'name': 'AliExpress'},
    'bestbuy':    {'sync_func': sync_bestbuy_products,    'name': 'BestBuy'},
}


def sync_all_platforms(query, limit, category_slug=None):
    enabled_platforms = Platform.objects.filter(api_enabled=True)
    all_results = {
        'query':                query,
        'platforms':            [],
        'total_synced':         0,
        'total_updated':        0,
        'total_failed':         0,
        'results_by_platform':  {},
    }

    for platform in enabled_platforms:
        sync_func = PLATFORM_SYNC_CONFIG.get(
            platform.code, {}).get('sync_func')
        if not sync_func:
            continue
        try:
            result = sync_func(platform, query, limit,
                               category_slug=category_slug)
            result_data = result.data.get('data', {})
            all_results['platforms'].append(platform.code)
            all_results['total_synced'] += result_data.get('synced', 0)
            all_results['total_updated'] += result_data.get('updated', 0)
            all_results['total_failed'] += result_data.get('failed', 0)
            all_results['results_by_platform'][platform.code] = result_data
        except Exception as e:
            logger.error(
                f"Failed to sync platform {platform.code}: {e}", exc_info=True)

    return success_response(all_results, message="All platforms synced")



# -------------------------- Multi-Platform Search and Live Sync API View --------------------------
@api_view(['GET'])
def search_and_sync(request):
    query = request.GET.get('q', '')
    category_slug = request.GET.get('category_slug', '') or query
    limit = min(int(request.GET.get('limit', 10)), 200)
    platform_code = request.GET.get('platform', 'amazon')

    if not query:
        return error_response('Query parameter "q" is required', code=400)

    if platform_code == 'all':
        return sync_all_platforms(query, limit, category_slug=category_slug)

    try:
        platform = Platform.objects.get(code=platform_code)
    except Platform.DoesNotExist:
        return error_response(f'Platform "{platform_code}" not found', code=404)

    sync_func = PLATFORM_SYNC_CONFIG.get(platform_code, {}).get('sync_func')
    if not sync_func:
        return error_response(f'Platform "{platform_code}" is not supported for sync', code=400)

    return sync_func(platform, query, limit, category_slug=category_slug)


# -------------------------- Smart Search & Real-Time Product Query View --------------------------
@api_view(['GET'])
def smart_search(request):
    query = request.GET.get('q', '')
    limit = min(int(request.GET.get('limit', 10)), 100)
    page = int(request.GET.get('page', 1))
    page_size = min(int(request.GET.get('page_size', 10)), 100)

    if not query:
        return error_response('q is required', code=400)

    favorite_ids = set()
    if request.user.is_authenticated:
        favorite_ids = set(
            Favorite.objects.filter(user=request.user)
            .values_list('product_id', flat=True)
        )

    user_id = request.user.id if request.user.is_authenticated else 'anon'
    cache_key = f'smart_search_v4_{query}_{limit}_{user_id}'
    cached = cache.get(cache_key)
    if cached:
        # Inject is_favorite into the cache results
        results_with_fav = [
            {**item, 'is_favorite': item['id'] in favorite_ids}
            for item in cached
        ]
        return success_response({
            'source':  'cache',
            'query':   query,
            'count':   len(cached),
            'results': paginate_results(results_with_fav, page, page_size),
            'pagination': get_pagination_meta(cached, page, page_size),
        }, message="Results from cache")

    # slug → words ("coins-currency" → ["coins", "currency"])
    search_terms = [t for t in query.replace('-', ' ').split() if len(t) > 2]

    title_q = Q()
    for term in search_terms:
        title_q &= Q(title__icontains=term)

    existing_products = Product.objects.filter(
        title_q,
        is_active=True,
        listings__is_available=True,
    ).prefetch_related(
        'listings__platform',
        'category',
    ).select_related('category').distinct()

    if existing_products.exists():
        sync_all_platforms_task.delay(query, limit)

        results = []
        for product in existing_products[:limit]:
            listings = product.listings.filter(
                is_available=True,
                price__gt=0
            ).select_related('platform').order_by('price')

            if not listings.exists():
                continue

            seen_urls = set()
            price_comparison = []

            for listing in listings:
                if listing.external_url in seen_urls:
                    continue
                seen_urls.add(listing.external_url)

                price_comparison.append({
                    'platform':            listing.platform.name,
                    'platform_code':       listing.platform.code,
                    'price':               float(listing.price),
                    'currency':            listing.currency,
                    'original_price':      float(listing.original_price) if listing.original_price else None,
                    'discount_percentage': float(listing.discount_percentage) if listing.discount_percentage else None,
                    'free_shipping':       listing.free_shipping,
                    'shipping_cost':       float(listing.shipping_cost),
                    'total_price':         float(listing.get_total_price()),
                    'url':                 listing.external_url,
                    'condition':           listing.condition,
                    'seller':              listing.seller_username,
                    'product_id':          product.id,
                    'product_title':       product.title,
                    'product_slug':        product.slug,
                    'main_image':          product.main_image,
                })

            valid_prices = [p for p in price_comparison if p['price'] > 0]
            if not valid_prices:
                continue

            valid_prices.sort(key=lambda x: x['total_price'])
            best_deal = min(valid_prices, key=lambda x: x['price'])
            platforms = list({p['platform_code'] for p in valid_prices})

            results.append({
                'id':              product.id,
                'title':           product.title,
                'slug':            product.slug,
                'main_image':      product.main_image,
                'category':        product.category_id,
                'category_name':   product.category.name if product.category else '',
                'platforms_count': len(platforms),
                'available_on':    platforms,
                'lowest_price':    best_deal['price'],
                'is_favorite':     product.id in favorite_ids,
                # 'best_deal': {
                #     'platform':      best_deal['platform'],
                #     'platform_code': best_deal['platform_code'],
                #     'price':         best_deal['price'],
                #     'url':           best_deal['url'],
                #     'free_shipping': best_deal['free_shipping'],
                # },
                # 'price_comparison': valid_prices,
            })

        results.sort(key=lambda x: x['lowest_price'] or 0)
        cache.set(cache_key, results, 300)

        return success_response({
            'source':     'database',
            'query':      query,
            'count':      len(results),
            'note':       'Background sync started for fresh data',
            'results':    paginate_results(results, page, page_size),
            'pagination': get_pagination_meta(results, page, page_size),
        }, message="Results from database")

    task = sync_all_platforms_task.delay(query, limit)
    return success_response({
        'source':        'syncing',
        'query':         query,
        'task_id':       task.id,
        'message':       'Data fetching started from all platforms',
        'check_status':  f'/api/v1/fetch-products/task-status/{task.id}/',
        'fetch_results': f'/api/v1/fetch-products/smart-search/?q={query}&limit={limit}',
    }, message="Sync started", code=202)


# ── Pagination Helper Functions ───────────────────────────────────────────────

def paginate_results(results: list, page: int, page_size: int) -> list:
    """Returns items from a specific page from the result list."""
    page = max(1, page)
    start = (page - 1) * page_size
    end = start + page_size
    return results[start:end]


def get_pagination_meta(results: list, page: int, page_size: int) -> dict:
    """Create pagination metadata."""
    total_count = len(results)
    total_pages = math.ceil(total_count / page_size) if page_size > 0 else 1
    page = max(1, page)

    return {
        'total_count':  total_count,
        'total_pages':  total_pages,
        'current_page': page,
        'page_size':    page_size,
        'has_next':     page < total_pages,
        'has_previous': page > 1,
        'next_page':    page + 1 if page < total_pages else None,
        'prev_page':    page - 1 if page > 1 else None,
    }


# -------------------------- Celery Asynchronous Sync Task Status Checker View --------------------------
@api_view(['GET'])
def task_status(request, task_id):
    from celery.result import AsyncResult
    result = AsyncResult(task_id)
    response_data = {'task_id': task_id, 'status': result.status}

    if result.status == 'SUCCESS':
        task_result = result.result or {}
        platform = task_result.get('platform', '')
        products = task_result.get('products', [])
        synced = task_result.get('synced', 0)
        updated = task_result.get('updated', 0)
        failed = task_result.get('failed', 0)

        response_data.update({
            'query':    request.GET.get('q', ''),
            'platform': platform,
            'limit':    len(products),
            'synced':   synced,
            'updated':  updated,
            'failed':   failed,
            'products': products,
            'message':  'Sync completed! Now fetch results.',
        })

    elif result.status == 'FAILURE':
        response_data['error'] = str(result.result)

    return success_response(response_data, message="Task status fetched")



# -------------------------- Bulk Product Ingestion & Platform Synchronizer API View --------------------------
@api_view(['POST'])
def bulk_sync_products(request):
    platform_code = request.data.get('platform')
    product_ids = request.data.get(
        'product_ids') or request.data.get('external_ids', [])

    if not platform_code or not product_ids:
        return error_response('Both "platform" and "product_ids" are required', code=400)

    try:
        platform = Platform.objects.get(code=platform_code)
    except Platform.DoesNotExist:
        return error_response(f'Platform "{platform_code}" not found', code=404)

    service_map = {
        'ebay':    EbayRapidService,
        'walmart': WalmartService,
        'amazon':  AmazonService,
        'sephora': SephoraService,
    }

    service_class = service_map.get(platform_code)
    if not service_class:
        return error_response(f'Platform "{platform_code}" not supported for bulk sync', code=400)

    service = service_class()
    result = {
        'platform': platform_code,
        'total':    len(product_ids),
        'synced':   0,
        'updated':  0,
        'failed':   0,
        'products': [],
    }

    for external_id in product_ids:
        try:
            hits = service.search_products(str(external_id), limit=1)
            if not hits:
                result['failed'] += 1
                continue

            product_data = service.extract_product_data(hits[0])
            product_data['external_id'] = external_id

            with transaction.atomic():
                product, listing, created = save_generic_product_to_db(
                    product_data, platform
                )

            if product and listing:
                if created:
                    result['synced'] += 1
                else:
                    result['updated'] += 1
                result['products'].append({
                    'id':           product.id,
                    'title':        product.title,
                    'slug':         product.slug,
                    'external_id':  external_id,
                    'price':        float(listing.price),
                    'currency':     listing.currency,
                    'external_url': listing.external_url,
                    'main_image':   product.main_image,
                    'status':       'created' if created else 'updated',
                })
            else:
                result['failed'] += 1

        except Exception as e:
            result['failed'] += 1
            logger.error(
                f"Bulk sync failed for {external_id}: {e}", exc_info=True)

    return success_response(result, message="Bulk sync completed")


# -------------------------- Retailer Platform External Product ID Extractor View --------------------------
@api_view(['GET'])
def get_external_ids(request):
    query = request.GET.get('q', '')
    limit = min(int(request.GET.get('limit', 10)), 50)
    platform_code = request.GET.get('platform', 'ebay')

    if not query:
        return error_response('Query parameter "q" is required', code=400)

    platform_config = {
        'ebay':    (EbayRapidService, 'external_id'),
        'walmart': (WalmartService,   'usItemId'),
        'amazon':  (AmazonService,    'asin'),
        'sephora': (SephoraService,   'external_id'),
    }

    if platform_code == 'all':
        all_items = {}
        for code, (ServiceClass, id_key) in platform_config.items():
            try:
                svc = ServiceClass()
                items = svc.search_products(query, limit=limit) or []
                for item in items:
                    d = svc.extract_product_data(item) if hasattr(
                        svc, 'extract_product_data') else item
                    all_items.setdefault(code, []).append({
                        'external_id': d.get('external_id') or d.get(id_key, ''),
                        'title':       d.get('title') or d.get('name'),
                        'price':       d.get('price', 0),
                        'url':         d.get('external_url') or d.get('url', ''),
                        'image':       d.get('main_image') or d.get('image', ''),
                    })
            except Exception as e:
                logger.error(f"{code} search failed: {e}")

        return success_response({
            'query':   query,
            'results': all_items,
        }, message="External IDs fetched")

    if platform_code not in platform_config:
        return error_response(f'Platform "{platform_code}" not supported', code=400)

    ServiceClass, id_key = platform_config[platform_code]
    service = ServiceClass()
    raw_items = service.search_products(query, limit=limit) or []

    items_detail = []
    for item in raw_items:
        d = service.extract_product_data(item) if hasattr(
            service, 'extract_product_data') else item
        items_detail.append({
            'external_id': d.get('external_id') or d.get(id_key, ''),
            'title':       d.get('title') or d.get('name'),
            'price':       d.get('price', 0),
            'url':         d.get('external_url') or d.get('url', ''),
            'image':       d.get('main_image') or d.get('image', ''),
        })

    return success_response({
        'query':          query,
        'platform':       platform_code,
        'items_returned': len(items_detail),
        'items':          items_detail,
    }, message="External IDs fetched")

