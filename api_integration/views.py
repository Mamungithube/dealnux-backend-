from rest_framework import viewsets, status
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q, Min, Count, Avg
from django.db import transaction
from .models import Product, ProductListing, Platform, Category, PriceHistory, ProductImage, ProductSpecification
from .serializers import (
    ProductSerializer, ProductDetailSerializer, 
    ProductListingSerializer, PlatformSerializer,
    CategorySerializer, PriceHistorySerializer
)
from .ebay_service import EbayService


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
    Save eBay product to database
    Returns (product, listing, created)
    """
    ebay_service = EbayService()
    
    # Get detailed item info
    item_id = item_data.get('itemId')
    detailed_item = ebay_service.get_item_details(item_id)
    
    if not detailed_item:
        return None, None, False
    
    # Extract product data
    product_data = ebay_service.extract_product_data(detailed_item)
    
    # Create or get product
    product, product_created = Product.objects.get_or_create(
        title=product_data['title'],
        defaults={
            'description': product_data.get('description', ''),
            'brand': product_data.get('brand', ''),
            'model_number': product_data.get('model_number', ''),
            'main_image': product_data.get('main_image', '')
        }
    )
    
    # Create or update listing
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
    
    # Record price history
    if listing_created:
        PriceHistory.objects.create(
            listing=listing,
            price=listing.price,
            currency=listing.currency
        )
    else:
        # Check if price changed
        last_history = listing.price_history.first()
        if not last_history or last_history.price != listing.price:
            PriceHistory.objects.create(
                listing=listing,
                price=listing.price,
                currency=listing.currency
            )
    
    # Save images
    if product_data.get('additional_images'):
        # Delete old images
        ProductImage.objects.filter(product=product).delete()
        
        # Add new images
        for order, image_url in enumerate(product_data['additional_images'][:10]):
            ProductImage.objects.create(
                product=product,
                image_url=image_url,
                order=order
            )
    
    # Save specifications
    if product_data.get('specifications'):
        # Delete old specs
        ProductSpecification.objects.filter(product=product).delete()
        
        # Add new specs
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
    """
    API endpoint for products
    """
    queryset = Product.objects.filter(is_active=True).prefetch_related('listings', 'images', 'specifications')
    serializer_class = ProductSerializer
    pagination_class = StandardResultsSetPagination
    lookup_field = 'slug'
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ProductDetailSerializer
        return ProductSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filters
        category = self.request.query_params.get('category', None)
        if category:
            queryset = queryset.filter(category__slug=category)
        
        brand = self.request.query_params.get('brand', None)
        if brand:
            queryset = queryset.filter(brand__iexact=brand)
        
        min_price = self.request.query_params.get('min_price', None)
        max_price = self.request.query_params.get('max_price', None)
        
        if min_price:
            queryset = queryset.filter(listings__price__gte=min_price)
        if max_price:
            queryset = queryset.filter(listings__price__lte=max_price)
        
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(brand__icontains=search)
            )
        
        # Sort
        sort = self.request.query_params.get('sort', '-created_at')
        if sort == 'price_low':
            queryset = queryset.annotate(min_price=Min('listings__price')).order_by('min_price')
        elif sort == 'price_high':
            queryset = queryset.annotate(min_price=Min('listings__price')).order_by('-min_price')
        elif sort == 'newest':
            queryset = queryset.order_by('-created_at')
        elif sort == 'popular':
            queryset = queryset.annotate(listing_count=Count('listings')).order_by('-listing_count')
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
        
        if comparison_data['price_comparison']:
            comparison_data['best_deal'] = comparison_data['price_comparison'][0]
        else:
            comparison_data['best_deal'] = None
        
        return Response(comparison_data)


class ProductListingViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for product listings"""
    queryset = ProductListing.objects.filter(is_available=True).select_related('product', 'platform')
    serializer_class = ProductListingSerializer
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        platform = self.request.query_params.get('platform', None)
        if platform:
            queryset = queryset.filter(platform__code=platform)
        
        condition = self.request.query_params.get('condition', None)
        if condition:
            queryset = queryset.filter(condition=condition)
        
        min_price = self.request.query_params.get('min_price', None)
        max_price = self.request.query_params.get('max_price', None)
        
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
    limit = min(int(request.GET.get('limit', 10)), 50)  # Max 50
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
    
    result = {
        'query': query,
        'platform': platform_code,
        'limit': limit,
        'synced': 0,
        'updated': 0,
        'failed': 0,
        'products': []
    }
    
    # Get eBay service
    ebay_service = EbayService()
    
    # Search products
    search_results = ebay_service.search_products(query, limit=limit)
    
    if not search_results:
        return Response({
            'error': 'Failed to fetch products from eBay'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    items = search_results.get('itemSummaries', [])
    
    # Sync each item to database
    for item in items:
        try:
            with transaction.atomic():
                product, listing, created = save_ebay_product_to_db(item, platform)
                
                if product and listing:
                    if created:
                        result['synced'] += 1
                    else:
                        result['updated'] += 1
                    
                    result['products'].append({
                        'id': product.id,
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
            print(f"Failed to sync {item.get('itemId')}: {str(e)}")
            continue
    
    return Response(result)


@api_view(['POST'])
def bulk_sync_products(request):
    """
    Bulk sync multiple products
    POST /api/bulk-sync/
    
    Body:
    {
        "platform": "ebay",
        "product_ids": ["v1|110588835408|0", "v1|110588803036|410110915047"]
    }
    """
    platform_code = request.data.get('platform')
    product_ids = request.data.get('product_ids', [])
    
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
            # Check if already exists
            existing = ProductListing.objects.filter(
                platform=platform,
                external_id=external_id
            ).first()
            
            # Get item details
            item_data = ebay_service.get_item_details(external_id)
            
            if not item_data:
                result['failed'] += 1
                continue
            
            with transaction.atomic():
                product, listing, created = save_ebay_product_to_db(item_data, platform)
                
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
            print(f"Failed to sync {external_id}: {str(e)}")
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
                'list': '/api/products/',
                'detail': '/api/products/{slug}/',
                'compare_prices': '/api/products/{slug}/compare_prices/',
            },
            'listings': {
                'list': '/api/listings/',
                'detail': '/api/listings/{id}/',
            },
            'platforms': {
                'list': '/api/platforms/',
                'detail': '/api/platforms/{code}/',
            },
            'sync': {
                'search_and_sync': '/api/search-and-sync/?q={query}&limit=10',
                'bulk_sync': '/api/bulk-sync/ (POST)',
            }
        }
    })