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


# -------------------------- Unified Product & Seller Listing Detail API View --------------------------
@api_view(['GET'])
@permission_classes([AllowAny])
def product_detail(request, pk):
    product = None
    seller_product_data = None
    standalone_seller_product = None

    try:
        from store.models import SellerProduct, ProductReview
        from django.db.models import Avg, Count

        seller_product = SellerProduct.objects.filter(
            id=pk, status='APPROVED').first()
        if seller_product:
            if seller_product.linked_product:
                product = seller_product.linked_product
            elif seller_product.linked_listing:
                product = seller_product.linked_listing.product
                seller_product.linked_product = product
                seller_product.save(update_fields=['linked_product'])
            else:
                try:
                    seller_product._ensure_linked_records()
                    seller_product.save(
                        update_fields=['linked_product', 'linked_listing', 'reviewed_at'])
                    product = seller_product.linked_product
                except Exception:
                    standalone_seller_product = seller_product  

            if product:
                stats = ProductReview.objects.filter(product=seller_product).aggregate(
                    avg=Avg('rating'), total=Count('id')
                )
                seller_product_data = {
                    'id': seller_product.id,
                    'price': str(seller_product.price),
                    'main_image': request.build_absolute_uri(seller_product.main_image.url) if seller_product.main_image else None,
                    'original_price': str(seller_product.original_price) if seller_product.original_price else None,
                    'currency': seller_product.currency,
                    'condition': seller_product.condition,
                    'seller_shop': seller_product.seller.shop_name,
                    'seller_logo': None,
                    'rating': round(stats['avg'] or 0.0, 1),
                    'review_count': stats['total'],
                    'platform_name': seller_product.seller.shop_name,
                    'external_url': '',
                }
            else:
                standalone_seller_product = seller_product 

    except ImportError:
        pass

    #  standalone SellerProduct — ProductDetailSerializer 
    if standalone_seller_product:
        sp = standalone_seller_product
        from store.models import ProductReview
        from django.db.models import Avg, Count

        stats = ProductReview.objects.filter(product=sp).aggregate(
            avg=Avg('rating'), total=Count('id')
        )
        main_image = request.build_absolute_uri(sp.main_image.url) if sp.main_image else None

        data = {
            'id': sp.id,
            'title': sp.title,
            'slug': '',
            'description': sp.description or '',
            'category': sp.category.id if hasattr(sp, 'category') and sp.category else None,
            'category_name': sp.category.name if sp.category else '',
            'brand': sp.brand or '',
            'main_image': main_image,
            'images': [],
            'price': float(sp.price),
            'lowest_price': float(sp.price),
            'shipping_cost': float(sp.shipping_cost or 0),
            'platform_name': sp.seller.shop_name,
            'external_url': '',
            'is_available': True,
            'is_active': True,
            'created_at': sp.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'is_favorite': False,
            'is_cart': False,
            'has_coupon': False,
            'coupon_text': '',
            'deal_badge': '',
            'is_best_seller': False,
            'rating': round(stats['avg'] or 0.0, 1),
            'review_count': stats['total'],
            'original_price': str(sp.original_price) if sp.original_price else None,
            'currency': sp.currency,
            'condition': sp.condition,
            'seller_shop': sp.seller.shop_name,
            'seller_logo': None,
            'related_products': [],
            'listings': [
                {
                    'id': sp.id,
                    'platform_name': sp.seller.shop_name,
                    'platform_code': f'local-seller-{sp.seller.id}',
                    'price': str(sp.price),
                    'currency': sp.currency,
                    'original_price': str(sp.original_price) if sp.original_price else None,
                    'discount_percentage': str(round(sp.discount_percentage, 2)) if sp.discount_percentage else None,
                    'condition': sp.condition,
                    'free_shipping': sp.free_shipping,
                    'shipping_cost': str(sp.shipping_cost or '0.00'),
                    'total_price': float(sp.price) + (float(sp.shipping_cost or 0) if not sp.free_shipping else 0),
                    'external_url': '',
                    'is_available': True,
                    'has_coupon': False,
                    'coupon_text': '',
                    'deal_badge': '',
                    'is_best_seller': False,
                }
            ],
        }
        return success_response(data, message="Product details fetched successfully")


    if not product:
        product = Product.objects.filter(id=pk, is_active=True).first()

    if not product:
        return error_response("Product not found", code=404)

    context = {'request': request}
    if request.user.is_authenticated:
        context['favorite_ids'] = set(Favorite.objects.filter(
            user=request.user).values_list('product_id', flat=True))
        context['cart_product_ids'] = set(CartItem.objects.filter(
            user=request.user).values_list('product_id', flat=True))
    else:
        context['favorite_ids'], context['cart_product_ids'] = set(), set()

    related_products = Product.objects.filter(
        category=product.category,
        brand=product.brand
    ).exclude(id=product.id)[:6]

    serializer = ProductDetailSerializer(product, context=context)
    data = serializer.data

    if not seller_product_data:
        if not request.user.is_authenticated:
            return error_response("Login required to view retailer details.", code=401)

        from payment.utils import validate_and_increment_click
        success, message = validate_and_increment_click(
            request.user, product_id=product.id)
        if not success:
            return error_response(message, code=403 if "subscribe" in message.lower() else 429)

    if seller_product_data:
        data.update(seller_product_data)

    data['related_products'] = ProductSerializer(
        related_products, many=True, context=context).data
    return success_response(data, message="Product details fetched successfully")
# ============================================================================


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# -------------------------- Global Product Catalog ViewSet (Filtering, Sorting, Search & Savings) --------------------------
class ProductViewSet(viewsets.ModelViewSet):

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

        try:
            obj = Product.objects.get(slug=slug, is_active=True)
            self.check_object_permissions(self.request, obj)
            return obj
        except Product.DoesNotExist:
            pass

        slug_as_title = slug.replace('-', ' ').lower()
        slug_as_title = re.sub(r'\d+opens?', '', slug_as_title)
        slug_as_title = re.sub(r'opens?\s+in\s+a\s+new', '', slug_as_title)
        slug_as_title = re.sub(r'\b(window|tab|new|or)\b', '', slug_as_title)
        slug_as_title = re.sub(r'\s+', ' ', slug_as_title).strip()

        slug_words = [w for w in slug_as_title.split() if len(w) > 2]

        # AND filter
        query = Q()
        for word in slug_words:
            query &= Q(title__icontains=word)
        candidates = Product.objects.filter(query, is_active=True)

        # If AND doesn't work, use OR with the first 5 words.
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

        from rest_framework.exceptions import NotFound
        raise NotFound("No Product matches the given query.")

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ProductDetailSerializer
        return ProductSerializer


    # def get_queryset(self):
    #     queryset = super().get_queryset()

    #     search_query = self.request.query_params.get('search', '').strip()
    #     sort = self.request.query_params.get('sort', '').strip()

    #     is_low = sort in ['price_low', 'lowest_price',
    #                       'Lowest Price'] or 'price_low' in self.request.query_params
    #     is_high = sort in ['price_high', 'highest_price',
    #                        'Highest Price'] or 'price_high' in self.request.query_params
    #     is_newest = sort in [
    #         'newest', 'Newest'] or 'newest' in self.request.query_params
    #     is_best = sort in [
    #         'best_deal', 'Best Deal'] or 'best_deal' in self.request.query_params

    #     min_price = self.request.query_params.get('min_price', '').strip()
    #     max_price = self.request.query_params.get('max_price', '').strip()

    #     queryset = queryset.filter(
    #         title__isnull=False,
    #         main_image__isnull=False,
    #         listings__price__gt=0,
    #         listings__is_available=True,
    #     ).exclude(title='', main_image='')

    #     category_input = self.request.query_params.getlist('category')
    #     explicit_category_ids = set()

    #     accessory_keywords = [
    #         'power bank', 'powerbank', 'solar', 'cable', 'charger', 'charging',
    #         'case', 'cover', 'box', 'station', 'stand', 'holder', 'mount',
    #         'tag', 'sticker', 'bag', 'kit', 'parts', 'lens', 'stabilizer', 'gimbal',
    #         'replacement', 'repair', 'tripod', 'strap', 'film', 'glass', 'battery', 'cord',
    #         'protector', 'adapter', 'screen guard', 'controller', 'gaming controller',
    #         'printer', 'cutting machine', 'poster', 'aux', 'usb board', 'connector',
    #         'price tag', 'thermal printer', 'cup holder', 'attachment lens',
    #         'converter', 'transmission', 'fill light', 'lighting', 'storage box',
    #         'pushchair', 'stroller', 'gaming controller', 'docking station'
    #     ]
    #     accessory_pattern = '|'.join(re.escape(w) for w in accessory_keywords)

    #     if category_input:
    #         slugs = []
    #         for item in category_input:
    #             slugs.extend([s.strip() for s in item.split(',') if s.strip()])
    #         if slugs:
    #             matching_cats = Category.objects.filter(slug__in=slugs)
    #             for cat in matching_cats:
    #                 explicit_category_ids.add(cat.id)
    #                 explicit_category_ids.update(
    #                     cat.children.values_list('id', flat=True))

    #             if explicit_category_ids:
    #                 queryset = queryset.filter(
    #                     category__id__in=explicit_category_ids)
    #                 queryset = queryset.filter(
    #                     ~Q(title__iregex=rf"(?i)({accessory_pattern})"))
    #             else:
    #                 return queryset.none()

    #     if search_query:
    #         search_terms = [t for t in re.split(
    #             r'\s+', search_query.lower()) if len(t) > 1]
    #         if not search_terms:
    #             return queryset.none()

    #         sq = re.escape(search_query)
    #         normalized_query = search_query.lower().strip()
    #         is_searching_accessory = any(
    #             word in normalized_query for word in accessory_keywords)

    #         # Strict AND filter
    #         strict_q = Q()
    #         for term in search_terms:
    #             strict_q &= Q(title__icontains=term)
    #         queryset = queryset.filter(strict_q)

    #         if not is_searching_accessory:
    #             queryset = queryset.filter(
    #                 ~Q(title__iregex=rf"(?i)({accessory_pattern})"))

    #         # Scoring
    #         phone_brands = ['apple', 'iphone', 'samsung', 'motorola', 'moto',
    #                         'google', 'pixel', 'oneplus', 'xiaomi', 'nokia', 'sony', 'lg']
    #         phone_specs = [r'\d+GB', r'unlocked', r'smartphone',
    #                        r'cell phone', r'dual sim', r'android', r'ios']

    #         queryset = queryset.annotate(
    #             brand_boost=Case(
    #                 When(
    #                     Q(title__iregex=rf"^({'|'.join(phone_brands)})"), then=Value(80.0)),
    #                 default=Value(0.0),
    #                 output_field=FloatField(),
    #             ),
    #             direct_match=Case(
    #                 When(title__iregex=rf'^{sq}', then=Value(50.0)),
    #                 When(title__icontains=search_query, then=Value(20.0)),
    #                 default=Value(0.0),
    #                 output_field=FloatField(),
    #             ),
    #             specs_boost=Case(
    #                 When(Q(title__iregex=rf"(?i)({'|'.join(phone_specs)})"), then=Value(
    #                     30.0)) if not is_searching_accessory else When(Q(pk__isnull=False), then=Value(0.0)),
    #                 default=Value(0.0),
    #                 output_field=FloatField(),
    #             ),
    #         ).annotate(
    #             final_relevance=F('brand_boost') +
    #             F('direct_match') + F('specs_boost')
    #         )

    #     if is_low:
    #         queryset = queryset.annotate(min_p=Min('listings__price')).filter(
    #             min_p__gt=0).order_by('min_p')

    #     elif is_high:
    #         queryset = queryset.annotate(min_p=Min('listings__price')).filter(
    #             min_p__gt=0).order_by('-min_p')

    #     elif is_newest:
    #         queryset = queryset.order_by('-created_at')

    #     elif is_best:
    #         if search_query:
    #             queryset = queryset.order_by('-final_relevance', '-created_at')
    #         else:
    #             queryset = queryset.order_by('-created_at')

    #     else:
    #         # Default sorting
    #         if search_query:
    #             queryset = queryset.order_by('-final_relevance', '-created_at')
    #         else:
    #             queryset = queryset.order_by('-created_at')

    #     if min_price or max_price:
    #         queryset = queryset.annotate(
    #             min_listing_price=Min('listings__price'))

    #     if min_price:
    #         try:
    #             queryset = queryset.filter(
    #                 min_listing_price__gte=float(min_price))
    #         except ValueError:
    #             pass

    #     if max_price:
    #         try:
    #             queryset = queryset.filter(
    #                 min_listing_price__lte=float(max_price))
    #         except ValueError:
    #             pass

    #     return queryset.distinct()


    def get_queryset(self):
        queryset = super().get_queryset()

        search_query = self.request.query_params.get('search', '').strip()
        sort = self.request.query_params.get('sort', '').strip()

        # 1. Smart Sort Detection
        is_low = sort in ['price_low', 'lowest_price', 'Lowest Price'] or 'price_low' in self.request.query_params
        is_high = sort in ['price_high', 'highest_price', 'Highest Price'] or 'price_high' in self.request.query_params
        is_newest = sort in ['newest', 'Newest'] or 'newest' in self.request.query_params
        is_best = sort in ['best_deal', 'Best Deal'] or 'best_deal' in self.request.query_params

        min_price = self.request.query_params.get('min_price', '').strip()
        max_price = self.request.query_params.get('max_price', '').strip()

        # 2. Base Quality Filter
        queryset = queryset.filter(
            title__isnull=False,
            main_image__isnull=False,
            listings__price__gt=0,
            listings__is_available=True,
        ).exclude(title='', main_image='')

        # 3. Category & Accessory Logic
        category_input = self.request.query_params.getlist('category')
        explicit_category_ids = set()

        accessory_keywords = [
            'power bank', 'powerbank', 'solar', 'cable', 'charger', 'charging',
            'case', 'cover', 'box', 'station', 'stand', 'holder', 'mount',
            'tag', 'sticker', 'bag', 'kit', 'parts', 'lens', 'stabilizer', 'gimbal',
            'replacement', 'repair', 'tripod', 'strap', 'film', 'glass', 'battery', 'cord',
            'protector', 'adapter', 'screen guard', 'controller', 'gaming controller',
            'printer', 'cutting machine', 'poster', 'aux', 'usb board', 'connector',
            'price tag', 'thermal printer', 'cup holder', 'attachment lens',
            'converter', 'transmission', 'fill light', 'lighting', 'storage box',
            'pushchair', 'stroller', 'gaming controller', 'docking station'
        ]
        accessory_pattern = '|'.join(re.escape(w) for w in accessory_keywords)

        if category_input:
            slugs = []
            for item in category_input:
                slugs.extend([s.strip() for s in item.split(',') if s.strip()])
            if slugs:
                matching_cats = Category.objects.filter(slug__in=slugs)
                for cat in matching_cats:
                    explicit_category_ids.add(cat.id)
                    explicit_category_ids.update(cat.children.values_list('id', flat=True))

                if explicit_category_ids:
                    queryset = queryset.filter(category__id__in=explicit_category_ids)
                    queryset = queryset.filter(~Q(title__iregex=rf"(?i)({accessory_pattern})"))
                else:
                    return queryset.none()

        # 4. Search and Relevance Scoring
        if search_query:
            search_terms = [t for t in re.split(r'\s+', search_query.lower()) if len(t) > 1]
            if not search_terms:
                return queryset.none()

            sq = re.escape(search_query)
            normalized_query = search_query.lower().strip()
            is_searching_accessory = any(word in normalized_query for word in accessory_keywords)

            # Strict AND filter
            strict_q = Q()
            for term in search_terms:
                strict_q &= Q(title__icontains=term)
            queryset = queryset.filter(strict_q)

            if not is_searching_accessory:
                queryset = queryset.filter(~Q(title__iregex=rf"(?i)({accessory_pattern})"))

            # Category boost triggers
            phone_trigger = any(w in normalized_query for w in ['phone', 'mobile', 'cell', 'smartphone'])
            laptop_trigger = any(w in normalized_query for w in ['laptop', 'notebook', 'macbook', 'chromebook'])

            phone_brands = ['apple', 'iphone', 'samsung', 'motorola', 'moto', 'google', 'pixel', 'oneplus', 'xiaomi', 'nokia', 'sony', 'lg']
            phone_specs = [r'\d+GB', r'unlocked', r'smartphone', r'cell phone', r'dual sim', r'android', r'ios']

            # Build category_boost dynamically
            category_when = []
            if phone_trigger:
                category_when.append(
                    When(
                        Q(category__name__icontains='Smartphones') | Q(category__name__icontains='Cell Phones'),
                        then=Value(100.0)
                    )
                )
            if laptop_trigger:
                category_when.append(
                    When(
                        Q(category__name__icontains='Laptops'),
                        then=Value(100.0)
                    )
                )

            # Build specs_boost dynamically
            specs_when = []
            if not is_searching_accessory:
                specs_when.append(
                    When(
                        Q(title__iregex=rf"(?i)({'|'.join(phone_specs)})"),
                        then=Value(30.0)
                    )
                )

            queryset = queryset.annotate(
                category_boost=Case(
                    *category_when,
                    default=Value(0.0),
                    output_field=FloatField(),
                ),
                brand_boost=Case(
                    When(Q(title__iregex=rf"^({'|'.join(phone_brands)})"), then=Value(80.0)),
                    default=Value(0.0),
                    output_field=FloatField(),
                ),
                direct_match=Case(
                    When(title__iregex=rf'^{sq}', then=Value(50.0)),
                    When(title__icontains=search_query, then=Value(20.0)),
                    default=Value(0.0),
                    output_field=FloatField(),
                ),
                specs_boost=Case(
                    *specs_when,
                    default=Value(0.0),
                    output_field=FloatField(),
                ),
            ).annotate(
                final_relevance=F('category_boost') + F('brand_boost') + F('direct_match') + F('specs_boost')
            )

        # 5. Global Sorting Block
        if is_low:
            queryset = queryset.annotate(min_p=Min('listings__price')).filter(min_p__gt=0).order_by('min_p')
        elif is_high:
            queryset = queryset.annotate(min_p=Min('listings__price')).filter(min_p__gt=0).order_by('-min_p')
        elif is_newest:
            queryset = queryset.order_by('-created_at')
        elif is_best:
            if search_query:
                queryset = queryset.order_by('-final_relevance', '-created_at')
            else:
                queryset = queryset.order_by('-created_at')
        else:
            if search_query:
                queryset = queryset.order_by('-final_relevance', '-created_at')
            else:
                queryset = queryset.order_by('-created_at')

        # 6. Price Range Filter
        if min_price or max_price:
            queryset = queryset.annotate(min_listing_price=Min('listings__price'))
            if min_price:
                try:
                    queryset = queryset.filter(min_listing_price__gte=float(min_price))
                except ValueError:
                    pass
            if max_price:
                try:
                    queryset = queryset.filter(min_listing_price__lte=float(max_price))
                except ValueError:
                    pass

        return queryset.distinct()

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
                    'total_count':  total_count,
                    'total_pages':  total_pages,
                    'current_page': current_page,
                    'page_size':    page_size,
                    'has_next':     self.paginator.page.has_next(),
                    'has_previous': self.paginator.page.has_previous(),
                    'next_page':    current_page + 1 if self.paginator.page.has_next() else None,
                    'prev_page':    current_page - 1 if self.paginator.page.has_previous() else None,
                },
                'results': results,
            })

        serializer = self.get_serializer(queryset, many=True)
        return success_response({'results': serializer.data})

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.request.user and self.request.user.is_authenticated:
            from api_integration.models import CartItem, Favorite

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

        this_deal_listing = best_deal_product.listings.filter(
            is_available=True, price__gt=0).order_by('price').first()
        if not this_deal_listing:
            return error_response("No valid price found for this deal.", code=404)

        this_price = float(this_deal_listing.get_total_price())

        from django.db.models import Q, Max
        match_query = Q()
        if best_deal_product.gtin:
            match_query |= Q(product__gtin=best_deal_product.gtin)
        if best_deal_product.asin:
            match_query |= Q(product__asin=best_deal_product.asin)

        if not match_query:
            max_price_data = best_deal_product.listings.filter(
                is_available=True).aggregate(max_p=Max('price'))
        else:

            max_price_data = ProductListing.objects.filter(
                match_query,
                is_available=True
            ).aggregate(max_p=Max('price'))

        highest_market_price = float(max_price_data['max_p'] or this_price)

        savings = round(highest_market_price - this_price, 2)

        if savings > 0:
            with transaction.atomic():
                user = request.user

                current_total = float(
                    getattr(user, 'total_lifetime_savings', 0.0))
                user.total_lifetime_savings = current_total + savings
                user.save()

                SavingsActivity.objects.create(
                    user=user,
                    title=f"Saved by choosing best deal: {best_deal_product.title}",
                    saved_amount=savings
                )

            return success_response({
                "product": best_deal_product.title,
                "you_paid": this_price,
                "market_high": highest_market_price,
                "saved_amount": savings,
                "total_lifetime_savings": float(user.total_lifetime_savings)
            }, message="Savings recorded successfully based on best deal comparison!")

        return success_response({
            "saved_amount": 0,
            "message": "This is already the highest price or no comparison available."
        })



# -------------------------- Product Multi-Retailer Listings ReadOnly ViewSet --------------------------
class ProductListingViewSet(viewsets.ReadOnlyModelViewSet):
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


