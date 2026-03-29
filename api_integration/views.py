import time
import logging
from unicodedata import category
from oauthlib.uri_validate import query
from rest_framework import viewsets
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q, Min, Count
from django.db import transaction
from django.core.cache import cache
import math
from rest_framework import permissions as drf_permissions
from .services.walmart_service import WalmartService
from .services.amazon_service import AmazonService
from .services.sephora_service import SephoraService
from .services.ebay_service import EbayRapidService
from .services.target_service import TargetService
from .services.wayfair_service import WayfairService
from .services.aliexpress_service import AliExpressService
from .services.bestbuy_service import BestBuyService
from .tasks import sync_all_platforms_task, sync_ebay_task
from .db_helpers import save_generic_product_to_db
from django.db.models import Q, Min, FloatField, Value
from difflib import SequenceMatcher
import re
from .models import (
    Product, ProductListing, Platform, Category,
    CartItem, SavingsActivity, Favorite
)
from .serializers import (
    ProductSerializer, ProductDetailSerializer,
    ProductListingSerializer, PlatformSerializer,
    CategorySerializer, PriceHistorySerializer,
    CartItemSerializer, FavoriteSerializer, CategoryTreeSerializer, CategoryChildSerializer
)
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger(__name__)


def clean_display_title(title):
    title = re.sub(r'\d+%?\s*opens?\s+in\s+a\s+new\s+(window|tab)(\s+or\s+(tab|window))?', '', title, flags=re.IGNORECASE)
    title = re.sub(r'opens?\s+in\s+a\s+new\s+(window|tab)(\s+or\s+(tab|window))?', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+', ' ', title).strip(' -')
    return title


def normalize_title(title):
    """Title normalize করবে comparison এর জন্য"""
    title = title.lower().strip()
    # special characters সরাবে
    title = re.sub(r'[^\w\s]', '', title)
    # extra spaces সরাবে
    title = re.sub(r'\s+', ' ', title)
    return title


def similarity_score(title1, title2):
    """দুইটা title এর মধ্যে similarity score বের করবে (0-100)"""
    t1 = normalize_title(title1)
    t2 = normalize_title(title2)
    score = SequenceMatcher(None, t1, t2).ratio() * 100
    return round(score, 2)


def extract_keywords(title):
    """Title থেকে important keywords বের করবে"""
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

    # ১. SellerProduct id দিয়ে খোঁজা (local seller)
    try:
        from store.models import SellerProduct
        seller_product = SellerProduct.objects.get(id=pk, status='APPROVED')
        product = seller_product.linked_product
    except SellerProduct.DoesNotExist:
        pass

    # ২. সরাসরি Product id দিয়ে খোঁজা (3rd party)
    if not product:
        product = Product.objects.filter(id=pk, is_active=True).first()

    if not product:
        return error_response("Product not found", code=404)

    serializer = ProductDetailSerializer(product)
    return success_response(serializer.data, message="Product fetched")
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

    queryset = Product.objects.filter(is_active=True).prefetch_related(
        'listings', 'images', 'specifications', 'category'
    )
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

        import re
        from difflib import SequenceMatcher
        from django.db.models import Q

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

        # AND কাজ না করলে প্রথম ৫ word দিয়ে OR
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

    def get_queryset(self):
        queryset = super().get_queryset()

        # Query params নেওয়া হচ্ছে
        category = self.request.query_params.get('category', '').strip()
        search = self.request.query_params.get('search', '').strip()
        sort = self.request.query_params.get('sort', 'newest').strip()

        # =========================
        # Category Filter
        # =========================
        if category:
            try:
                # category slug দিয়ে category বের করবে
                cat = Category.objects.get(slug=category)

                # child category থাকলে সেগুলাও নিবে
                child_ids = list(cat.children.values_list('id', flat=True))

                # parent + child category ids
                all_ids = [cat.id] + child_ids

                queryset = queryset.filter(category__id__in=all_ids)

            except Category.DoesNotExist:
                return queryset.none()

        # =========================
        # Search Filter
        # =========================
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(brand__icontains=search)
            )

        # =========================
        # Sorting
        # =========================
        if sort == 'price_low':
            queryset = queryset.annotate(
                sort_price=Min('listings__price')
            ).order_by('sort_price')

        elif sort == 'price_high':
            queryset = queryset.annotate(
                sort_price=Min('listings__price')
            ).order_by('-sort_price')

        elif sort == 'popular':
            queryset = queryset.annotate(
                total_listing=Count('listings')
            ).order_by('-total_listing')

        elif sort == 'oldest':
            queryset = queryset.order_by('created_at')

        else:
            # newest default
            queryset = queryset.order_by('-created_at')

        return queryset.distinct()

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated = self.get_paginated_response(serializer.data)

            total_count = paginated.data['count']
            page_size = self.paginator.get_page_size(request)
            current_page = self.paginator.page.number
            total_pages = math.ceil(total_count / page_size)

            return success_response({
                'count':   total_count,
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
                'results': serializer.data,
            })

        serializer = self.get_serializer(queryset, many=True)
        return success_response({'results': serializer.data})

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.request.user.is_authenticated:
            context['favorite_ids'] = set(
                Favorite.objects.filter(user=self.request.user)
                .values_list('product_id', flat=True)
            )
        else:
            context['favorite_ids'] = set()
        return context
    

from rapidfuzz import fuzz

VARIANT_TOKENS = {
    'max', 'plus', 'ultra', 'mini', 'pro', 'lite', 'fe',
    'air', 'fold', 'flip', 'edge', 'note',
}

def extract_core_title(title):
    noise_patterns = [
        r'\(.*?\)',
        r'\[.*?\]',
        r'\b(at&t|t[\-]?mobile|verizon|sprint|tmobile|att)\b',
        r'\b(unlocked|locked|factory|carrier)\b',
        r'\b(great|good|fair|excellent|mint|poor)\s*(condition)?\b',
        r'\b(refurbished|restored|renewed|remanufactured)\b',
        r'\b(free\s*shipping|ships\s*fast|seller\s*refurbished)\b',
        r'opens?\s+in\s+a\s+new\s+(window|tab).*',
        r'\d+%?\s*opens?.*',
        r'\b(black|white|silver|gold|blue|red|green|pink|purple|titanium|midnight|starlight|natural|cosmic|desert)\b',
        r'\b\d+\s*gb\b',
        r'\b\d+\s*tb\b',
        r'\bsmartphone\b',
        r'\bvery\b',
        r'-\s*$',
    ]
    core = title
    for pattern in noise_patterns:
        core = re.sub(pattern, '', core, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', core).strip(' -,|/')


def variant_check(core1, core2):
    tokens1 = set(core1.lower().split())
    tokens2 = set(core2.lower().split())
    variants1 = tokens1 & VARIANT_TOKENS
    variants2 = tokens2 & VARIANT_TOKENS
    extra   = variants2 - variants1
    missing = variants1 - variants2
    return len(extra) == 0 and len(missing) == 0


def number_check(core1, core2):
    nums1 = set(re.findall(r'\b\d+\b', core1))
    nums2 = set(re.findall(r'\b\d+\b', core2))
    if not nums1 and not nums2:
        return True
    if not nums1 or not nums2:
        return True
    return len(nums1 - nums2) == 0


def product_match_score(title1, title2):
    core1 = extract_core_title(title1)
    core2 = extract_core_title(title2)

    # Hard block — variant বা number mismatch
    if not variant_check(core1, core2):
        return 0.0
    if not number_check(core1, core2):
        return 0.0

    tokens1 = set(core1.lower().split())
    tokens2 = set(core2.lower().split())

    jaccard = 0.0
    if tokens1 or tokens2:
        jaccard = len(tokens1 & tokens2) / len(tokens1 | tokens2) * 100

    token_sort = fuzz.token_sort_ratio(core1, core2)
    return round((jaccard * 0.75) + (token_sort * 0.25), 1)


@api_view(['GET'])
@permission_classes([AllowAny])
def compare_prices_api(request, slug):
    product = Product.objects.filter(slug=slug, is_active=True).first()
    if not product:
        return error_response("Product not found", code=404)

    target_title = clean_display_title(product.title)
    target_core  = extract_core_title(target_title)
    THRESHOLD    = 75

    # Step 1: DB candidate filter
    # core title এর words দিয়ে OR filter — broad net
    core_words = [w for w in target_core.lower().split() if len(w) > 2]

    q = Q(is_active=True)
    for word in core_words:
        q |= Q(title__icontains=word)

    candidates = Product.objects.filter(q).exclude(id=product.id)

    # Step 2: score করো
    matched_ids = [product.id]

    for cand in candidates:
        cand_title = clean_display_title(cand.title)
        score = product_match_score(target_title, cand_title)
        if score >= THRESHOLD:
            matched_ids.append(cand.id)

    # Step 3: listings নাও
    listings = ProductListing.objects.filter(
        product__id__in=matched_ids,
        is_available=True,
        price__gt=0,
    ).select_related('platform', 'product')

    seen_platforms = {}

    for listing in listings:
        listing_title = clean_display_title(listing.product.title)
        score         = product_match_score(target_title, listing_title)
        platform_code = listing.platform.code
        total_price   = float(listing.get_total_price())

        entry = {
            'platform':         listing.platform.name,
            'platform_code':    platform_code,
            'matched_title':    listing_title,
            'similarity_score': score,
            'price':            float(listing.price),
            'currency':         listing.currency,
            'shipping_cost':    float(listing.shipping_cost),
            'free_shipping':    listing.free_shipping,
            'total_price':      total_price,
            'condition':        listing.condition,
            'seller':           listing.seller_username,
            'seller_rating':    float(listing.seller_rating) if listing.seller_rating else None,
            'url':              listing.external_url,
            'last_updated':     listing.last_checked,
        }

        if platform_code not in seen_platforms:
            seen_platforms[platform_code] = entry
        elif total_price < seen_platforms[platform_code]['total_price']:
            seen_platforms[platform_code] = entry

    price_comparison = sorted(seen_platforms.values(), key=lambda x: x['total_price'])

    return success_response({
        'product': {
            'id':         product.id,
            'title':      target_title,
            'slug':       product.slug,
            'brand':      product.brand,
            'main_image': product.main_image,
        },
        'meta': {
            'total_platforms':  len(price_comparison),
            'matched_products': len(matched_ids),
        },
        'price_comparison': price_comparison,
        'best_deal':        price_comparison[0] if price_comparison else None,
    }, message="Price comparison fetched")

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
        # শুধু parent categories (parent=None)
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
    limit = min(int(request.GET.get('limit', 10)), 50)
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
    limit = min(int(request.GET.get('limit', 10)), 50)
    page = int(request.GET.get('page', 1))
    page_size = min(int(request.GET.get('page_size', 10)), 50)

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
        # cache এর results এ is_favorite inject করুন
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
        title_q |= Q(title__icontains=term)

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
    """Result list থেকে নির্দিষ্ট page এর items return করে।"""
    page = max(1, page)
    start = (page - 1) * page_size
    end = start + page_size
    return results[start:end]


def get_pagination_meta(results: list, page: int, page_size: int) -> dict:
    """Pagination metadata তৈরি করে।"""
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

    # ── এই দুটো method যোগ করুন ──
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

        # ১. SellerProduct id দিয়ে linked_product খোঁজা
        try:
            from store.models import SellerProduct  # আপনার app name অনুযায়ী বদলান
            seller_product = SellerProduct.objects.get(
                id=product_id, status='APPROVED')
            product = seller_product.linked_product
        except SellerProduct.DoesNotExist:
            pass

        # ২. সরাসরি Product id দিয়েও খোঁজা (fallback)
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
        return self._success(serializer.data, message="Cart items fetched")

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
        if not cart_items.exists():
            raise ValidationError({"cart": "Your cart is empty."})

        original_total = 0
        optimized_total = 0
        single_store_total = 0
        optimized_split = {}
        single_store_items = []

        for item in cart_items:
            product = item.product
            qty = item.quantity

            # selected_listing এর বদলে সবচেয়ে সস্তা listing কে current price ধরছি
            cheapest_current = ProductListing.objects.filter(
                product=product, is_available=True
            ).order_by('price').first()

            if not cheapest_current:
                continue

            current_price = cheapest_current.price * qty
            original_total += current_price

            opt_price = cheapest_current.price * qty
            optimized_total += opt_price
            platform_name = cheapest_current.platform.name
            optimized_split.setdefault(
                platform_name, {'total': 0, 'items': []})
            optimized_split[platform_name]['total'] += float(opt_price)
            optimized_split[platform_name]['items'].append({
                'product':     product.title,
                'unit_price':  float(cheapest_current.price),
                'quantity':    qty,
                'total_price': float(opt_price),
                'url':         cheapest_current.external_url,
            })

            ebay_listing = ProductListing.objects.filter(
                product=product, platform__code='ebay', is_available=True
            ).first()
            if ebay_listing:
                single_price = ebay_listing.price * qty
                single_store_total += single_price
                single_store_items.append({
                    'product':     product.title,
                    'unit_price':  float(ebay_listing.price),
                    'quantity':    qty,
                    'total_price': float(single_price),
                })
            else:
                single_store_total += current_price

        split_savings = float(original_total - optimized_total)
        data = {
            "cart_total_original": float(original_total),
            "options": {
                "single_store": {
                    "platform":   "eBay",
                    "total_cost": float(single_store_total),
                    "shipments":  1,
                    "items":      single_store_items,
                },
                "optimized_split": {
                    "total_cost":  float(optimized_total),
                    "total_saved": split_savings if split_savings > 0 else 0,
                    "shipments":   len(optimized_split),
                    "platforms":   optimized_split,
                },
            },
            "savings_summary": {
                "original_total":      float(original_total),
                "price_match_savings": float(original_total - optimized_total) if original_total > optimized_total else 0,
                "final_price":         float(optimized_total),
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
            user=user).order_by('-created_at')[:5]
        data = {
            "total_lifetime_savings": float(getattr(user, 'total_lifetime_savings', 0.0)),
            "recent_activity": [
                {"title": a.title, "saved_amount": float(
                    a.saved_amount), "date": a.time_ago}
                for a in recent
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
        page_size = min(100, max(1, int(request.GET.get('page_size', 20))))
    except (ValueError, TypeError):
        page, page_size = 1, 20

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

    # ── এই দুটো method যোগ করুন ──
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

        # ১. SellerProduct id দিয়ে খোঁজা
        try:
            from store.models import SellerProduct
            seller_product = SellerProduct.objects.get(
                id=product_id, status='APPROVED')
            product = seller_product.linked_product
        except SellerProduct.DoesNotExist:
            pass

        # ২. সরাসরি Product id দিয়ে খোঁজা (fallback)
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

        # ১. SellerProduct id দিয়ে খোঁজা
        try:
            from store.models import SellerProduct
            seller_product = SellerProduct.objects.get(
                id=product_id, status='APPROVED')
            product = seller_product.linked_product
        except SellerProduct.DoesNotExist:
            pass

        # ২. সরাসরি Product id দিয়ে খোঁজা (fallback)
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
