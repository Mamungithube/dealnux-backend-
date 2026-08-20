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
from dealnux.responses import success_response, error_response
from api_integration.tasks import (
    sync_amazon_task, sync_ebay_task, sync_walmart_task,
    sync_all_platforms_task
)
from .search_sync_views import clean_display_title

logger = logging.getLogger(__name__)

VARIANT_TOKENS = {
    'max', 'plus', 'ultra', 'mini', 'pro', 'lite', 'fe',
    'air', 'fold', 'flip', 'edge', 'note', 'x', 'xl',
}

STORAGE_PATTERN = re.compile(r'(\d+)\s*(gb|tb|mb)', re.IGNORECASE)
RAM_PATTERN = re.compile(r'(\d+)\s*gb\s*ram', re.IGNORECASE)

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




# -------------------------- Multi-Platform Product Price Comparison API View --------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def compare_prices_api(request, slug):
    import time
    from store.models import SellerProduct

    product = None
    sp_target = None

    if str(slug).isdigit():
        pk = int(slug)
        sp_target = SellerProduct.objects.filter(id=pk, status='APPROVED').first()
        if sp_target and sp_target.linked_product:
            product = sp_target.linked_product
        elif not sp_target:
            product = Product.objects.filter(id=pk, is_active=True).first()
    else:
        product = Product.objects.filter(slug=slug, is_active=True).first()
        if not product:
            sp_target = SellerProduct.objects.filter(title__icontains=slug.replace('-', ' '), status='APPROVED').first()
            if sp_target and sp_target.linked_product:
                product = sp_target.linked_product

    if not product and sp_target:
        try:
            sp_target._ensure_linked_records()
            product = sp_target.linked_product
        except Exception:
            pass

    if not product and not sp_target:
        return error_response("Product not found", code=404)

    target_title = product.title if product else (sp_target.title if sp_target else '')
    clean_target_title = clean_display_title(target_title)

    sync_triggered = False

    if product:
        existing_platforms_count = ProductListing.objects.filter(
            product=product,
            is_available=True
        ).values('platform').distinct().count()

        cache_key = f"sync_lock_{product.id}"
        if existing_platforms_count < 3 and not cache.get(cache_key):
            fingerprint = get_product_fingerprint(clean_target_title)
            query_for_api = fingerprint['core_name'] or clean_target_title[:50]

            try:
                priority_tasks = [
                    sync_amazon_task.s(query_for_api, 3),
                    sync_ebay_task.s(query_for_api, 3),
                    sync_walmart_task.s(query_for_api, 3),
                ]
                for i, task in enumerate(priority_tasks):
                    task.apply_async(countdown=i * 60)
            except Exception:
                sync_all_platforms_task.delay(query_for_api, limit=5)

            cache.set(cache_key, True, 86400)
            sync_triggered = True

        candidates = Product.objects.filter(
            category=product.category,
            is_active=True
        ).exclude(id=product.id).only('id', 'title', 'brand') if product.category else Product.objects.none()

        matched_ids = [product.id]
        THRESHOLD = 75

        accessory_words = ['cable', 'case', 'cover', 'charger', 'stand', 'mount', 'station']
        target_is_acc = any(w in clean_target_title.lower() for w in accessory_words)

        for cand in candidates:
            cand_title_lower = cand.title.lower()
            cand_is_acc = any(w in cand_title_lower for w in accessory_words)
            if target_is_acc != cand_is_acc:
                continue
            score = calculate_match_score(product.title, cand.title)
            if score >= THRESHOLD:
                matched_ids.append(cand.id)
    else:
        matched_ids = []

    comparison_list = []
    prices = []
    seen_urls = set()

    # Add Marketplace Seller offers
    if sp_target:
        seller_prods = [sp_target]
    elif product:
        seller_prods = list(SellerProduct.objects.filter(linked_product=product, status='APPROVED'))
    else:
        seller_prods = []

    for sp in seller_prods:
        s_name = sp.seller.shop_name if (sp.seller and sp.seller.shop_name) else "Seller"
        total_p = float(sp.price) + (float(getattr(sp, 'shipping_cost', 0) or 0) if not getattr(sp, 'free_shipping', True) else 0)
        prices.append(total_p)

        img_url = request.build_absolute_uri(sp.main_image.url) if sp.main_image else None

        comparison_list.append({
            'platform': s_name,
            'platform_code': f"local-seller-{sp.seller.id if sp.seller else 0}",
            'product_id': sp.id,
            'listing_id': str(sp.id),
            'price': float(sp.price),
            'total_price': total_p,
            'url': '',
            'seller': s_name,
            'main_image': img_url,
            'shipping_cost': str(getattr(sp, 'shipping_cost', '0.00') or '0.00'),
            'is_available': True,
            'has_coupon': False,
            'coupon_text': '',
            'deal_badge': 'BEST DEAL' if getattr(sp, 'is_featured', False) else '',
            'clean_title': clean_display_title(sp.title),
        })

    # Add 3rd-party ProductListings (Amazon, eBay, Walmart, etc. from DB)
    if matched_ids:
        listings = ProductListing.objects.filter(
            product__id__in=matched_ids,
            is_available=True,
            price__gt=0
        ).select_related('platform', 'product').order_by('price')

        for listing in listings:
            if listing.external_url and listing.external_url in seen_urls:
                continue
            if listing.external_url:
                seen_urls.add(listing.external_url)

            total_p = float(listing.get_total_price())
            prices.append(total_p)

            img_url = listing.product.main_image
            if img_url and not str(img_url).startswith('http'):
                img_url = request.build_absolute_uri(img_url)

            comparison_list.append({
                'platform': listing.platform.name if listing.platform else 'Retailer',
                'platform_code': listing.platform.code if listing.platform else 'external',
                'product_id': listing.product.id,
                'listing_id': listing.external_id or str(listing.id),
                'price': float(listing.price),
                'total_price': total_p,
                'url': listing.external_url,
                'seller': listing.seller_username or "Verified Store",
                'main_image': img_url,
                'shipping_cost': str(listing.shipping_cost),
                'is_available': listing.is_available,
                'has_coupon': listing.has_coupon,
                'coupon_text': listing.coupon_text,
                'deal_badge': listing.deal_badge,
                'clean_title': clean_display_title(listing.product.title),
            })

    comparison_list.sort(key=lambda x: float(x['total_price']))

    prod_id = product.id if product else (sp_target.id if sp_target else 0)
    prod_title = clean_target_title

    prod_img = None
    if product and product.main_image:
        img_val = str(product.main_image.url if hasattr(product.main_image, 'url') else product.main_image).strip()
        if img_val:
            prod_img = img_val if img_val.startswith('http') else request.build_absolute_uri(img_val)

    if not prod_img and sp_target and sp_target.main_image:
        img_val = str(sp_target.main_image.url if hasattr(sp_target.main_image, 'url') else sp_target.main_image).strip()
        if img_val:
            prod_img = img_val if img_val.startswith('http') else request.build_absolute_uri(img_val)

    if not prod_img and comparison_list:
        for deal in comparison_list:
            if deal.get('main_image'):
                prod_img = deal['main_image']
                break

    return success_response({
        'product': {
            'id': prod_id,
            'title': prod_title,
            'slug': product.slug if product else '',
            'brand': product.brand if product else '',
            'main_image': prod_img,
        },
        'meta': {
            'total_deals_found': len(comparison_list),
            'sync_triggered': sync_triggered,
            'message': "Searching for more deals..." if sync_triggered else "Results updated."
        },
        'price_analysis': {
            'lowest_price': min(prices) if prices else 0,
            'highest_price': max(prices) if prices else 0,
            'potential_savings': round(max(prices) - min(prices), 2) if len(prices) > 1 else 0
        },
        'price_comparison': comparison_list,
        'best_deal': comparison_list[0] if comparison_list else None
    }, message="Price comparison fetched successfully")
# -------------------------- Category-Wide Multi-Platform Price Comparison & Deals View --------------------------
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

