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

logger = logging.getLogger(__name__)

# ============================================================================
# Platform-specific sync functions
# ============================================================================


def sync_ebay_products(platform, query, limit):
    """Sync eBay products"""
    ebay_service = EbayService()
    search_results = ebay_service.search_products(query, limit=limit)

    if not search_results:
        return Response({
            'error': 'Failed to fetch products from eBay'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
                product, listing, created = save_ebay_product_to_db(
                    item, platform)

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
            logger.error(
                f"Failed to sync eBay item {external_id}: {str(e)}", exc_info=True)

    return Response(result)


def sync_clickbank_products(platform, query, limit):
    """Sync ClickBank products"""
    clickbank_service = ClickBankService()
    search_results = clickbank_service.search_mock_products(query, limit)

    if not search_results:
        return Response({
            'error': 'No ClickBank products found'
        }, status=status.HTTP_404_NOT_FOUND)

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
                # Create/update product
                product, _ = Product.objects.get_or_create(
                    title=product_data['title'],
                    defaults={
                        'description': product_data.get('description', '') or '',
                        'brand': product_data.get('brand', '') or '',
                        'model_number': product_data.get('model_number', '') or '',
                        # None হলে '' হবে
                        'main_image': product_data.get('main_image', '') or ''
                    }
                )

                shipping_info = product_data.get('shipping_info', {})

                # Create/update listing
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

                # Save specifications
                if product_data.get('specifications'):
                    ProductSpecification.objects.filter(
                        product=product).delete()
                    for name, value in product_data['specifications'].items():
                        ProductSpecification.objects.create(
                            product=product,
                            name=name,
                            value=value
                        )

                # Price history
                if created:
                    PriceHistory.objects.create(
                        listing=listing,
                        price=listing.price,
                        currency=listing.currency
                    )
                else:
                    last_history = listing.price_history.order_by(
                        '-recorded_at').first()
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
            logger.error(
                f"Failed to sync ClickBank product {external_id}: {str(e)}", exc_info=True)

    return Response(result)


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

            result_data = result.data
            all_results['platforms'].append(platform.code)
            all_results['total_synced'] += result_data.get('synced', 0)
            all_results['total_updated'] += result_data.get('updated', 0)
            all_results['total_failed'] += result_data.get('failed', 0)
            all_results['results_by_platform'][platform.code] = result_data

        except Exception as e:
            logger.error(
                f"Failed to sync platform {platform.code}: {str(e)}", exc_info=True)
            continue

    return Response(all_results)


# ============================================================================
# Pagination
# ============================================================================

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# ============================================================================
# Helper Functions
# ============================================================================

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

    # Create or get product
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

    # Create or update listing
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

    # Record price history
    if listing_created:
        PriceHistory.objects.create(
            listing=listing,
            price=listing.price,
            currency=listing.currency
        )
    else:
        # FIX: ordering by recorded_at to get the latest record reliably
        last_history = listing.price_history.order_by('-recorded_at').first()
        if not last_history or last_history.price != listing.price:
            PriceHistory.objects.create(
                listing=listing,
                price=listing.price,
                currency=listing.currency
            )

    # Save images
    if product_data.get('additional_images'):
        ProductImage.objects.filter(product=product).delete()
        for order, image_url in enumerate(product_data['additional_images'][:10]):
            ProductImage.objects.create(
                product=product,
                image_url=image_url,
                order=order
            )

    # Save specifications
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

        # FIX: annotate only once with unique names to avoid conflicts
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
        listings = product.listings.filter(
            is_available=True).select_related('platform')

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

        comparison_data['price_comparison'].sort(
            key=lambda x: x['total_price'])
        comparison_data['best_deal'] = (
            comparison_data['price_comparison'][0]
            if comparison_data['price_comparison'] else None
        )

        return Response(comparison_data)


class ProductListingViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for product listings"""
    queryset = ProductListing.objects.filter(
        is_available=True).select_related('product', 'platform')
    serializer_class = ProductListingSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = super().get_queryset()

        platform = self.request.query_params.get('platform')
        if platform:
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

    Parameters:
        q (str): Search query (required)
        limit (int): Number of products to sync (default: 10, max: 50)
        platform (str): Platform code (default: ebay)
    """
    query = request.GET.get('q', '')
    limit = min(int(request.GET.get('limit', 10)), 50)
    platform_code = request.GET.get('platform', 'ebay')

    if not query:
        return Response({
            'error': 'Query parameter "q" is required'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        platform = Platform.objects.get(code=platform_code)
    except Platform.DoesNotExist:
        return Response({
            'error': f'Platform "{platform_code}" not found'
        }, status=status.HTTP_404_NOT_FOUND)

    # FIX: Route to correct platform service instead of always using eBay
    if platform_code == 'ebay':
        return sync_ebay_products(platform, query, limit)
    elif platform_code == 'clickbank':
        return sync_clickbank_products(platform, query, limit)
    elif platform_code == 'all':
        return sync_all_platforms(query, limit)
    else:
        return Response({
            'error': f'Platform "{platform_code}" is not supported for sync'
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def bulk_sync_products(request):
    """
    Bulk sync multiple products
    POST /api/bulk-sync/
    Body: {
        "platform": "ebay",
        "product_ids": ["v1|110588835408|0", "v1|110588803036|410110915047"]
    }
    """
    platform_code = request.data.get('platform')
    product_ids = request.data.get(
        'product_ids') or request.data.get('external_ids', [])

    if not platform_code or not product_ids:
        return Response({
            'error': 'Both "platform" and "product_ids" are required'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        platform = Platform.objects.get(code=platform_code)
    except Platform.DoesNotExist:
        return Response({
            'error': f'Platform "{platform_code}" not found'
        }, status=status.HTTP_404_NOT_FOUND)

    result = {
        'platform': platform_code,
        'total': len(product_ids),
        'synced': 0,
        'updated': 0,
        'failed': 0,
        'products': []
    }

    ebay_service = EbayService()

    for external_id in product_ids:
        try:
            item_data = ebay_service.get_item_details(external_id)

            if not item_data:
                result['failed'] += 1
                continue

            with transaction.atomic():
                product, listing, created = save_ebay_product_to_db(
                    item_data, platform)

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
            logger.error(
                f"Failed to bulk sync {external_id}: {str(e)}", exc_info=True)
            continue

    return Response(result)


@api_view(['GET'])
def api_root(request):
    """API Root - List all available endpoints"""
    return Response({
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
    })


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
        return Response({'error': 'Query is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        platform = Platform.objects.get(code=platform_code)
    except Platform.DoesNotExist:
        return Response(
            {'error': f'Platform "{platform_code}" not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    ebay_service = EbayService()
    search_results = ebay_service.search_products(query, limit=limit)

    if not search_results:
        return Response({'error': 'Failed to search eBay'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    items = search_results.get('itemSummaries', [])

    result = {
        'query': query,
        'platform': platform_code,
        'total_found': search_results.get('total', 0),
        'items_fetched': len(items),
        'synced': 0,
        'updated': 0,
        'skipped': 0,
        'failed': 0,
        'products': [],
        'external_ids': []
    }

    for item in items:
        external_id = item.get('itemId')
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
                product, listing, created = save_ebay_product_to_db(
                    item, platform)

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
            logger.error(
                f"Failed to sync {external_id}: {str(e)}", exc_info=True)

    return Response(result)


@api_view(['GET'])
def get_external_ids(request):
    """
    GET /api/get-external-ids/?q=laptop&limit=10
    """
    query = request.GET.get('q', '')
    limit = min(int(request.GET.get('limit', 10)), 50)

    if not query:
        return Response(
            {'error': 'Query parameter "q" is required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    ebay_service = EbayService()
    search_results = ebay_service.search_products(query, limit=limit)

    if not search_results:
        return Response({'error': 'Failed to search eBay'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    items = search_results.get('itemSummaries', [])

    external_ids = []
    items_detail = []

    for item in items:
        item_id = item.get('itemId')
        external_ids.append(item_id)
        items_detail.append({
            'external_id': item_id,
            'title': item.get('title'),
            'price': item.get('price', {}).get('value'),
            'currency': item.get('price', {}).get('currency'),
            'condition': item.get('condition'),
            'url': item.get('itemWebUrl')
        })

    return Response({
        'query': query,
        'total_found': search_results.get('total', 0),
        'items_returned': len(items),
        'external_ids': external_ids,
        'items': items_detail,
        'bulk_sync_body': {
            'platform': 'ebay',
            'product_ids': external_ids
        }
    })
