import math
import re
import logging
from difflib import SequenceMatcher

from django.db.models import Q
from rest_framework import viewsets
from rest_framework.decorators import api_view, action, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import NotFound

from api_integration.models import (
    Product, ProductListing, Platform,
    CartItem, Favorite
)
from api_integration.serializers import (
    ProductSerializer, ProductDetailSerializer,
    ProductListingSerializer, PlatformSerializer,
)
from api_integration.services.product_query_service import (
    filter_and_score_products,
    get_product_detail_payload,
    record_deal_savings,
)
from api_integration.db_helpers import save_generic_product_to_db
from config.responses import success_response, error_response


logger = logging.getLogger(__name__)


# -------------------------- Unified Product & Seller Listing Detail API View --------------------------
@api_view(['GET'])
@permission_classes([AllowAny])
def product_detail(request, pk):
    result = get_product_detail_payload(pk, request)
    if result.get('error'):
        return error_response(result['message'], code=result.get('code', 400))
    return success_response(result['data'], message=result.get('message', 'Product details fetched successfully'))


# -------------------------- Pagination --------------------------
class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# -------------------------- Global Product Catalog ViewSet --------------------------
class ProductViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    queryset = Product.objects.all().prefetch_related(
        'listings',
        'listings__platform',
        'images'
    ).select_related('category')
    serializer_class = ProductSerializer
    pagination_class = StandardResultsSetPagination
    lookup_field = 'slug'

    def get_object(self):
        slug = self.kwargs.get('slug')
        if not slug:
            raise NotFound("No Product identifier provided.")

        # 1. Try direct ID lookup if parameter is numeric (e.g. /product/123)
        if str(slug).isdigit():
            try:
                obj = Product.objects.get(id=int(slug), is_active=True)
                self.check_object_permissions(self.request, obj)
                return obj
            except Product.DoesNotExist:
                pass

        # 2. Try exact slug lookup
        try:
            obj = Product.objects.get(slug=slug, is_active=True)
            self.check_object_permissions(self.request, obj)
            return obj
        except Product.DoesNotExist:
            pass

        # 3. Try case-insensitive slug lookup
        try:
            obj = Product.objects.get(slug__iexact=slug, is_active=True)
            self.check_object_permissions(self.request, obj)
            return obj
        except (Product.DoesNotExist, Product.MultipleObjectsReturned):
            pass

        # 4. Fuzzy fallback matching
        slug_as_title = slug.replace('-', ' ').lower()
        slug_as_title = re.sub(r'\d+opens?', '', slug_as_title)
        slug_as_title = re.sub(r'opens?\s+in\s+a\s+new', '', slug_as_title)
        slug_as_title = re.sub(r'\b(window|tab|new|or)\b', '', slug_as_title)
        slug_as_title = re.sub(r'\s+', ' ', slug_as_title).strip()

        slug_words = [w for w in slug_as_title.split() if len(w) > 2]

        query = Q()
        for word in slug_words:
            query &= Q(title__icontains=word)
        candidates = Product.objects.filter(query, is_active=True)

        if not candidates.exists():
            query = Q()
            for word in slug_words[:5]:
                query |= Q(title__icontains=word)
            candidates = Product.objects.filter(query, is_active=True)

        best_match = None
        best_score = 0

        for product in candidates:
            score = SequenceMatcher(
                None,
                slug_as_title,
                product.title.lower()
            ).ratio() * 100

            if score > best_score:
                best_score = score
                best_match = product

        if best_match and best_score >= 30:
            self.check_object_permissions(self.request, best_match)
            return best_match

        raise NotFound("No Product matches the given query.")

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ProductDetailSerializer
        return ProductSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        return filter_and_score_products(queryset, self.request.query_params)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            results = serializer.data
            total_count = self.paginator.page.paginator.count
            page_size = self.paginator.get_page_size(request)
            current_page = self.paginator.page.number
            total_pages = math.ceil(total_count / page_size)

            return success_response({
                'count': len(results),
                'pagination': {
                    'page': current_page,
                    'page_size': page_size,
                    'total_count': total_count,
                    'total_pages': total_pages,
                },
                'results': results
            }, message="Products retrieved successfully")

        serializer = self.get_serializer(queryset, many=True)
        return success_response(serializer.data, message="Products retrieved successfully")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.request.user and self.request.user.is_authenticated:
            context['favorite_ids'] = set(
                Favorite.objects.filter(user=self.request.user)
                .values_list('product_id', flat=True)
            )
            context['cart_product_ids'] = set(
                CartItem.objects.filter(user=self.request.user)
                .values_list('product_id', flat=True)
            )
        else:
            context['favorite_ids'] = set()
            context['cart_product_ids'] = set()
        return context

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def record_purchase_intent(self, request, slug=None):
        best_deal_product = self.get_object()
        result = record_deal_savings(best_deal_product, request.user)
        if result.get('error'):
            return error_response(result['message'], code=result.get('code', 400))
        return success_response(result['data'], message=result.get('message', "Savings recorded successfully based on best deal comparison!"))


# -------------------------- Product Multi-Retailer Listings ReadOnly ViewSet --------------------------
class ProductListingViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    queryset = ProductListing.objects.filter(
        is_available=True).select_related('product', 'platform')
    serializer_class = ProductListingSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        platform = self.request.query_params.get('platform')
        condition = self.request.query_params.get('condition')
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')

        if platform and platform != 'all':
            queryset = queryset.filter(platform__code=platform)
        if condition:
            queryset = queryset.filter(condition=condition)
        if min_price:
            queryset = queryset.filter(price__gte=min_price)
        if max_price:
            queryset = queryset.filter(price__lte=max_price)

        return queryset.order_by(self.request.query_params.get('sort', 'price'))


# -------------------------- Supported Retail Platforms ReadOnly ViewSet --------------------------
class PlatformViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PlatformSerializer
    lookup_field = 'code'

    def get_queryset(self):
        return Platform.objects.filter(api_enabled=True) | Platform.objects.filter(
            code__startswith='local-seller-'
        )


# -------------------------- Product Historical Price Tracking & Analytics API View --------------------------
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
                'platform':      listing.platform.name,
                'platform_code': listing.platform.code,
                'price':         float(history.price),
                'currency':      history.currency,
                'recorded_at':   history.recorded_at,
            })

    history_data.sort(key=lambda x: x['recorded_at'], reverse=True)

    return success_response({
        'product':       product.title,
        'slug':          product.slug,
        'total_records': len(history_data),
        'price_history': history_data,
    }, message="Price history fetched")


# -------------------------- Amazon Promo Code Verification & Details API View --------------------------
@api_view(['GET'])
@permission_classes([AllowAny])
def amazon_promo_details(request):
    from api_integration.services.amazon_service import AmazonService

    promo_code = request.GET.get('promo_code', '')
    country = request.GET.get('country', 'US')

    if not promo_code:
        return error_response('promo_code is required', code=400)

    service = AmazonService()
    data = service.get_promo_code_details(promo_code, country)

    if not data:
        return error_response('Promo code not found or expired', code=404)

    return success_response(data, message="Promo code details fetched")
