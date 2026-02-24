import time
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q, Min, Count, Avg
from django.db import transaction
from .models import Product, ProductListing, Platform, Category, PriceHistory, ProductImage, ProductSpecification
from .serializers import (
    ProductSerializer,
    ProductDetailSerializer,
    ProductListingSerializer,
    PlatformSerializer,
    CategorySerializer,
    PriceHistorySerializer
)
from .services.ebay_service import EbayService
from .services.clickbank_service import ClickBankService
from rest_framework.exceptions import ValidationError

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
    """
    Save ClickBank product to database
    Returns (product, listing, created)
    """
    product, _ = Product.objects.get_or_create(
        title=product_data['title'],
        defaults={
            'description': product_data.get('description', '') or '',
            'brand': product_data.get('brand', '') or '',
            'model_number': product_data.get('model_number', '') or '',
            'main_image': product_data.get('main_image', '') or ''
        }
    )

    shipping_info = product_data.get('shipping_info', {})

    listing, created = ProductListing.objects.update_or_create(
        product=product,
        platform=platform,
        external_id=product_data['external_id'],
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
            'free_shipping': shipping_info.get('free_shipping', False),
            'is_available': product_data.get('is_available', True)
        }
    )

    if product_data.get('specifications'):
        ProductSpecification.objects.filter(product=product).delete()
        for name, value in product_data['specifications'].items():
            ProductSpecification.objects.create(
                product=product,
                name=name,
                value=value
            )

    if created:
        PriceHistory.objects.create(
            listing=listing,
            price=listing.price,
            currency=listing.currency
        )

    return product, listing, created


def save_ebay_product_to_db(item_data, platform):
    """
    Save eBay product to database.
    Returns (product, listing, created)
    """
    ebay_service = EbayService()
    item_id = item_data.get('itemId')
    detailed_item = ebay_service.get_item_details(item_id)

    if not detailed_item:
        return None, None, False

    product_data = ebay_service.extract_product_data(detailed_item)

    product, _ = Product.objects.get_or_create(
        title=product_data['title'],
        defaults={
            'description': product_data.get('description', ''),
            'brand': product_data.get('brand', ''),
            'model_number': product_data.get('model_number', ''),
            'main_image': product_data.get('main_image', '')
        }
    )

    shipping_info = product_data.get('shipping_info', {})

    listing, listing_created = ProductListing.objects.update_or_create(
        product=product,
        platform=platform,
        external_id=product_data['external_id'],
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
            'is_available': product_data.get('is_available', True)
        }
    )

    if listing_created:
        PriceHistory.objects.create(
            listing=listing,
            price=listing.price,
            currency=listing.currency
        )
    else:
        last_history = listing.price_history.order_by('-recorded_at').first()
        if not last_history or last_history.price != listing.price:
            PriceHistory.objects.create(
                listing=listing,
                price=listing.price,
                currency=listing.currency
            )

    if product_data.get('additional_images'):
        ProductImage.objects.filter(product=product).delete()
        for order, image_url in enumerate(product_data['additional_images'][:10]):
            ProductImage.objects.create(
                product=product,
                image_url=image_url,
                order=order
            )

    if product_data.get('specifications'):
        ProductSpecification.objects.filter(product=product).delete()
        for name, value in product_data['specifications'].items():
            ProductSpecification.objects.create(
                product=product,
                name=name,
                value=value
            )

    return product, listing, listing_created


# ============================================================================
# Platform-specific sync functions
# ============================================================================

def sync_ebay_products(platform, query, limit):
    """Sync eBay products"""
    ebay_service = EbayService()
    search_results = ebay_service.search_products(query, limit=limit)

    if not search_results:
        return error_response("Failed to fetch products from eBay", code=500)

    items = search_results.get('itemSummaries', [])

    result = {
        'query': query,
        'platform': 'ebay',
        'limit': limit,
        'synced': 0,
        'updated': 0,
        'failed': 0,
        'products': [],
        'external_ids': []
    }

    for item in items:
        external_id = item.get('itemId')
        result['external_ids'].append(external_id)

        try:
            with transaction.atomic():
                product, listing, created = save_ebay_product_to_db(item, platform)

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
                        'status': 'created' if created else 'updated'
                    })
                else:
                    result['failed'] += 1

        except Exception as e:
            result['failed'] += 1
            logger.error(f"Failed to sync eBay item {external_id}: {str(e)}", exc_info=True)

    return success_response(result, message="eBay sync completed")


def sync_clickbank_products(platform, query, limit):
    """Sync ClickBank products"""
    clickbank_service = ClickBankService()
    search_results = clickbank_service.search_mock_products(query, limit)

    if not search_results:
        return error_response("No ClickBank products found", code=404)

    result = {
        'query': query,
        'platform': 'clickbank',
        'limit': limit,
        'synced': 0,
        'updated': 0,
        'failed': 0,
        'products': [],
        'external_ids': []
    }

    for item in search_results:
        external_id = item.get('site')
        result['external_ids'].append(external_id)

        try:
            product_data = clickbank_service.extract_product_data(item)

            with transaction.atomic():
                product, _ = Product.objects.get_or_create(
                    title=product_data['title'],
                    defaults={
                        'description': product_data.get('description', '') or '',
                        'brand': product_data.get('brand', '') or '',
                        'model_number': product_data.get('model_number', '') or '',
                        'main_image': product_data.get('main_image', '') or ''
                    }
                )

                shipping_info = product_data.get('shipping_info', {})

                listing, created = ProductListing.objects.update_or_create(
                    product=product,
                    platform=platform,
                    external_id=external_id,
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
                        'free_shipping': shipping_info.get('free_shipping', False),
                        'is_available': product_data.get('is_available', True)
                    }
                )

                if product_data.get('specifications'):
                    ProductSpecification.objects.filter(product=product).delete()
                    for name, value in product_data['specifications'].items():
                        ProductSpecification.objects.create(
                            product=product,
                            name=name,
                            value=value
                        )

                if created:
                    PriceHistory.objects.create(
                        listing=listing,
                        price=listing.price,
                        currency=listing.currency
                    )
                else:
                    last_history = listing.price_history.order_by('-recorded_at').first()
                    if not last_history or last_history.price != listing.price:
                        PriceHistory.objects.create(
                            listing=listing,
                            price=listing.price,
                            currency=listing.currency
                        )

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
                    'status': 'created' if created else 'updated'
                })

        except Exception as e:
            result['failed'] += 1
            logger.error(f"Failed to sync ClickBank product {external_id}: {str(e)}", exc_info=True)

    return success_response(result, message="ClickBank sync completed")


def sync_all_platforms(query, limit):
    """Sync from ALL enabled platforms"""
    enabled_platforms = Platform.objects.filter(api_enabled=True)

    all_results = {
        'query': query,
        'platforms': [],
        'total_synced': 0,
        'total_updated': 0,
        'total_failed': 0,
        'results_by_platform': {}
    }

    for platform in enabled_platforms:
        try:
            if platform.code == 'ebay':
                result = sync_ebay_products(platform, query, limit)
            elif platform.code == 'clickbank':
                result = sync_clickbank_products(platform, query, limit)
            else:
                continue

            result_data = result.data.get('data', {})
            all_results['platforms'].append(platform.code)
            all_results['total_synced'] += result_data.get('synced', 0)
            all_results['total_updated'] += result_data.get('updated', 0)
            all_results['total_failed'] += result_data.get('failed', 0)
            all_results['results_by_platform'][platform.code] = result_data

        except Exception as e:
            logger.error(f"Failed to sync platform {platform.code}: {str(e)}", exc_info=True)
            continue

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
    """API endpoint for products"""
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

        brand = self.request.query_params.get('brand')
        if brand:
            queryset = queryset.filter(brand__iexact=brand)

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
            queryset = queryset.annotate(
                sort_price=Min('listings__price')
            ).order_by('sort_price')
        elif sort == 'price_high':
            queryset = queryset.annotate(
                sort_price=Min('listings__price')
            ).order_by('-sort_price')
        elif sort == 'newest':
            queryset = queryset.order_by('-created_at')
        elif sort == 'popular':
            queryset = queryset.annotate(
                listing_count=Count('listings')
            ).order_by('-listing_count')
        else:
            queryset = queryset.order_by(sort)

        return queryset.distinct()

    @action(detail=True, methods=['get'])
    def compare_prices(self, request, slug=None):
        """Compare prices across all platforms"""
        product = self.get_object()
        listings = product.listings.filter(is_available=True).select_related('platform')

        comparison_data = {
            'product': {
                'id': product.id,
                'title': product.title,
                'slug': product.slug,
                'brand': product.brand,
                'main_image': product.main_image
            },
            'price_comparison': []
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
                'last_updated': listing.last_checked
            })

        comparison_data['price_comparison'].sort(key=lambda x: x['total_price'])
        comparison_data['best_deal'] = (
            comparison_data['price_comparison'][0]
            if comparison_data['price_comparison'] else None
        )

        return success_response(comparison_data, message="Price comparison fetched")


class ProductListingViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for product listings"""
    queryset = ProductListing.objects.filter(
        is_available=True).select_related('product', 'platform')
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
    """API endpoint for platforms"""
    queryset = Platform.objects.filter(api_enabled=True)
    serializer_class = PlatformSerializer
    lookup_field = 'code'


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for categories"""
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    lookup_field = 'slug'


# ============================================================================
# Custom API Endpoints
# ============================================================================

@api_view(['GET'])
def search_and_sync(request):
    """
    Search and automatically sync products to database
    GET /api/search-and-sync/?q=laptop&limit=10&platform=ebay
    """
    query = request.GET.get('q', '')
    limit = min(int(request.GET.get('limit', 10)), 50)
    platform_code = request.GET.get('platform', 'ebay')

    if not query:
        return error_response('Query parameter "q" is required', code=400)

    try:
        platform = Platform.objects.get(code=platform_code)
    except Platform.DoesNotExist:
        return error_response(f'Platform "{platform_code}" not found', code=404)

    if platform_code == 'ebay':
        return sync_ebay_products(platform, query, limit)
    elif platform_code == 'clickbank':
        return sync_clickbank_products(platform, query, limit)
    elif platform_code == 'all':
        return sync_all_platforms(query, limit)
    else:
        return error_response(f'Platform "{platform_code}" is not supported for sync', code=400)


@api_view(['POST'])
def bulk_sync_products(request):
    """
    Bulk sync multiple products
    POST /api/bulk-sync/
    Body: { "platform": "ebay", "product_ids": ["v1|110588835408|0"] }
    """
    platform_code = request.data.get('platform')
    product_ids = request.data.get('product_ids') or request.data.get('external_ids', [])

    if not platform_code or not product_ids:
        return error_response('Both "platform" and "product_ids" are required', code=400)

    try:
        platform = Platform.objects.get(code=platform_code)
    except Platform.DoesNotExist:
        return error_response(f'Platform "{platform_code}" not found', code=404)

    if platform_code == 'ebay':
        service = EbayService()
    elif platform_code == 'clickbank':
        service = ClickBankService()
    else:
        return error_response(f'Platform "{platform_code}" not supported for bulk sync', code=400)

    result = {
        'platform': platform_code,
        'total': len(product_ids),
        'synced': 0,
        'updated': 0,
        'failed': 0,
        'products': []
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
                    'status': 'created' if created else 'updated'
                })
            else:
                result['failed'] += 1

        except Exception as e:
            result['failed'] += 1
            logger.error(f"Failed to bulk sync {external_id}: {str(e)}", exc_info=True)
            continue

    return success_response(result, message="Bulk sync completed")


@api_view(['GET'])
def api_root(request):
    """API Root - List all available endpoints"""
    return success_response({
        'message': 'Dealnux Price Comparison API',
        'version': '1.0',
        'endpoints': {
            'products': {
                'list': '/products/',
                'detail': '/products/{slug}/',
                'compare_prices': '/products/{slug}/compare_prices/',
            },
            'listings': {
                'list': '/listings/',
                'detail': '/listings/{id}/',
            },
            'platforms': {
                'list': '/platforms/',
                'detail': '/platforms/{code}/',
            },
            'sync': {
                'search_and_sync': '/search-and-sync/?q={query}&limit=10',
                'bulk_sync': '/bulk-sync/ (POST)',
            }
        }
    }, message="API root")


@api_view(['POST'])
def sync_from_search_results(request):
    """
    POST /api/sync-from-search/
    Body: {"query": "laptop", "limit": 10, "platform": "ebay"}
    """
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
        items_key = 'itemSummaries'
        id_key = 'itemId'
        items = search_results.get(items_key, []) if search_results else []

    elif platform_code == 'clickbank':
        service = ClickBankService()
        search_results = service.search_mock_products(query, limit)
        id_key = 'site'
        items = search_results if isinstance(search_results, list) else []

    else:
        return error_response(f'Platform "{platform_code}" sync not implemented', code=501)

    if not search_results:
        return error_response(f'Failed to search {platform_code}', code=500)

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
        'external_ids': []
    }

    for item in items:
        external_id = item.get(id_key)
        result['external_ids'].append(external_id)

        try:
            existing = ProductListing.objects.filter(
                platform=platform,
                external_id=external_id
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
                    'status': 'already_exists'
                })
                continue

            with transaction.atomic():
                if platform_code == 'ebay':
                    product, listing, created = save_ebay_product_to_db(item, platform)
                elif platform_code == 'clickbank':
                    product_data = service.extract_product_data(item)
                    product, listing, created = save_clickbank_product_to_db(product_data, platform)
                else:
                    result['failed'] += 1
                    continue

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
                    'status': status_text
                })
            else:
                result['failed'] += 1

        except Exception as e:
            result['failed'] += 1
            logger.error(f"Failed to sync {external_id}: {str(e)}", exc_info=True)

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

        try:
            ebay_service = EbayService()
            ebay_results = ebay_service.search_products(query, limit=limit)
            ebay_items = ebay_results.get('itemSummaries', []) if ebay_results else []
            for item in ebay_items:
                all_items.append({
                    'external_id': item.get('itemId'),
                    'platform': 'ebay',
                    'title': item.get('title'),
                    'price': item.get('price', {}).get('value'),
                    'currency': item.get('price', {}).get('currency', 'USD'),
                    'condition': item.get('condition'),
                    'url': item.get('itemWebUrl')
                })
        except Exception as e:
            logger.error(f"eBay search failed: {e}")

        try:
            cb_service = ClickBankService()
            cb_items = cb_service.search_mock_products(query, limit)
            for item in cb_items:
                all_items.append({
                    'external_id': item.get('site'),
                    'platform': 'clickbank',
                    'title': item.get('title'),
                    'price': item.get('price'),
                    'currency': 'USD',
                    'condition': 'NEW',
                    'url': item.get('url')
                })
        except Exception as e:
            logger.error(f"ClickBank search failed: {e}")

        return success_response({
            'query': query,
            'platform': 'all',
            'items_returned': len(all_items),
            'items': all_items,
        }, message="External IDs fetched")

    if platform_code == 'ebay':
        service = EbayService()
        search_results = service.search_products(query, limit=limit)
        items = search_results.get('itemSummaries', []) if search_results else []
        id_key = 'itemId'

    elif platform_code == 'clickbank':
        service = ClickBankService()
        items = service.search_mock_products(query, limit)
        search_results = {'total': len(items)}
        id_key = 'site'

    else:
        return error_response(f'Platform "{platform_code}" not supported', code=400)

    external_ids = []
    items_detail = []

    for item in items:
        item_id = item.get(id_key)
        external_ids.append(item_id)
        items_detail.append({
            'external_id': item_id,
            'title': item.get('title'),
            'price': item.get('price', {}).get('value') if platform_code == 'ebay' else item.get('price'),
            'currency': item.get('price', {}).get('currency') if platform_code == 'ebay' else 'USD',
            'condition': item.get('condition'),
            'url': item.get('itemWebUrl') if platform_code == 'ebay' else item.get('url')
        })

    return success_response({
        'query': query,
        'platform': platform_code,
        'total_found': search_results.get('total', len(items)),
        'items_returned': len(items),
        'external_ids': external_ids,
        'items': items_detail,
        'bulk_sync_body': {
            'platform': platform_code,
            'product_ids': external_ids
        }
    }, message="External IDs fetched")


@api_view(['GET'])
def product_price_history(request, slug):
    """
    GET /api/v1/fetch-products/products/{slug}/price_history/
    """
    try:
        product = Product.objects.get(slug=slug)
    except Product.DoesNotExist:
        return error_response('Product not found', code=404)

    listings = product.listings.all()
    history_data = []

    for listing in listings:
        histories = listing.price_history.order_by('-recorded_at')
        for history in histories:
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
        'price_history': history_data
    }, message="Price history fetched")


from .tasks import sync_all_platforms_task, sync_ebay_task, sync_clickbank_task
from django.core.cache import cache


@api_view(['GET'])
def smart_search(request):
    """
    Parallel sync + Cache
    GET /api/v1/fetch-products/smart-search/?q=laptop&limit=10
    """
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
            'results': cached
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
            'results': results
        }, message="Results from database")

    task = sync_all_platforms_task.delay(query, limit)

    return success_response({
        'source': 'syncing',
        'query': query,
        'task_id': task.id,
        'message': 'Data fetching started from all platforms',
        'check_status': f'/api/v1/fetch-products/task-status/{task.id}/',
        'fetch_results': f'/api/v1/fetch-products/smart-search/?q={query}&limit={limit}'
    }, message="Sync started", code=202)


@api_view(['GET'])
def task_status(request, task_id):
    """
    Task status check
    GET /api/v1/fetch-products/task-status/{task_id}/
    """
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

from rest_framework.permissions import IsAuthenticated
from .models import CartItem
from .serializers import CartItemSerializer
from api_integration.models import ProductListing


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
            "data": data
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
        
        # কার্ট ফাঁকা থাকলে exception থ্রো করবে, যা আপনার custom_exception_handler হ্যান্ডেল করবে (success: false)
        if not cart_items.exists():
            raise ValidationError({"cart": "Your cart is empty."})

        original_total = 0
        optimized_total = 0
        single_store_total = 0
        optimized_split = {}
        single_store_target = 'ebay' # Default fallback
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
                
                # ✅ ক্লিয়ার কাট স্ট্রাকচার
                optimized_split[platform_name]['items'].append({
                    'product': product.title,
                    'unit_price': float(cheapest_listing.price),
                    'quantity': qty,
                    'total_price': float(opt_price),
                    'url': cheapest_listing.external_url
                })

            single_store_listing = ProductListing.objects.filter(
                product=product, platform__code=single_store_target, is_available=True
            ).first()

            if single_store_listing:
                single_price = single_store_listing.price * qty
                single_store_total += single_price
                
                # ✅ ক্লিয়ার কাট স্ট্রাকচার
                single_store_items.append({
                    'product': product.title, 
                    'unit_price': float(single_store_listing.price),
                    'quantity': qty,
                    'total_price': float(single_price)
                })
            else:
                single_store_total += current_price

        split_savings = float(original_total - optimized_total)
        
        # রেসপন্সের মূল ডাটা
        data = {
            "cart_total_original": float(original_total),
            "options": {
                "single_store": {
                    "platform": "eBay",
                    "total_cost": float(single_store_total),
                    "shipments": 1,
                    "items": single_store_items
                },
                "optimized_split": {
                    "total_cost": float(optimized_total),
                    "total_saved": split_savings if split_savings > 0 else 0,
                    "shipments": len(optimized_split.keys()),
                    "platforms": optimized_split
                }
            },
            "savings_summary": {
                "original_total": float(original_total),
                "price_match_savings": float(original_total - optimized_total) if original_total > optimized_total else 0,
                "final_price": float(optimized_total)
            }
        }
        
        # আপনার success ফরম্যাটে ডাটা রিটার্ন করবে (success: true)
        return self._success(data, message="Checkout options generated", code=200)