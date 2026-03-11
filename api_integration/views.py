import time
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q, Min, Count, Avg
from django.db import transaction

from api_integration.services.walmart_service import WalmartService
from api_integration.services.amazon_service import AmazonService
from api_integration.services.shopify_service import ShopifyService
from api_integration.services.homedepot_service import HomeDepotService
from .models import (
    Product, ProductListing, Platform, Category,
    PriceHistory, ProductImage, ProductSpecification,
    CartItem, SavingsActivity
)
from .serializers import (
    ProductSerializer,
    ProductDetailSerializer,
    ProductListingSerializer,
    PlatformSerializer,
    CategorySerializer,
    PriceHistorySerializer,
    CartItemSerializer,
)
from .services.ebay_service import EbayService
from .services.clickbank_service import ClickBankService
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

logger = logging.getLogger(__name__)


# ============================================================================
# Standardized Response Helpers
# ============================================================================

def success_response(data=None, message="Success", code=200):
    return Response({
        "success": True,
        "code": code,
        "message": message,
        "timestamp": int(time.time()),
        "data": data or {}
    }, status=code)


def error_response(message="Error", data=None, code=400):
    return Response({
        "success": False,
        "code": code,
        "message": message,
        "timestamp": int(time.time()),
        "data": data or {}
    }, status=code)


# ============================================================================
# DB Save Helpers
# ============================================================================

def save_clickbank_product_to_db(product_data, platform):
    brand = (product_data.get('brand') or '').strip()
    model_number = (product_data.get('model_number') or '').strip()

    product = None
    if brand and model_number:
        product = Product.objects.filter(
            brand__iexact=brand, model_number__iexact=model_number
        ).first()

    if not product:
        product, _ = Product.objects.get_or_create(
            title=product_data.get('title', 'Unknown Product'),
            defaults={
                'description': product_data.get('description', '') or '',
                'brand': brand,
                'model_number': model_number,
                'main_image': product_data.get('main_image', '') or '',
            }
        )

    shipping_info = product_data.get('shipping_info', {})

    listing, created = ProductListing.objects.update_or_create(
        product=product,
        platform=platform,
        external_id=product_data.get('external_id'),
        defaults={
            'external_url': product_data.get('external_url', ''),
            'price': product_data.get('price', 0),
            'currency': product_data.get('currency', 'USD'),
            'condition': product_data.get('condition', 'NEW'),
            'quantity': product_data.get('quantity', 0),
            'seller_username': product_data.get('seller_username', ''),
            'seller_rating': product_data.get('seller_rating'),
            'item_location': product_data.get('item_location', ''),
            'shipping_cost': shipping_info.get('cost', 0),
            'shipping_currency': shipping_info.get('currency', 'USD'),
            'free_shipping': shipping_info.get('free_shipping', False),
            'estimated_delivery_days': shipping_info.get('estimated_days'),
            'returns_accepted': product_data.get('returns_accepted', False),
            'return_period_days': product_data.get('return_period_days'),
            'is_available': product_data.get('is_available', True),
        }
    )

    if product_data.get('specifications'):
        ProductSpecification.objects.filter(product=product).delete()
        for name, value in product_data['specifications'].items():
            ProductSpecification.objects.create(product=product, name=name, value=value)

    if created:
        PriceHistory.objects.create(
            listing=listing, price=listing.price, currency=listing.currency
        )

    return product, listing, created


def save_ebay_product_to_db(item_data, platform):
    ebay_service = EbayService()
    item_id = item_data.get('itemId')
    detailed_item = ebay_service.get_item_details(item_id)

    if not detailed_item:
        return None, None, False

    product_data = ebay_service.extract_product_data(detailed_item)

    brand = (product_data.get('brand') or '').strip()
    model_number = (product_data.get('model_number') or '').strip()

    product = None
    if brand and model_number:
        product = Product.objects.filter(
            brand__iexact=brand, model_number__iexact=model_number
        ).first()

    if not product:
        product, _ = Product.objects.get_or_create(
            title=product_data.get('title', 'Unknown Product'),
            defaults={
                'description': product_data.get('description', '') or '',
                'brand': brand,
                'model_number': model_number,
                'main_image': product_data.get('main_image', '') or '',
            }
        )

    shipping_info = product_data.get('shipping_info', {})

    listing, listing_created = ProductListing.objects.update_or_create(
        product=product,
        platform=platform,
        external_id=product_data.get('external_id'),
        defaults={
            'external_url': product_data.get('external_url', ''),
            'price': product_data.get('price', 0),
            'currency': product_data.get('currency', 'USD'),
            'original_price': product_data.get('original_price'),
            'discount_percentage': product_data.get('discount_percentage'),
            'condition': product_data.get('condition', 'NEW'),
            'quantity': product_data.get('quantity', 0),
            'seller_username': product_data.get('seller_username', ''),
            'seller_rating': product_data.get('seller_rating'),
            'seller_feedback_count': product_data.get('seller_feedback_count', 0),
            'item_location': product_data.get('item_location', ''),
            'ships_from_country': product_data.get('ships_from_country', ''),
            'shipping_cost': shipping_info.get('cost', 0),
            'shipping_currency': shipping_info.get('currency', 'USD'),
            'free_shipping': shipping_info.get('free_shipping', False),
            'estimated_delivery_days': shipping_info.get('estimated_days'),
            'returns_accepted': product_data.get('returns_accepted', False),
            'return_period_days': product_data.get('return_period_days'),
            'is_available': product_data.get('is_available', True),
        }
    )

    if listing_created:
        PriceHistory.objects.create(
            listing=listing, price=listing.price, currency=listing.currency
        )
    else:
        last_history = listing.price_history.order_by('-recorded_at').first()
        if not last_history or last_history.price != listing.price:
            PriceHistory.objects.create(
                listing=listing, price=listing.price, currency=listing.currency
            )

    if product_data.get('additional_images'):
        ProductImage.objects.filter(product=product).delete()
        for order, image_url in enumerate(product_data['additional_images'][:10]):
            ProductImage.objects.create(product=product, image_url=image_url, order=order)

    if product_data.get('specifications'):
        ProductSpecification.objects.filter(product=product).delete()
        for name, value in product_data['specifications'].items():
            ProductSpecification.objects.create(product=product, name=name, value=value)

    return product, listing, listing_created


def save_generic_product_to_db(product_data, platform):
    """
    Universal save helper — for all platforms like Amazon, Walmart, Shopify, HomeDepot.
    Saves shipping_info, seller fields in product_data if they are present.
    """
    brand = (product_data.get('brand') or '').strip()
    model_number = (product_data.get('model_number') or '').strip()

    # ── Product match / create ────────────────────────────────────────────
    product = None
    if brand and model_number:
        product = Product.objects.filter(
            brand__iexact=brand, model_number__iexact=model_number
        ).first()

    if not product:
        product, _ = Product.objects.get_or_create(
            title=product_data.get('title', 'Unknown'),
            defaults={
                'description': product_data.get('description', '') or '',
                'brand': brand,
                'model_number': model_number,
                'main_image': product_data.get('main_image') or '',
            }
        )
    else:
        # existing product image update koro jodi nai thake
        if not product.main_image and product_data.get('main_image'):
            product.main_image = product_data['main_image']
            product.save(update_fields=['main_image'])

    # ── Shipping info ────────────────────────────────────────────────────
    shipping_info = product_data.get('shipping_info', {}) or {}

    # ── Listing update_or_create ──────────────────────────────────────────
    listing, created = ProductListing.objects.update_or_create(
        product=product,
        platform=platform,
        external_id=product_data.get('external_id'),
        defaults={
            'external_url': product_data.get('external_url', ''),
            'price': product_data.get('price', 0) or 0,
            'currency': product_data.get('currency', 'USD'),
            'original_price': product_data.get('original_price'),
            'discount_percentage': product_data.get('discount_percentage'),
            'condition': product_data.get('condition', 'NEW'),
            'quantity': int(product_data.get('quantity') or 0),
            'seller_username': product_data.get('seller_username', '') or '',
            'seller_rating': product_data.get('seller_rating'),
            'seller_feedback_count': int(product_data.get('seller_feedback_count') or 0),
            'item_location': product_data.get('item_location', '') or '',
            'ships_from_country': product_data.get('ships_from_country', '') or '',
            'shipping_cost': shipping_info.get('cost', 0) or 0,
            'shipping_currency': shipping_info.get('currency', 'USD'),
            'free_shipping': bool(shipping_info.get('free_shipping', False)),
            'estimated_delivery_days': shipping_info.get('estimated_days'),
            'returns_accepted': bool(product_data.get('returns_accepted', False)),
            'return_period_days': product_data.get('return_period_days'),
            'is_available': bool(product_data.get('is_available', True)),
        }
    )

    # ── Price history ────────────────────────────────────────────────────
    if created:
        PriceHistory.objects.create(
            listing=listing, price=listing.price, currency=listing.currency
        )
    else:
        last_history = listing.price_history.order_by('-recorded_at').first()
        if not last_history or last_history.price != listing.price:
            PriceHistory.objects.create(
                listing=listing, price=listing.price, currency=listing.currency
            )

    # ── Additional images ────────────────────────────────────────────────
    if product_data.get('additional_images'):
        ProductImage.objects.filter(product=product).delete()
        for order, image_url in enumerate(product_data['additional_images'][:10]):
            if image_url:
                ProductImage.objects.create(product=product, image_url=image_url, order=order)

    # ── Specifications ───────────────────────────────────────────────────
    if product_data.get('specifications'):
        ProductSpecification.objects.filter(product=product).delete()
        for name, value in product_data['specifications'].items():
            ProductSpecification.objects.create(product=product, name=name, value=str(value))

    return product, listing, created


# ============================================================================
# Platform-specific sync helpers
# ============================================================================

def _build_result_template(query, platform_code, limit):
    return {
        'query': query,
        'platform': platform_code,
        'limit': limit,
        'synced': 0,
        'updated': 0,
        'failed': 0,
        'products': [],
        'external_ids': [],
    }


def _generic_sync_loop(items, platform, external_id_key, save_callable):
    result = _build_result_template('', platform.code, 0)

    for item in items:
        external_id = item.get(external_id_key)
        result['external_ids'].append(external_id)
        logger.debug(f"Syncing {platform.code} item {external_id}")

        try:
            with transaction.atomic():
                product, listing, created = save_callable(item, platform)

                if product and listing:
                    if created:
                        result['synced'] += 1
                    else:
                        result['updated'] += 1

                    result['products'].append({
                        'product_id': product.id,
                        'listing_id': listing.id,
                        'external_id': external_id,
                        'title': product.title,
                        'slug': product.slug,
                        'price': float(listing.price),
                        'currency': listing.currency,
                        'status': 'created' if created else 'updated',
                    })
                else:
                    result['failed'] += 1
                    logger.warning(f"No product/listing returned for {platform.code} item {external_id}")

        except Exception as e:
            result['failed'] += 1
            logger.error(f"Failed to sync {platform.code} item {external_id}: {e}", exc_info=True)

    return result


def sync_ebay_products(platform, query, limit):
    ebay_service = EbayService()
    search_results = ebay_service.search_products(query, limit=limit)

    if not search_results:
        return error_response("Failed to fetch products from eBay", code=500)

    items = search_results.get('itemSummaries', [])
    result = _generic_sync_loop(items, platform, 'itemId', save_ebay_product_to_db)
    result['query'] = query
    result['limit'] = limit
    return success_response(result, message="eBay sync completed")


def sync_clickbank_products(platform, query, limit):
    clickbank_service = ClickBankService()
    search_results = clickbank_service.search_mock_products(query, limit)

    if not search_results:
        return error_response("No ClickBank products found", code=404)

    normalized_items = []
    for item in search_results:
        try:
            normalized_items.append(clickbank_service.extract_product_data(item))
        except Exception:
            continue

    result = _generic_sync_loop(normalized_items, platform, 'external_id', save_clickbank_product_to_db)
    result['query'] = query
    result['limit'] = limit
    return success_response(result, message="ClickBank sync completed")


def sync_walmart_products(platform, query, limit):
    service = WalmartService()
    items = service.search_products(query, limit=limit)

    if not items:
        return error_response("No Walmart products found", code=404)

    normalized = []
    for item in items:
        try:
            normalized.append(service.extract_product_data(item))
        except Exception:
            continue

    result = _generic_sync_loop(normalized, platform, 'external_id', save_generic_product_to_db)
    result['query'] = query
    result['limit'] = limit
    return success_response(result, message="Walmart sync completed")


def sync_amazon_products(platform, query, limit):
    service = AmazonService()
    items = service.search_products(query, limit=limit)

    if items is None:
        return error_response("Amazon search failed", code=500)

    if not items:
        return success_response(
            _build_result_template(query, 'amazon', limit),
            message="No Amazon products found"
        )

    normalized = []
    for item in items:
        try:
            normalized.append(service.extract_product_data(item))
        except Exception:
            continue

    result = _generic_sync_loop(normalized, platform, 'external_id', save_generic_product_to_db)
    result['query'] = query
    result['limit'] = limit
    return success_response(result, message="Amazon sync completed")


def sync_shopify_products(platform, query, limit):
    service = ShopifyService()
    items = service.search_products(query, limit=limit)

    if not items:
        return error_response("No Shopify products found", code=404)

    normalized = []
    for item in items:
        try:
            normalized.append(service.extract_product_data(item, store_url=query))
        except Exception:
            continue

    result = _generic_sync_loop(normalized, platform, 'external_id', save_generic_product_to_db)
    result['query'] = query
    result['limit'] = limit
    return success_response(result, message="Shopify sync completed")


def sync_homedepot_products(platform, query, limit):
    """
    Home Depot sync — শুধু numeric productId দিয়ে কাজ করে।
    Text query এলে skip করে।
    """
    service = HomeDepotService()

    if not str(query).strip().isdigit():
        # Text query returns empty success (will skip hourly sync)
        logger.info(f"HomeDepot skipped for non-numeric query: '{query}'")
        result = _build_result_template(query, 'homedepot', limit)
        result['note'] = 'HomeDepot requires numeric productId — text query skipped'
        return success_response(result, message="Home Depot sync skipped (non-numeric query)")

    items = service.search_products(query, limit=limit)

    if not items:
        return error_response("No Home Depot products found", code=404)

    normalized = []
    for item in items:
        try:
            normalized.append(service.extract_product_data(item))
        except Exception:
            continue

    result = _generic_sync_loop(normalized, platform, 'external_id', save_generic_product_to_db)
    result['query'] = query
    result['limit'] = limit
    return success_response(result, message="Home Depot sync completed")


# ── Register sync functions ──────────────────────────────────────────────────
PLATFORM_SYNC_CONFIG = {
    'ebay':      {'sync_func': sync_ebay_products,      'name': 'eBay'},
    'clickbank': {'sync_func': sync_clickbank_products,  'name': 'ClickBank'},
    'walmart':   {'sync_func': sync_walmart_products,    'name': 'Walmart'},
    'amazon':    {'sync_func': sync_amazon_products,     'name': 'Amazon'},
    'shopify':   {'sync_func': sync_shopify_products,    'name': 'Shopify'},
    'homedepot': {'sync_func': sync_homedepot_products,  'name': 'Home Depot'},
}


def sync_all_platforms(query, limit):
    """Sync from ALL enabled platforms in sequence."""
    enabled_platforms = Platform.objects.filter(api_enabled=True)

    all_results = {
        'query': query,
        'platforms': [],
        'total_synced': 0,
        'total_updated': 0,
        'total_failed': 0,
        'results_by_platform': {},
    }

    for platform in enabled_platforms:
        sync_func = PLATFORM_SYNC_CONFIG.get(platform.code, {}).get('sync_func')
        if not sync_func:
            continue

        try:
            result = sync_func(platform, query, limit)
            result_data = result.data.get('data', {})
            all_results['platforms'].append(platform.code)
            all_results['total_synced'] += result_data.get('synced', 0)
            all_results['total_updated'] += result_data.get('updated', 0)
            all_results['total_failed'] += result_data.get('failed', 0)
            all_results['results_by_platform'][platform.code] = result_data
        except Exception as e:
            logger.error(f"Failed to sync platform {platform.code}: {e}", exc_info=True)

    return success_response(all_results, message="All platforms synced")


# ============================================================================
# Pagination
# ============================================================================

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# ============================================================================
# REST API ViewSets
# ============================================================================

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.filter(is_active=True).prefetch_related(
        'listings', 'images', 'specifications'
    )
    serializer_class = ProductSerializer
    pagination_class = StandardResultsSetPagination
    lookup_field = 'slug'

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ProductDetailSerializer
        return ProductSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category__slug=category)

        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        if min_price:
            queryset = queryset.filter(listings__price__gte=min_price)
        if max_price:
            queryset = queryset.filter(listings__price__lte=max_price)

        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(brand__icontains=search)
            )

        sort = self.request.query_params.get('sort', '-created_at')
        if sort == 'price_low':
            queryset = queryset.annotate(sort_price=Min('listings__price')).order_by('sort_price')
        elif sort == 'price_high':
            queryset = queryset.annotate(sort_price=Min('listings__price')).order_by('-sort_price')
        elif sort == 'newest':
            queryset = queryset.order_by('-created_at')
        elif sort == 'popular':
            queryset = queryset.annotate(listing_count=Count('listings')).order_by('-listing_count')
        else:
            queryset = queryset.order_by(sort)

        return queryset.distinct()

    @action(detail=True, methods=['get'])
    def compare_prices(self, request, slug=None):
        product = self.get_object()
        listings = product.listings.filter(is_available=True).select_related('platform')

        comparison_data = {
            'product': {
                'id': product.id,
                'title': product.title,
                'slug': product.slug,
                'brand': product.brand,
                'main_image': product.main_image,
            },
            'price_comparison': [],
        }

        for listing in listings:
            comparison_data['price_comparison'].append({
                'platform': listing.platform.name,
                'platform_code': listing.platform.code,
                'price': float(listing.price),
                'currency': listing.currency,
                'shipping_cost': float(listing.shipping_cost),
                'free_shipping': listing.free_shipping,
                'total_price': float(listing.get_total_price()),
                'condition': listing.condition,
                'seller': listing.seller_username,
                'seller_rating': float(listing.seller_rating) if listing.seller_rating else None,
                'url': listing.external_url,
                'last_updated': listing.last_checked,
            })

        comparison_data['price_comparison'].sort(key=lambda x: x['total_price'])
        comparison_data['best_deal'] = (
            comparison_data['price_comparison'][0]
            if comparison_data['price_comparison'] else None
        )

        return success_response(comparison_data, message="Price comparison fetched")


class ProductListingViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ProductListing.objects.filter(
        is_available=True
    ).select_related('product', 'platform')
    serializer_class = ProductListingSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = super().get_queryset()

        platform = self.request.query_params.get('platform')
        if platform and platform != 'all':
            queryset = queryset.filter(platform__code=platform)

        condition = self.request.query_params.get('condition')
        if condition:
            queryset = queryset.filter(condition=condition)

        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        if min_price:
            queryset = queryset.filter(price__gte=min_price)
        if max_price:
            queryset = queryset.filter(price__lte=max_price)

        sort = self.request.query_params.get('sort', 'price')
        queryset = queryset.order_by(sort)

        return queryset


class PlatformViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Platform.objects.filter(api_enabled=True)
    serializer_class = PlatformSerializer
    lookup_field = 'code'


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    lookup_field = 'slug'


# ============================================================================
# Custom API Endpoints
# ============================================================================

@api_view(['GET'])
def search_and_sync(request):
    query = request.GET.get('q', '')
    limit = min(int(request.GET.get('limit', 10)), 50)
    platform_code = request.GET.get('platform', 'ebay')

    if not query:
        return error_response('Query parameter "q" is required', code=400)

    if platform_code == 'all':
        return sync_all_platforms(query, limit)

    try:
        platform = Platform.objects.get(code=platform_code)
    except Platform.DoesNotExist:
        return error_response(f'Platform "{platform_code}" not found', code=404)

    sync_func = PLATFORM_SYNC_CONFIG.get(platform_code, {}).get('sync_func')
    if not sync_func:
        return error_response(f'Platform "{platform_code}" is not supported for sync', code=400)

    return sync_func(platform, query, limit)


@api_view(['POST'])
def bulk_sync_products(request):
    platform_code = request.data.get('platform')
    product_ids = request.data.get('product_ids') or request.data.get('external_ids', [])

    if not platform_code or not product_ids:
        return error_response('Both "platform" and "product_ids" are required', code=400)

    try:
        platform = Platform.objects.get(code=platform_code)
    except Platform.DoesNotExist:
        return error_response(f'Platform "{platform_code}" not found', code=404)

    service_map = {
        'ebay': EbayService,
        'clickbank': ClickBankService,
        'walmart': WalmartService,
        'amazon': AmazonService,
        'shopify': ShopifyService,
        'homedepot': HomeDepotService,
    }

    service_class = service_map.get(platform_code)
    if not service_class:
        return error_response(f'Platform "{platform_code}" not supported for bulk sync', code=400)

    service = service_class()

    result = {
        'platform': platform_code,
        'total': len(product_ids),
        'synced': 0,
        'updated': 0,
        'failed': 0,
        'products': [],
    }

    for external_id in product_ids:
        try:
            if platform_code == 'ebay':
                item_data = service.get_item_details(external_id)
                if not item_data:
                    result['failed'] += 1
                    continue
                with transaction.atomic():
                    product, listing, created = save_ebay_product_to_db(item_data, platform)

            elif platform_code == 'clickbank':
                item_data = service.get_product_details(external_id)
                if not item_data:
                    result['failed'] += 1
                    continue
                product_data = service.extract_product_data(item_data)
                with transaction.atomic():
                    product, listing, created = save_clickbank_product_to_db(product_data, platform)

            else:
                # walmart, amazon, shopify, homedepot — search by ID then save
                hits = service.search_products(str(external_id), limit=1)
                if not hits:
                    result['failed'] += 1
                    continue
                product_data = service.extract_product_data(hits[0])
                with transaction.atomic():
                    product, listing, created = save_generic_product_to_db(product_data, platform)

            if product and listing:
                if created:
                    result['synced'] += 1
                else:
                    result['updated'] += 1
                result['products'].append({
                    'id': product.id,
                    'title': product.title,
                    'slug': product.slug,
                    'external_id': external_id,
                    'status': 'created' if created else 'updated',
                })
            else:
                result['failed'] += 1

        except Exception as e:
            result['failed'] += 1
            logger.error(f"Failed to bulk sync {external_id}: {e}", exc_info=True)

    return success_response(result, message="Bulk sync completed")


@api_view(['POST'])
def sync_from_search_results(request):
    query = request.data.get('query', '')
    limit = min(int(request.data.get('limit', 10)), 50)
    platform_code = request.data.get('platform', 'ebay')

    if not query:
        return error_response('Query is required', code=400)

    try:
        platform = Platform.objects.get(code=platform_code)
    except Platform.DoesNotExist:
        return error_response(f'Platform "{platform_code}" not found', code=404)

    if platform_code == 'ebay':
        service = EbayService()
        search_results = service.search_products(query, limit=limit)
        items = search_results.get('itemSummaries', []) if search_results else []
        id_key = 'itemId'

    elif platform_code == 'clickbank':
        service = ClickBankService()
        items = service.search_mock_products(query, limit)
        id_key = 'site'
        search_results = {'total': len(items)}

    elif platform_code == 'walmart':
        service = WalmartService()
        items = service.search_products(query, limit=limit)
        id_key = 'itemId'
        search_results = {'total': len(items)}

    elif platform_code == 'amazon':
        service = AmazonService()
        items = service.search_products(query, limit=limit)
        id_key = 'asin'
        search_results = {'total': len(items)}

    elif platform_code == 'shopify':
        service = ShopifyService()
        items = service.search_products(query, limit=limit)
        id_key = 'id'
        search_results = {'total': len(items)}

    else:
        return error_response(f'Platform "{platform_code}" sync not implemented', code=501)

    result = {
        'query': query,
        'platform': platform_code,
        'total_found': search_results.get('total', len(items)) if isinstance(search_results, dict) else len(items),
        'items_fetched': len(items),
        'synced': 0,
        'updated': 0,
        'skipped': 0,
        'failed': 0,
        'products': [],
        'external_ids': [],
    }

    for item in items:
        external_id = item.get(id_key)
        result['external_ids'].append(external_id)

        try:
            existing = ProductListing.objects.filter(
                platform=platform, external_id=external_id
            ).first()

            if existing:
                result['skipped'] += 1
                result['products'].append({
                    'product_id': existing.product.id,
                    'listing_id': existing.id,
                    'external_id': external_id,
                    'title': existing.product.title,
                    'price': float(existing.price),
                    'currency': existing.currency,
                    'status': 'already_exists',
                })
                continue

            with transaction.atomic():
                if platform_code == 'ebay':
                    product, listing, created = save_ebay_product_to_db(item, platform)
                elif platform_code == 'clickbank':
                    product_data = service.extract_product_data(item)
                    product, listing, created = save_clickbank_product_to_db(product_data, platform)
                else:
                    product_data = service.extract_product_data(item)
                    product, listing, created = save_generic_product_to_db(product_data, platform)

            if product and listing:
                status_text = 'created' if created else 'updated'
                if created:
                    result['synced'] += 1
                else:
                    result['updated'] += 1

                result['products'].append({
                    'product_id': product.id,
                    'listing_id': listing.id,
                    'external_id': external_id,
                    'title': product.title,
                    'slug': product.slug,
                    'price': float(listing.price),
                    'currency': listing.currency,
                    'seller': listing.seller_username,
                    'condition': listing.condition,
                    'status': status_text,
                })
            else:
                result['failed'] += 1

        except Exception as e:
            result['failed'] += 1
            logger.error(f"Failed to sync {external_id}: {e}", exc_info=True)

    return success_response(result, message="Sync from search completed")


@api_view(['GET'])
def get_external_ids(request):
    query = request.GET.get('q', '')
    limit = min(int(request.GET.get('limit', 10)), 50)
    platform_code = request.GET.get('platform', 'ebay')

    if not query:
        return error_response('Query parameter "q" is required', code=400)

    if platform_code == 'all':
        all_items = []
        errors = {}

        # ── eBay ─────────────────────────────────────────────────────────────
        try:
            ebay_service = EbayService()
            ebay_results = ebay_service.search_products(query, limit=limit)
            for item in (ebay_results.get('itemSummaries', []) if ebay_results else []):
                all_items.append({
                    'external_id': item.get('itemId'),
                    'platform': 'ebay',
                    'title': item.get('title'),
                    'price': item.get('price', {}).get('value'),
                    'currency': item.get('price', {}).get('currency', 'USD'),
                    'condition': item.get('condition'),
                    'url': item.get('itemWebUrl'),
                })
        except Exception as e:
            logger.error(f"eBay search failed: {e}")
            errors['ebay'] = str(e)

        # ── ClickBank ─────────────────────────────────────────────────────────
        try:
            cb_service = ClickBankService()
            for item in cb_service.search_mock_products(query, limit):
                all_items.append({
                    'external_id': item.get('site'),
                    'platform': 'clickbank',
                    'title': item.get('title'),
                    'price': item.get('price'),
                    'currency': 'USD',
                    'condition': 'NEW',
                    'url': item.get('url'),
                })
        except Exception as e:
            logger.error(f"ClickBank search failed: {e}")
            errors['clickbank'] = str(e)

        # ── Amazon ────────────────────────────────────────────────────────────
        try:
            amazon_service = AmazonService()
            amazon_items = amazon_service.search_products(query, limit=limit)
            for item in (amazon_items or []):
                price_raw = item.get('product_price') or item.get('price') or '0'
                try:
                    price_val = float(str(price_raw).replace('$', '').replace(',', '').strip())
                except (ValueError, TypeError):
                    price_val = 0.0
                all_items.append({
                    'external_id': item.get('asin'),
                    'platform': 'amazon',
                    'title': item.get('product_title') or item.get('title'),
                    'price': price_val,
                    'currency': 'USD',
                    'condition': 'NEW',
                    'url': item.get('product_url') or item.get('url'),
                    'image': item.get('product_photo') or item.get('thumbnail'),
                    'rating': item.get('product_star_rating'),
                })
        except Exception as e:
            logger.error(f"Amazon search failed: {e}")
            errors['amazon'] = str(e)

        # ── Walmart ───────────────────────────────────────────────────────────
        try:
            walmart_service = WalmartService()
            walmart_items = walmart_service.search_products(query, limit=limit)
            for item in (walmart_items or []):
                all_items.append({
                    'external_id': str(item.get('itemId') or item.get('external_id') or ''),
                    'platform': 'walmart',
                    'title': item.get('name') or item.get('title'),
                    'price': item.get('salePrice') or item.get('price') or 0,
                    'currency': 'USD',
                    'condition': 'NEW',
                    'url': item.get('productUrl') or item.get('external_url'),
                    'image': item.get('thumbnailImage') or item.get('main_image'),
                })
        except Exception as e:
            logger.error(f"Walmart search failed: {e}")
            errors['walmart'] = str(e)

        # ── Shopify ───────────────────────────────────────────────────────────
        try:
            shopify_service = ShopifyService()
            shopify_items = shopify_service.search_products(query, limit=limit)
            for item in (shopify_items or []):
                variants = item.get('variants', [])
                price_val = 0.0
                if variants:
                    try:
                        price_val = float(variants[0].get('price', 0) or 0)
                    except (ValueError, TypeError):
                        price_val = 0.0
                images = item.get('images', [])
                main_image = images[0].get('src', '') if images else ''
                all_items.append({
                    'external_id': str(item.get('id') or ''),
                    'platform': 'shopify',
                    'title': item.get('title'),
                    'price': price_val,
                    'currency': 'USD',
                    'condition': 'NEW',
                    'url': f"{shopify_service.default_store}/products/{item.get('handle', '')}",
                    'image': main_image,
                    'vendor': item.get('vendor'),
                })
        except Exception as e:
            logger.error(f"Shopify search failed: {e}")
            errors['shopify'] = str(e)

        response_data = {
            'query': query,
            'platform': 'all',
            'items_returned': len(all_items),
            'items': all_items,
        }
        if errors:
            response_data['platform_errors'] = errors

        return success_response(response_data, message="External IDs fetched")

    # Single platform
    platform_config = {
        'ebay':      (EbayService,      'itemId',  lambda s, q, l: (s.search_products(q, limit=l).get('itemSummaries', []) if s.search_products(q, limit=l) else [], {})),
        'clickbank': (ClickBankService, 'site',    lambda s, q, l: (s.search_mock_products(q, l), {})),
        'walmart':   (WalmartService,   'itemId',  lambda s, q, l: (s.search_products(q, limit=l), {})),
        'amazon':    (AmazonService,    'asin',    lambda s, q, l: (s.search_products(q, limit=l), {})),
        'shopify':   (ShopifyService,   'id',      lambda s, q, l: (s.search_products(q, limit=l), {})),
    }

    if platform_code not in platform_config:
        return error_response(f'Platform "{platform_code}" not supported', code=400)

    service_class, id_key, fetch_fn = platform_config[platform_code]
    service = service_class()

    if platform_code == 'ebay':
        search_results = service.search_products(query, limit=limit)
        items = search_results.get('itemSummaries', []) if search_results else []
    elif platform_code == 'clickbank':
        items = service.search_mock_products(query, limit)
        search_results = {'total': len(items)}
    elif platform_code == 'walmart':
        items = service.search_products(query, limit=limit)
        search_results = {'total': len(items)}
    elif platform_code == 'amazon':
        items = service.search_products(query, limit=limit)
        search_results = {'total': len(items)}
    elif platform_code == 'shopify':
        items = service.search_products(query, limit=limit)
        search_results = {'total': len(items)}

    external_ids = []
    items_detail = []

    for item in items:
        item_id = item.get(id_key)
        external_ids.append(item_id)
        items_detail.append({
            'external_id': item_id,
            'title': item.get('title'),
            'categories': item.get('categories', []),
            'price': item.get('price', {}).get('value') if platform_code == 'ebay' else item.get('price'),
            'currency': item.get('price', {}).get('currency') if platform_code == 'ebay' else 'USD',
            'condition': item.get('condition'),
            'url': item.get('itemWebUrl') if platform_code == 'ebay' else item.get('url'),
        })

    return success_response({
        'query': query,
        'platform': platform_code,
        'total_found': search_results.get('total', len(items)) if isinstance(search_results, dict) else len(items),
        'items_returned': len(items),
        'external_ids': external_ids,
        'items': items_detail,
        'bulk_sync_body': {
            'platform': platform_code,
            'product_ids': external_ids,
        },
    }, message="External IDs fetched")


@api_view(['GET'])
def product_price_history(request, slug):
    try:
        product = Product.objects.get(slug=slug)
    except Product.DoesNotExist:
        return error_response('Product not found', code=404)

    listings = product.listings.all()
    history_data = []

    for listing in listings:
        for history in listing.price_history.order_by('-recorded_at'):
            history_data.append({
                'platform': listing.platform.name,
                'platform_code': listing.platform.code,
                'price': float(history.price),
                'currency': history.currency,
                'recorded_at': history.recorded_at,
            })

    history_data.sort(key=lambda x: x['recorded_at'], reverse=True)

    return success_response({
        'product': product.title,
        'slug': product.slug,
        'total_records': len(history_data),
        'price_history': history_data,
    }, message="Price history fetched")


from .tasks import sync_all_platforms_task, sync_ebay_task, sync_clickbank_task
from django.core.cache import cache


@api_view(['GET'])
def smart_search(request):
    query = request.GET.get('q', '')
    limit = min(int(request.GET.get('limit', 10)), 50)

    if not query:
        return error_response('q is required', code=400)

    cache_key = f'smart_search_{query}_{limit}'
    cached = cache.get(cache_key)

    if cached:
        return success_response({
            'source': 'cache',
            'query': query,
            'results': cached,
        }, message="Results from cache")

    existing_products = Product.objects.filter(
        Q(title__icontains=query) | Q(description__icontains=query),
        is_active=True
    ).prefetch_related('listings__platform')[:limit]

    if existing_products.exists():
        sync_all_platforms_task.delay(query, limit)
        results = ProductSerializer(existing_products, many=True).data
        cache.set(cache_key, results, 300)

        return success_response({
            'source': 'database',
            'query': query,
            'count': len(results),
            'note': 'Background sync started for fresh data',
            'results': results,
        }, message="Results from database")

    task = sync_all_platforms_task.delay(query, limit)

    return success_response({
        'source': 'syncing',
        'query': query,
        'task_id': task.id,
        'message': 'Data fetching started from all platforms',
        'check_status': f'/api/v1/fetch-products/task-status/{task.id}/',
        'fetch_results': f'/api/v1/fetch-products/smart-search/?q={query}&limit={limit}',
    }, message="Sync started", code=202)


@api_view(['GET'])
def task_status(request, task_id):
    from celery.result import AsyncResult

    result = AsyncResult(task_id)
    response_data = {
        'task_id': task_id,
        'status': result.status,
    }

    if result.status == 'SUCCESS':
        response_data['result'] = result.result
        response_data['message'] = 'Sync completed! Now fetch results.'
    elif result.status == 'FAILURE':
        response_data['error'] = str(result.result)

    return success_response(response_data, message="Task status fetched")


# ============================================================================
# Cart ViewSet
# ============================================================================

class CartViewSet(viewsets.ModelViewSet):
    serializer_class = CartItemSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CartItem.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def _success(self, data, message="Success", code=200):
        return Response({
            "success": True,
            "code": code,
            "message": message,
            "timestamp": int(time.time()),
            "data": data,
        }, status=code)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return self._success(serializer.data, message="Item added to cart", code=201)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return self._success(serializer.data, message="Cart item fetched")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return self._success(serializer.data, message="Cart items fetched")

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return self._success(serializer.data, message="Cart item updated")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return self._success({}, message="Item removed from cart")

    @action(detail=False, methods=['get'])
    def checkout_options(self, request):
        cart_items = self.get_queryset()

        if not cart_items.exists():
            raise ValidationError({"cart": "Your cart is empty."})

        original_total = 0
        optimized_total = 0
        single_store_total = 0
        optimized_split = {}
        single_store_target = 'ebay'
        single_store_items = []

        for item in cart_items:
            product = item.product
            qty = item.quantity
            current_price = item.selected_listing.price * qty
            original_total += current_price

            cheapest_listing = ProductListing.objects.filter(
                product=product, is_available=True
            ).order_by('price').first()

            if cheapest_listing:
                opt_price = cheapest_listing.price * qty
                optimized_total += opt_price
                platform_name = cheapest_listing.platform.name

                if platform_name not in optimized_split:
                    optimized_split[platform_name] = {'total': 0, 'items': []}

                optimized_split[platform_name]['total'] += float(opt_price)
                optimized_split[platform_name]['items'].append({
                    'product': product.title,
                    'unit_price': float(cheapest_listing.price),
                    'quantity': qty,
                    'total_price': float(opt_price),
                    'url': cheapest_listing.external_url,
                })

            single_store_listing = ProductListing.objects.filter(
                product=product, platform__code=single_store_target, is_available=True
            ).first()

            if single_store_listing:
                single_price = single_store_listing.price * qty
                single_store_total += single_price
                single_store_items.append({
                    'product': product.title,
                    'unit_price': float(single_store_listing.price),
                    'quantity': qty,
                    'total_price': float(single_price),
                })
            else:
                single_store_total += current_price

        split_savings = float(original_total - optimized_total)

        data = {
            "cart_total_original": float(original_total),
            "options": {
                "single_store": {
                    "platform": "eBay",
                    "total_cost": float(single_store_total),
                    "shipments": 1,
                    "items": single_store_items,
                },
                "optimized_split": {
                    "total_cost": float(optimized_total),
                    "total_saved": split_savings if split_savings > 0 else 0,
                    "shipments": len(optimized_split.keys()),
                    "platforms": optimized_split,
                },
            },
            "savings_summary": {
                "original_total": float(original_total),
                "price_match_savings": float(original_total - optimized_total) if original_total > optimized_total else 0,
                "final_price": float(optimized_total),
            },
        }

        return self._success(data, message="Checkout options generated")

    @action(detail=False, methods=['post'])
    def complete_checkout(self, request):
        cart_items = self.get_queryset()

        if not cart_items.exists():
            raise ValidationError({"cart": "Your cart is empty."})

        original_total = 0
        optimized_total = 0
        activities_to_create = []

        for item in cart_items:
            qty = item.quantity
            current_price = item.selected_listing.price * qty
            original_total += current_price

            cheapest_listing = ProductListing.objects.filter(
                product=item.product, is_available=True
            ).order_by('price').first()

            if cheapest_listing:
                opt_price = cheapest_listing.price * qty
                optimized_total += opt_price
                item_saved = float(current_price - opt_price)
                if item_saved > 0:
                    activities_to_create.append(
                        SavingsActivity(
                            user=request.user,
                            title=item.product.title,
                            saved_amount=item_saved,
                        )
                    )
            else:
                optimized_total += current_price

        total_saved = float(original_total - optimized_total)

        with transaction.atomic():
            user = request.user
            if total_saved > 0:
                current_savings = getattr(user, 'total_lifetime_savings', 0)
                user.total_lifetime_savings = float(current_savings) + total_saved
                user.save()
                if activities_to_create:
                    SavingsActivity.objects.bulk_create(activities_to_create)

            cart_items.delete()

        recent_activities = SavingsActivity.objects.filter(
            user=request.user
        ).order_by('-created_at')[:5]

        data = {
            "total_paid": float(optimized_total),
            "total_saved_this_order": total_saved,
            "lifetime_savings_now": float(getattr(user, 'total_lifetime_savings', 0)),
            "recent_activity": [
                {"title": act.title, "saved_amount": float(act.saved_amount), "date": act.time_ago}
                for act in recent_activities
            ],
        }

        return self._success(data, message="Checkout completed successfully")

    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        user = request.user
        recent_activities = SavingsActivity.objects.filter(user=user).order_by('-created_at')[:5]

        data = {
            "total_lifetime_savings": float(getattr(user, 'total_lifetime_savings', 0.0)),
            "recent_activity": [
                {"title": act.title, "saved_amount": float(act.saved_amount), "date": act.time_ago}
                for act in recent_activities
            ],
        }

        return self._success(data, message="Dashboard data fetched successfully")


class DashboardSavingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        recent_activities = SavingsActivity.objects.filter(user=user).order_by('-created_at')[:5]

        data = {
            "total_lifetime_savings": float(getattr(user, 'total_lifetime_savings', 0.0)),
            "recent_activity": [
                {"title": act.title, "saved_amount": float(act.saved_amount), "date": act.time_ago}
                for act in recent_activities
            ],
        }

        return success_response(data, message="Dashboard data fetched successfully")