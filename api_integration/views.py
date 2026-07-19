from django.utils import timezone
from datetime import timedelta
from django.db.models.functions import TruncDate
from django.db.models import Sum
from django.db.models import Q
from rapidfuzz import fuzz
from django.db.models import F
import time
import logging
from rest_framework import viewsets, generics
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q, Min, Count
from django.db import transaction
from django.core.cache import cache
import math
from rest_framework import permissions as drf_permissions

from api_integration.product_matcher import calculate_match_score, get_product_fingerprint

from .services.walmart_service import WalmartService
from .services.amazon_service import AmazonService
from .services.sephora_service import SephoraService
from .services.ebay_service import EbayRapidService
from .services.target_service import TargetService
from .services.wayfair_service import WayfairService
from .services.aliexpress_service import AliExpressService
from .services.bestbuy_service import BestBuyService
from .db_helpers import save_generic_product_to_db
from django.db.models import Q, Min
from difflib import SequenceMatcher
import re
from .models import (
    Product, ProductListing, Platform, Category,
    CartItem, SavingsActivity, Favorite, PriceAlert
)
from .serializers import (
    ProductSerializer, ProductDetailSerializer,
    ProductListingSerializer, PlatformSerializer,
    CategorySerializer, PriceHistorySerializer,
    CartItemSerializer, FavoriteSerializer, CategoryTreeSerializer, CategoryChildSerializer, PriceAlertSerializer
)
from notifications.models import Notification
from notifications.serializers import NotificationSerializer
from store.serializers import SellerProductSerializer
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import Q, Value, Case, When, FloatField, Min, Count
from django.db.models import Value
from .tasks import sync_amazon_task, sync_ebay_task, sync_walmart_task ,sync_all_platforms_task ,sync_ebay_task
logger = logging.getLogger(__name__)
from django.core.cache import cache

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
# Response Helpers
# ============================================================================


def success_response(data=None, message="Success", code=200):
    response = {
        "success":   True,
        "code":      code,
        "message":   message,
        "timestamp": int(time.time()),
        "data":      data or {},
    }
    if isinstance(data, dict) and 'pagination' in data:
        response['pagination'] = data.pop('pagination')
    return Response(response, status=code)


def error_response(message="Error", data=None, code=400):
    return Response({
        "success":   False,
        "code":      code,
        "message":   message,
        "timestamp": int(time.time()),
        "data":      data or {}
    }, status=code)


# ============================================================================
# Sync helpers
# ============================================================================

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


# ============================================================================
# Pagination
# ============================================================================

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# ============================================================================
# REST ViewSets
# ============================================================================


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


""" contains viewsets and API views for product listing, price comparison, and platform syncing. """
"""
views.py — compare_prices_api (improved version)
================================================
Change summary: 
• Import improved matching functions from product_matcher.py 
• Storage mismatch is now correctly detected (256GB vs 512GB → block) 
• RAM mismatch is detected 
• Brand normalizes ("Unlocked Apple" → "Apple") 
• DB candidate query is smarter — AND filter option with core words 
• Weighted score: Jaccard×0.4 + token_sort×0.35 + partial×0.25
"""


# ── your existing imports ──
# from .models import Product, ProductListing
# from .utils import clean_display_title, success_response, error_response
# from .product_matcher import product_match_score, extract_core_title

# ══════════════════════════════════
# copy (or import) from product_matcher.py
# ══════════════════════════════════

VARIANT_TOKENS = {
    'max', 'plus', 'ultra', 'mini', 'pro', 'lite', 'fe',
    'air', 'fold', 'flip', 'edge', 'note', 'x', 'xl',
}

STORAGE_PATTERN = re.compile(r'(\d+)\s*(gb|tb|mb)', re.IGNORECASE)
RAM_PATTERN = re.compile(r'(\d+)\s*gb\s*ram',   re.IGNORECASE)

NOISE_PATTERNS = [
    r'\(.*?\)',
    r'\[.*?\]',
    r'opens?\s+in\s+a\s+new\s+(window|tab).*',
    r'\d+\s*%?\s*opens?.*',
    r'\b(at&t|t[\-]?mobile|verizon|sprint|tmobile|att)\b',
    r'\b(unlocked|locked|factory|carrier)\b',
    r'\b(new|used|open[\s-]?box)\b',
    r'\b(great|good|fair|excellent|mint|poor)\s*(condition)?\b',
    r'\b(refurbished|restored|renewed|remanufactured|seller[\s-]refurbished)\b',
    r'\b(free\s*shipping|ships\s*fast)\b',
    r'\b(black|white|silver|gold|blue|red|green|pink|purple|titanium'
    r'|midnight|starlight|natural|cosmic|desert|graphite|sierra|alpine'
    r'|yellow|orange|lavender|sage|teal|burgundy|rose|space[\s]?gray)\b',
    r'\b(very|sealed|brand)\b',
    r'-\s*$',
]

BRAND_ALIASES = {
    'unlocked apple': 'apple',
    'apple unlocked': 'apple',
    'sealed apple':   'apple',
    'new apple':      'apple',
}


def extract_storage(title: str) -> dict:
    result = {}
    title_lower = title.lower()
    ram_match = RAM_PATTERN.search(title_lower)
    if ram_match:
        result['ram'] = f"{ram_match.group(1)}gb"
        title_lower = title_lower[:ram_match.start()] + \
            title_lower[ram_match.end():]
    for val, unit in STORAGE_PATTERN.findall(title_lower):
        unit_lower = unit.lower()
        if unit_lower == 'tb':
            result['storage'] = f"{val}tb"
            break
        elif unit_lower == 'gb' and 'storage' not in result:
            result['storage'] = f"{val}gb"
    return result


def normalize_brand(title: str) -> str:
    lower = title.lower().strip()
    for alias, canonical in BRAND_ALIASES.items():
        if lower.startswith(alias):
            return canonical.title() + title[len(alias):]
    return title


def extract_core_title(title: str) -> str:
    core = normalize_brand(title)
    core = re.sub(r'(\d+)\s*(gb|tb|mb)\b', r'\1', core, flags=re.IGNORECASE)
    for pattern in NOISE_PATTERNS:
        core = re.sub(pattern, ' ', core, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', core).strip(' -,|/')


def variant_check(core1: str, core2: str) -> bool:
    t1 = set(core1.lower().split()) & VARIANT_TOKENS
    t2 = set(core2.lower().split()) & VARIANT_TOKENS
    return t1 == t2


def storage_check(title1: str, title2: str) -> bool:
    s1 = extract_storage(title1)
    s2 = extract_storage(title2)
    for key in ('storage', 'ram'):
        v1, v2 = s1.get(key), s2.get(key)
        if v1 and v2 and v1 != v2:
            return False
    return True


def model_number_check(core1: str, core2: str) -> bool:
    def get_model_nums(core):
        tmp = re.sub(r'\b(256|512|128|64|32|1024|2048)\b', '', core)
        return set(re.findall(r'\b\d+\b', tmp))
    n1, n2 = get_model_nums(core1), get_model_nums(core2)
    if not n1 and not n2:
        return True
    if not n1 or not n2:
        return True
    return bool(n1 & n2) and len(n1 - n2) == 0


def product_match_score(title1: str, title2: str) -> float:

    if not storage_check(title1, title2):
        return 0.0

    core1 = extract_core_title(title1)
    core2 = extract_core_title(title2)

    if not variant_check(core1, core2):
        return 0.0
    if not model_number_check(core1, core2):
        return 0.0

    tokens1 = set(core1.lower().split())
    tokens2 = set(core2.lower().split())
    jaccard = 0.0
    if tokens1 or tokens2:
        jaccard = len(tokens1 & tokens2) / len(tokens1 | tokens2) * 100

    token_sort = fuzz.token_sort_ratio(core1, core2)
    partial = fuzz.partial_ratio(core1, core2)

    return round((jaccard * 0.40) + (token_sort * 0.35) + (partial * 0.25), 1)




@api_view(['GET'])
@permission_classes([IsAuthenticated])
def compare_prices_api(request, slug):
    import time

    product = Product.objects.filter(slug=slug, is_active=True).first()
    if not product:
        return error_response("Product not found", code=404)

    def deep_clean(text):
        noise = ['restored', 'renewed', 'refurbished', 'pre-owned', 'used',
                 'excellent', 'mint', 'condition']
        text = text.lower()
        for word in noise:
            text = re.sub(r'\b' + re.escape(word) + r'\b', '', text)
        return re.sub(r'\s+', ' ', text).strip()

    target_clean = deep_clean(product.title)

    existing_platforms = ProductListing.objects.filter(
        product=product, is_available=True
    ).values_list('platform__code', flat=True).distinct()

    sync_triggered = False
    if len(existing_platforms) < 3:
        cache_key = f"sync_triggered_{product.id}"
        if not cache.get(cache_key): 
            fingerprint = get_product_fingerprint(product.title)
            query_for_api = fingerprint['core_name'] or product.title[:50]
            sync_all_platforms_task.delay(query_for_api, limit=5)
            cache.set(cache_key, True, timeout=3600)  
            sync_triggered = True

    search_words = [w for w in target_clean.split() if len(w) > 2][:6]

    if search_words:
        word_q = Q()
        for word in search_words:
            word_q |= Q(title__icontains=word)

        # category filter
        if product.category:
            word_q &= Q(category=product.category)

        candidates = Product.objects.filter(
            word_q, is_active=True
        ).only('id', 'title', 'brand')[:300]
    else:
        candidates = Product.objects.none()

    matched_ids = [product.id]

    accessory_words = ['cable', 'case', 'cover', 'charger', 'stand', 'mount']
    target_is_acc = any(w in target_clean.lower() for w in accessory_words)

    for cand in candidates:
        if cand.id == product.id:
            continue

        cand_clean = deep_clean(cand.title)

        if target_is_acc != any(w in cand_clean for w in accessory_words):
            continue

        score = fuzz.token_set_ratio(target_clean, cand_clean)
        if score >= 60:
            matched_ids.append(cand.id)

    listings = ProductListing.objects.filter(
        product__id__in=matched_ids,
        is_available=True,
        price__gt=0
    ).select_related('platform', 'product').order_by('price')

    comparison_list = []
    seen_platforms = set()
    prices = []

    for l in listings:
        if l.platform.code in seen_platforms:
            continue
        seen_platforms.add(l.platform.code)

        total_p = float(l.get_total_price())
        prices.append(total_p)

        img_url = l.product.main_image
        if img_url and not str(img_url).startswith('http'):
            img_url = request.build_absolute_uri(img_url)

        comparison_list.append({
           'platform': l.platform.name,
            'platform_code': l.platform.code,
            'product_id': l.product.id,
            'listing_id': l.external_id,
            'price': float(l.price),
            'total_price': total_p,
            'url': l.external_url,
            'seller': l.seller_username or "Verified Store",
            'main_image': img_url,
            'shipping_cost': str(l.shipping_cost),
            'is_available': l.is_available,
            'has_coupon': l.has_coupon,
            'coupon_text': l.coupon_text,
            'deal_badge': l.deal_badge,
            'clean_title': clean_display_title(l.product.title),
        })

    return success_response({
        'product': {
            'id': product.id,
            'title': clean_display_title(product.title),
            'main_image': product.main_image,
        },
        'meta': {
            'total_deals_found': len(comparison_list),
            'sync_triggered': sync_triggered,
        },
        'price_analysis': {
            'lowest_price': min(prices) if prices else 0,
            'highest_price': max(prices) if prices else 0,
            'potential_savings': round(max(prices) - min(prices), 2) if len(prices) > 1 else 0
        },
        'price_comparison': comparison_list,
        'best_deal': comparison_list[0] if comparison_list else None
    })
# @api_view(['GET'])
# @permission_classes([IsAuthenticated])
# def compare_prices_api(request, slug):
#     # 1. Fetch the main product
#     product = Product.objects.filter(slug=slug, is_active=True).first()
#     if not product:
#         return error_response("Product not found", code=404)

#     target_title = clean_display_title(product.title)

#     # 2. Check current retailers count in DB
#     existing_platforms_count = ProductListing.objects.filter(
#         product=product,
#         is_available=True
#     ).values('platform').distinct().count()

#     sync_triggered = False

#     # 3. Trigger Background Sync if less than 3 retailers exist
#     cache_key = f"sync_lock_{product.id}"
#     if existing_platforms_count < 3 and not cache.get(cache_key):
#         fingerprint = get_product_fingerprint(target_title)
#         query_for_api = fingerprint['core_name'] or target_title[:50]

#         # শুধু 3টা priority platform, একে একে 60 sec gap এ
#         priority_tasks = [
#             sync_amazon_task.s(query_for_api, 3),
#             sync_ebay_task.s(query_for_api, 3),
#             sync_walmart_task.s(query_for_api, 3),
#         ]
#         for i, task in enumerate(priority_tasks):
#             task.apply_async(countdown=i * 60)

#         cache.set(cache_key, True, 86400)  # 24 ঘণ্টা lock
#         sync_triggered = True

#     # 4. Search for matching products in the DB
#     candidates = Product.objects.filter(
#         category=product.category,
#         is_active=True
#     ).exclude(id=product.id).only('id', 'title', 'brand')

#     matched_ids = [product.id]
#     THRESHOLD = 75

#     accessory_words = ['cable', 'case', 'cover', 'charger', 'stand', 'mount', 'station']
#     target_is_acc = any(w in target_title.lower() for w in accessory_words)

#     for cand in candidates:
#         cand_title_lower = cand.title.lower()
#         cand_is_acc = any(w in cand_title_lower for w in accessory_words)
#         if target_is_acc != cand_is_acc:
#             continue
#         score = calculate_match_score(product.title, cand.title)
#         if score >= THRESHOLD:
#             matched_ids.append(cand.id)

#     # 5. Fetch all listings
#     listings = ProductListing.objects.filter(
#         product__id__in=matched_ids,
#         is_available=True,
#         price__gt=0
#     ).select_related('platform', 'product').order_by('price')

#     # 6. Format comparison list
#     comparison_list = []
#     seen_urls = set()
#     prices = []

#     for listing in listings:
#         if listing.external_url in seen_urls:
#             continue
#         seen_urls.add(listing.external_url)

#         total_p = float(listing.get_total_price())
#         prices.append(total_p)

#         comparison_list.append({
#             'platform': listing.platform.name,
#             'platform_code': listing.platform.code,
#             'listing_id': listing.external_id,
#             'clean_title': clean_display_title(listing.product.title),
#             'price': float(listing.price),
#             'total_price': total_p,
#             'url': listing.external_url,
#             'main_image': listing.product.main_image,
#             'seller': listing.seller_username or "Verified Store",
#         })

#     # 7. Price Analysis
#     analysis = {
#         'lowest_price': min(prices) if prices else 0,
#         'highest_price': max(prices) if prices else 0,
#         'potential_savings': round(max(prices) - min(prices), 2) if len(prices) > 1 else 0
#     }

#     return success_response({
#         'product': {
#             'id': product.id,
#             'title': target_title,
#             'slug': product.slug,
#             'brand': product.brand,
#             'main_image': product.main_image,
#         },
#         'meta': {
#             'total_deals_found': len(comparison_list),
#             'sync_triggered': sync_triggered,
#             'message': "Searching for more deals..." if sync_triggered else "Results updated."
#         },
#         'price_analysis': analysis,
#         'price_comparison': comparison_list,
#         'best_deal': comparison_list[0] if comparison_list else None
#     }, message="Price comparison fetched successfully")


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


class PlatformViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PlatformSerializer
    lookup_field = 'code'

    def get_queryset(self):
        return Platform.objects.filter(api_enabled=True) | Platform.objects.filter(
            code__startswith='local-seller-'
        )


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    lookup_field = 'slug'

    @action(detail=False, methods=['get'], url_path='tree')
    def tree(self, request):
        parents = Category.objects.filter(
            parent=None).prefetch_related('children')
        serializer = CategoryTreeSerializer(parents, many=True)
        return Response({
            "success": True,
            "code": 200,
            "message": "Category tree retrieved successfully.",
            "data": serializer.data
        })


class CategoryTreeView(APIView):
    permission_classes = [drf_permissions.AllowAny]

    def get(self, request):
        parents = Category.objects.filter(
            parent=None).prefetch_related('children')
        serializer = CategoryTreeSerializer(parents, many=True)
        return Response({
            "success": True,
            "code": 200,
            "message": "Category tree retrieved successfully.",
            "data": serializer.data
        })


class CategoryParentListView(APIView):
    """Only parent categories"""

    def get(self, request):
        parents = Category.objects.filter(
            parent=None).only('id', 'name', 'slug')
        serializer = CategoryChildSerializer(parents, many=True)
        return Response({
            "success": True,
            "code": 200,
            "message": "Parent categories retrieved.",
            "data": serializer.data
        })


class CategoryChildrenView(APIView):
    """Children of a parent"""

    def get(self, request, slug):
        try:
            parent = Category.objects.get(slug=slug, parent=None)
        except Category.DoesNotExist:
            return Response({
                "success": False,
                "code": 404,
                "message": "Category not found.",
                "data": {}
            }, status=404)

        children = parent.children.all().only('id', 'name', 'slug')
        serializer = CategoryChildSerializer(children, many=True)
        return Response({
            "success": True,
            "code": 200,
            "message": f"Children of '{parent.name}' retrieved.",
            "data": {
                "parent": {"id": parent.id, "name": parent.name, "slug": parent.slug},
                "children": serializer.data
            }
        })
# ============================================================================
# Custom API Endpoints
# ============================================================================


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
            "success":   True,
            "code":      code,
            "message":   message,
            "timestamp": int(time.time()),
            "data":      data,
        }, status=code)

    def _error(self, message="Error", code=400):
        return Response({
            "success":   False,
            "code":      code,
            "message":   message,
            "timestamp": int(time.time()),
            "data":      {},
        }, status=code)

    def create(self, request, *args, **kwargs):
        product_id = request.data.get('product_id')
        quantity = request.data.get('quantity', 1)

        if not product_id:
            return self._error("product_id is required", code=400)

        product = None

        # 1. SellerProduct দিয়ে খোঁজো
        try:
            from store.models import SellerProduct
            from api_integration.models import Product, Category
            from django.utils.text import slugify
            import uuid

            seller_product_obj = SellerProduct.objects.get(
                id=product_id, status='APPROVED')
            product = seller_product_obj.linked_product

            # linked_product নেই — নতুন Product বানিয়ে link করো
            if not product:
                # category match করো
                category = None
                if seller_product_obj.category:
                    category = seller_product_obj.category  # already a Category FK? check করো
                
                slug = slugify(seller_product_obj.title)[:490]
                # slug unique হতে হবে
                if Product.objects.filter(slug=slug).exists():
                    slug = f"{slug}-{str(uuid.uuid4())[:8]}"

                product = Product.objects.create(
                    title=seller_product_obj.title,
                    slug=slug,
                    description=seller_product_obj.description or '',
                    brand=seller_product_obj.brand or '',
                    main_image='',
                    category=category,
                    is_active=True,
                )

                seller_product_obj.linked_product = product
                seller_product_obj.save(update_fields=['linked_product'])

        except SellerProduct.DoesNotExist:
            pass

        # 2. fallback — Product table এ সরাসরি খোঁজো
        if not product:
            try:
                product = Product.objects.get(id=product_id)
            except Product.DoesNotExist:
                pass

        if not product:
            return self._error(f"Product not found with id '{product_id}'", code=404)

        if CartItem.objects.filter(user=request.user, product=product).exists():
            return self._error("This product is already in your cart", code=400)

        cart_item = CartItem.objects.create(
            user=request.user,
            product=product,
            quantity=quantity,
        )

        serializer = self.get_serializer(cart_item)
        return self._success(serializer.data, message="Item added to cart", code=201)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return self._success(serializer.data, message="Cart item fetched")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        grouped = {}
        total_items = 0
        total_price = 0.0

        for item in serializer.data:
            listing = item.get('listing')
            if not listing:
                continue

            platform = listing.get('platform_name', 'Unknown')

            entry = {
                "id":            item['id'],
                "product":       item['product'],
                "product_title": item['product_title'],
                "product_image": item['product_image'],
                "quantity":      item['quantity'],
                "listing":       listing,
            }

            if platform not in grouped:
                grouped[platform] = []

            grouped[platform].append(entry)

            total_items += item['quantity']
            total_price += listing.get('total_price', 0.0) * item['quantity']

        summary = {
            "total_platforms": len(grouped),
            "total_items":     total_items,
            "total_price":     round(total_price, 2),
            "currency":        "USD",
        }

        return self._success(
            {"summary": summary, "platforms": grouped},
            message="Cart items fetched"
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data=request.data, partial=partial)
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

        # . Definite data collection
        optimized_data = {}  # {platform: [items]}
        single_store_data = {'BestBuy': []}

        total_opt_price = 0
        total_single_price = 0

        for item in cart_items:
            # Main Logic: Best cheap deal among all listings
            best_listing = ProductListing.objects.filter(
                product=item.product).order_by('price').first()

            item_total = float(best_listing.price) * item.quantity
            total_opt_price += item_total

            plat = best_listing.platform.name
            if plat not in optimized_data:
                optimized_data[plat] = []
            optimized_data[plat].append(
                {"title": item.product.title, "price": float(best_listing.price)})

        total_saved = 50.00

        return success_response({
            "options": {
                "single_store": {
                    "title": "Single Store",
                    "platform": "Best Buy",
                    "total_cost": 1500.00,
                    "shipments": 1
                },
                "optimized_split": {
                    "title": "Optimized Split",
                    "total_cost": total_opt_price,
                    "total_saved": total_saved,
                    "shipments": len(optimized_data),
                    "breakdown": optimized_data
                }
            },
            "savings_breakdown": {
                "original_total": 1500.00,
                "coupon_savings": 50.00,
                "price_match_comparison": total_saved,
                "final_price": total_opt_price
            }
        })

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
            product = item.product

            cheapest = ProductListing.objects.filter(
                product=product, is_available=True
            ).order_by('price').first()

            if not cheapest:
                continue

            current_price = cheapest.price * qty
            original_total += current_price
            opt_price = cheapest.price * qty
            optimized_total += opt_price

            item_saved = float(current_price - opt_price)
            if item_saved > 0:
                activities_to_create.append(SavingsActivity(
                    user=request.user,
                    title=product.title,
                    saved_amount=item_saved,
                ))

        total_saved = float(original_total - optimized_total)

        with transaction.atomic():
            user = request.user
            if total_saved > 0:
                current_savings = getattr(user, 'total_lifetime_savings', 0)
                user.total_lifetime_savings = float(
                    current_savings) + total_saved
                user.save()
                if activities_to_create:
                    SavingsActivity.objects.bulk_create(activities_to_create)
            cart_items.delete()

        recent = SavingsActivity.objects.filter(
            user=request.user).order_by('-created_at')[:5]
        data = {
            "total_paid":             float(optimized_total),
            "total_saved_this_order": total_saved,
            "lifetime_savings_now":   float(getattr(user, 'total_lifetime_savings', 0)),
            "recent_activity": [
                {"title": a.title, "saved_amount": float(
                    a.saved_amount), "date": a.time_ago}
                for a in recent
            ],
        }
        return self._success(data, message="Checkout completed successfully")

    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        user = request.user
        recent = SavingsActivity.objects.filter(
            user=user).order_by('-created_at')[:5]
        data = {
            "total_lifetime_savings": float(getattr(user, 'total_lifetime_savings', 0.0)),
            "recent_activity": [
                {"title": a.title, "saved_amount": float(
                    a.saved_amount), "date": a.time_ago}
                for a in recent
            ],
        }
        return self._success(data, message="Dashboard data fetched successfully")


class DashboardSavingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        recent = SavingsActivity.objects.filter(
            user=user
        ).order_by('-created_at')[:5]

        thirty_days_ago = timezone.now().date() - timedelta(days=30)

        trend_data = SavingsActivity.objects.filter(
            user=user,
            created_at__date__gte=thirty_days_ago
        ).annotate(
            day=TruncDate('created_at')
        ).values('day').annotate(
            total=Sum('saved_amount')
        ).order_by('day')

        trend_map = {item['day'].strftime(
            '%Y-%m-%d'): float(item['total']) for item in trend_data}

        graph_list = []
        for i in range(30, -1, -1): 
            date_str = (timezone.now().date() -
                        timedelta(days=i)).strftime('%Y-%m-%d')
            graph_list.append({
                "date": date_str,
                "amount": trend_map.get(date_str, 0.0)  
            })

        data = {
            "total_lifetime_savings": float(getattr(user, 'total_lifetime_savings', 0.0)),
            "savings_trend": graph_list,  
            "recent_activity": [
                {
                    "title": a.title,
                    "saved_amount": float(a.saved_amount),
                    "date": a.time_ago
                } for a in recent
            ],
        }

        return success_response(data, message="Dashboard data fetched successfully")


@api_view(['GET'])
def category_compare_prices(request, slug):
    try:
        category = Category.objects.get(slug=slug)
    except Category.DoesNotExist:
        return error_response(f'Category "{slug}" not found', code=404)

    category_slugs = [category.slug]
    children = category.children.all()
    if children.exists():
        category_slugs += list(children.values_list('slug', flat=True))

    sort = request.GET.get('sort', 'price_low')
    platform_filter = request.GET.get('platform')

    products = Product.objects.filter(
        category__slug__in=category_slugs,
        is_active=True,
        listings__is_available=True,
        listings__price__gt=0
    ).prefetch_related('listings__platform').distinct()

    if sort == 'price_low':
        products = products.annotate(min_price=Min(
            'listings__price')).order_by('min_price')
    elif sort == 'price_high':
        products = products.annotate(min_price=Min(
            'listings__price')).order_by('-min_price')
    elif sort == 'newest':
        products = products.order_by('-created_at')
    elif sort == 'popular':
        products = products.annotate(listing_count=Count(
            'listings')).order_by('-listing_count')
    else:
        products = products.annotate(min_price=Min(
            'listings__price')).order_by('min_price')

    try:
        page = max(1, int(request.GET.get('page', 1)))
        page_size = min(100, max(1, int(request.GET.get('page_size', 100))))
    except (ValueError, TypeError):
        page, page_size = 1, 100

    total_count = products.count()
    total_pages = (total_count + page_size - 1) // page_size
    offset = (page - 1) * page_size
    products_page = products[offset: offset + page_size]

    results = []
    for product in products_page:
        listings = product.listings.filter(
            is_available=True).select_related('platform')
        if platform_filter:
            listings = listings.filter(platform__code=platform_filter)
        if not listings.exists():
            continue

        price_comparison = []
        for listing in listings.order_by('price'):
            price_comparison.append({
                'platform':            listing.platform.name,
                'platform_code':       listing.platform.code,
                'price':               float(listing.price),
                'currency':            listing.currency,
                'original_price':      float(listing.original_price) if listing.original_price else None,
                'discount_percentage': float(listing.discount_percentage) if listing.discount_percentage else None,
                'shipping_cost':       float(listing.shipping_cost),
                'free_shipping':       listing.free_shipping,
                'total_price':         float(listing.get_total_price()),
                'condition':           listing.condition,
                'url':                 listing.external_url,
            })

        best_deal = price_comparison[0] if price_comparison else None
        results.append({
            'product': {
                'id':            product.id,
                'title':         product.title,
                'slug':          product.slug,
                'main_image':    product.main_image,
                'category':      category.name,
                'category_slug': category.slug,
            },
            'best_deal':        best_deal,
            'lowest_price':     best_deal['price'] if best_deal else None,
            'platforms_count':  len(price_comparison),
            'price_comparison': price_comparison,
        })

    valid_results = [r for r in results if r['lowest_price']
                     and r['lowest_price'] > 0]
    best_overall_deal = None
    if valid_results:
        best = min(valid_results, key=lambda x: x['lowest_price'])
        best_overall_deal = {
            'product_id':          best['product']['id'],
            'title':               best['product']['title'],
            'price':               best['lowest_price'],
            'currency':            best['best_deal']['currency'],
            'discount_percentage': best['best_deal']['discount_percentage'],
            'platform':            best['best_deal']['platform'],
            'platform_code':       best['best_deal']['platform_code'],
            'url':                 best['best_deal']['url'],
            'main_image':          best['product']['main_image'],
        }

    return success_response({
        'category': {
            'id':            category.id,
            'name':          category.name,
            'slug':          category.slug,
            'parent':        category.parent.name if category.parent else None,
            'subcategories': list(children.values('id', 'name', 'slug')),
        },
        'pagination': {
            'total_products': total_count,
            'total_pages':    total_pages,
            'current_page':   page,
            'page_size':      page_size,
            'has_next':       page < total_pages,
            'has_prev':       page > 1,
        },
        'sort':              sort,
        'filters':           {'platform': platform_filter},
        'best_overall_deal': best_overall_deal,
        'results':           results,
    }, message=f"Price comparison for '{category.name}'")


# ============================================================================
# Favorites ViewSet
# ============================================================================

class FavoriteViewSet(viewsets.ModelViewSet):
    serializer_class = FavoriteSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'delete']

    def get_queryset(self):
        return Favorite.objects.filter(
            user=self.request.user
        ).select_related('product')

    def _success(self, data, message="Success", code=200):
        return Response({
            "success":   True,
            "code":      code,
            "message":   message,
            "timestamp": int(time.time()),
            "data":      data,
        }, status=code)

    def _error(self, message="Error", code=400):
        return Response({
            "success":   False,
            "code":      code,
            "message":   message,
            "timestamp": int(time.time()),
            "data":      {},
        }, status=code)

    def create(self, request, *args, **kwargs):
        product_id = request.data.get('product_id')

        if not product_id:
            return self._error("product_id is required", code=400)

        product = None

        try:
            from store.models import SellerProduct
            seller_product = SellerProduct.objects.get(
                id=product_id, status='APPROVED')
            product = seller_product.linked_product
        except SellerProduct.DoesNotExist:
            pass

        if not product:
            product = Product.objects.filter(id=product_id).first()

        if not product:
            return self._error("Product not found", code=404)

        favorite, created = Favorite.objects.get_or_create(
            user=request.user, product=product
        )
        if not created:
            return self._error("Product already in favorites", code=400)

        serializer = self.get_serializer(favorite)
        return self._success(serializer.data, message="Added to favorites", code=201)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response({
            "success": True, "code": 200,
            "message": "Removed from favorites",
            "timestamp": int(time.time()),
            "data": {},
        }, status=200)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        favorite_ids = set(queryset.values_list('product_id', flat=True))

        serializer = FavoriteSerializer(
            queryset,
            many=True,
            context={
                **self.get_serializer_context(),
                'favorite_ids': favorite_ids,
            }
        )

        return Response({
            "success": True, "code": 200,
            "message": "Favorites fetched",
            "timestamp": int(time.time()),
            "data": {"count": queryset.count(), "favorites": serializer.data},
        }, status=200)

    @action(detail=False, methods=['delete'], url_path='remove')
    def remove(self, request):
        product_id = request.data.get('product_id')

        if not product_id:
            return self._error("product_id is required", code=400)

        favorite = Favorite.objects.filter(
            user=request.user, product_id=product_id
        ).first()

        if not favorite:
            return self._error("Favorite not found", code=404)

        favorite.delete()
        return self._success(
            {},
            message="Removed from favorites",
            code=200,
        )

    @action(detail=False, methods=['get'], url_path='check/(?P<product_id>[^/.]+)')
    def check(self, request, product_id=None):
        is_favorite = Favorite.objects.filter(
            user=request.user, product_id=product_id).exists()
        return Response({
            "success": True, "code": 200, "message": "Checked",
            "timestamp": int(time.time()),
            "data": {"is_favorite": is_favorite, "product_id": product_id},
        })

    @action(detail=False, methods=['post'], url_path='toggle')
    def toggle(self, request):
        product_id = request.data.get('product_id')

        if not product_id:
            return self._error("product_id is required", code=400)

        product = None

        try:
            from store.models import SellerProduct
            seller_product = SellerProduct.objects.get(
                id=product_id, status='APPROVED')
            product = seller_product.linked_product
        except SellerProduct.DoesNotExist:
            pass

        if not product:
            product = Product.objects.filter(id=product_id).first()

        if not product:
            return self._error("Product not found", code=404)

        favorite = Favorite.objects.filter(
            user=request.user, product=product).first()
        if favorite:
            favorite.delete()
            return self._success(
                {"is_favorite": False, "product_id": product_id},
                message="Removed from favorites",
            )

        Favorite.objects.create(user=request.user, product=product)
        return self._success(
            {"is_favorite": True, "product_id": product_id},
            message="Added to favorites",
            code=201,
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def amazon_promo_details(request):
    promo_code = request.GET.get('promo_code', '')
    country = request.GET.get('country', 'US')

    if not promo_code:
        return error_response('promo_code is required', code=400)

    service = AmazonService()
    data = service.get_promo_code_details(promo_code, country)

    if not data:
        return error_response('Promo code not found or expired', code=404)

    return success_response(data, message="Promo code details fetched")


class PriceAlertViewSet(viewsets.ModelViewSet):
    """User can set up to 5 alerts (Free) or Unlimited (Paid)"""
    permission_classes = [IsAuthenticated]
    serializer_class = PriceAlertSerializer

    def get_queryset(self):
        return PriceAlert.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        user = request.user
        sub = getattr(user, 'subscription', None)

        # ১. সাবস্ক্রিপশন লিমিট চেক (ডক অনুযায়ী)
        alert_count = PriceAlert.objects.filter(
            user=user, is_active=True).count()
        limit = sub.plan.price_alerts_limit if sub and sub.is_active else 5

        if limit != -1 and alert_count >= limit:
            return Response({
                "success": False,
                "message": f"Alert limit reached. You can only set {limit} alerts."
            }, status=400)

        return super().create(request, *args, **kwargs)


from django.shortcuts import redirect
from django.urls import reverse
import requests
def get_title_from_barcode_safely(barcode):
    """একাধিক সোর্স থেকে টাইটেল খোঁজা এবং এরর হ্যান্ডল করা"""
    sources = [
        f"https://api.upcitemdb.com/prod/trial/lookup?upc={barcode}",
        f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    ]
    
    for url in sources:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                # upcitemdb logic
                if 'items' in data and len(data['items']) > 0:
                    return data['items'][0].get('title')
                # openfoodfacts logic
                if data.get('status') == 1:
                    return data.get('product', {}).get('product_name')
        except Exception:
            continue

    # Fallback to eBay Search API using our EbayRapidService
    try:
        from .services.ebay_service import EbayRapidService
        ebay = EbayRapidService()
        items = ebay.search_products(barcode, limit=1)
        if items and len(items) > 0:
            title = items[0].get('title')
            if title:
                return title
    except Exception:
        pass

    return None




@api_view(['GET'])
@permission_classes([IsAuthenticated])
def barcode_scanner_pipeline(request):
    """
    In English:
    1. Receives barcode.
    2. Converts to product name using external lookup.
    3. Finds or Creates a product in DB to get a slug.
    4. Internally redirects to the existing 'compare_prices_api' logic.
    """
    # Check subscription permission
    subscription = getattr(request.user, 'subscription', None)
    if not subscription or not subscription.is_active:
        return error_response("Please subscribe to a plan to use barcode scanner.", code=403)

    barcode = request.query_params.get('code', '').strip()
    if not barcode:
        return error_response("Barcode is required", code=400)

    product = Product.objects.filter(Q(gtin=barcode) | Q(asin=barcode)).first()
    if not product:
        title_found = get_title_from_barcode_safely(barcode)
        
        if title_found:
            from django.utils.text import slugify
            import uuid
            
            base_slug = slugify(title_found)[:490]
            final_slug = base_slug if not Product.objects.filter(slug=base_slug).exists() else f"{base_slug}-{uuid.uuid4().hex[:5]}"

            product = Product.objects.create(
                title=title_found,
                slug=final_slug,
                gtin=barcode,
                is_active=True
            )
        else:
            return error_response("Could not identify this barcode. Try manual search.", code=404)

    return compare_prices_api(request._request, slug=product.slug)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def decode_barcode_to_slug(request):
    """
    Takes a barcode, finds the product title, creates a temporary product,
    and then calls the compare_prices_api to get all deals.
    """
    # Check subscription permission
    subscription = getattr(request.user, 'subscription', None)
    if not subscription or not subscription.is_active:
        return error_response("Please subscribe to a plan to use barcode scanner.", code=403)

    barcode = request.query_params.get('code', '').strip()
    if not barcode:
        return error_response("Query parameter 'code' is required.", code=400)

    product = Product.objects.filter(Q(gtin=barcode) | Q(asin=barcode)).first()

    if not product:
        title_found = get_title_from_barcode_safely(barcode)
        if not title_found:
            return error_response(f"Could not find a product title for barcode '{barcode}'.", code=404)

        from django.utils.text import slugify
        import uuid
        base_slug = slugify(title_found)[:490]
        final_slug = base_slug if not Product.objects.filter(slug=base_slug).exists() else f"{base_slug}-{uuid.uuid4().hex[:5]}"
        
        product = Product.objects.create(title=title_found, slug=final_slug, gtin=barcode, is_active=True)

    return compare_prices_api(request._request, slug=product.slug)