"""
Product Query and Detail Services.
Contains business logic for product filtering, relevance scoring, detail resolution, and savings tracking.
"""

import re
import math
from django.db import transaction
from django.db.models import Q, F, Min, Max, Count, Avg, Value, Case, When, FloatField
from difflib import SequenceMatcher

from api_integration.models import (
    Product, ProductListing, Category,
    CartItem, SavingsActivity, Favorite
)
from api_integration.serializers import (
    ProductSerializer, ProductDetailSerializer
)


ACCESSORY_KEYWORDS = [
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

ACCESSORY_PATTERN = '|'.join(re.escape(w) for w in ACCESSORY_KEYWORDS)

PHONE_BRANDS = [
    'apple', 'iphone', 'samsung', 'motorola', 'moto',
    'google', 'pixel', 'oneplus', 'xiaomi', 'nokia', 'sony', 'lg'
]

PHONE_SPECS = [
    r'\d+GB', r'unlocked', r'smartphone',
    r'cell phone', r'dual sim', r'android', r'ios'
]


def filter_and_score_products(queryset, query_params):
    """
    Applies smart filtering, search relevance scoring, sorting, and price ranges to Product queryset.
    """
    search_query = query_params.get('search', '').strip()
    sort = query_params.get('sort', '').strip()

    # 1. Smart Sort Detection
    is_low = sort in ['price_low', 'lowest_price', 'Lowest Price'] or 'price_low' in query_params
    is_high = sort in ['price_high', 'highest_price', 'Highest Price'] or 'price_high' in query_params
    is_newest = sort in ['newest', 'Newest'] or 'newest' in query_params
    is_best = sort in ['best_deal', 'Best Deal'] or 'best_deal' in query_params

    min_price = query_params.get('min_price', '').strip()
    max_price = query_params.get('max_price', '').strip()

    # 2. Base Quality Filter
    queryset = queryset.filter(
        title__isnull=False,
        main_image__isnull=False,
        listings__price__gt=0,
        listings__is_available=True,
    ).exclude(title='', main_image='')

    # 3. Category & Accessory Logic
    category_input = query_params.getlist('category')
    explicit_category_ids = set()

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
                queryset = queryset.filter(~Q(title__iregex=rf"(?i)({ACCESSORY_PATTERN})"))
            else:
                return queryset.none()

    # 4. Search and Relevance Scoring
    if search_query:
        search_terms = [t for t in re.split(r'\s+', search_query.lower()) if len(t) > 1]
        if not search_terms:
            return queryset.none()

        sq = re.escape(search_query)
        normalized_query = search_query.lower().strip()
        is_searching_accessory = any(word in normalized_query for word in ACCESSORY_KEYWORDS)

        # Strict AND filter
        strict_q = Q()
        for term in search_terms:
            strict_q &= Q(title__icontains=term)
        queryset = queryset.filter(strict_q)

        if not is_searching_accessory:
            queryset = queryset.filter(~Q(title__iregex=rf"(?i)({ACCESSORY_PATTERN})"))

        # Category boost triggers
        phone_trigger = any(w in normalized_query for w in ['phone', 'mobile', 'cell', 'smartphone'])
        laptop_trigger = any(w in normalized_query for w in ['laptop', 'notebook', 'macbook', 'chromebook'])

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
                    Q(title__iregex=rf"(?i)({'|'.join(PHONE_SPECS)})"),
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
                When(Q(title__iregex=rf"^({'|'.join(PHONE_BRANDS)})"), then=Value(80.0)),
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


def get_product_detail_payload(pk, request):
    """
    Resolves unified product & seller listing detail, handling standalone seller products,
    retailer click tracking, review statistics, and related recommendations.
    """
    product = None
    seller_product_data = None
    standalone_seller_product = None

    try:
        from store.models import SellerProduct, ProductReview

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

    # Standalone SellerProduct
    if standalone_seller_product:
        sp = standalone_seller_product
        from store.models import ProductReview

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
        return {'error': False, 'data': data, 'message': "Product details fetched successfully"}

    if not product:
        product = Product.objects.filter(id=pk, is_active=True).first()

    if not product:
        return {'error': True, 'message': "Product not found", 'code': 404}

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
            return {'error': True, 'message': "Login required to view retailer details.", 'code': 401}

        from payment.utils import validate_and_increment_click
        success, message = validate_and_increment_click(
            request.user, product_id=product.id)
        if not success:
            return {'error': True, 'message': message, 'code': 403 if "subscribe" in message.lower() else 429}

    if seller_product_data:
        data.update(seller_product_data)

    data['related_products'] = ProductSerializer(
        related_products, many=True, context=context).data

    return {'error': False, 'data': data, 'message': "Product details fetched successfully"}


def record_deal_savings(best_deal_product, user):
    """
    Calculates market savings by comparing the best deal listing with market highest price
    and updates user lifetime savings.
    """
    this_deal_listing = best_deal_product.listings.filter(
        is_available=True, price__gt=0).order_by('price').first()
    if not this_deal_listing:
        return {'error': True, 'message': "No valid price found for this deal.", 'code': 404}

    this_price = float(this_deal_listing.get_total_price())

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
            current_total = float(getattr(user, 'total_lifetime_savings', 0.0))
            user.total_lifetime_savings = current_total + savings
            user.save()

            SavingsActivity.objects.create(
                user=user,
                title=f"Saved by choosing best deal: {best_deal_product.title}",
                saved_amount=savings
            )

        return {
            'error': False,
            'data': {
                "product": best_deal_product.title,
                "you_paid": this_price,
                "market_high": highest_market_price,
                "saved_amount": savings,
                "total_lifetime_savings": float(user.total_lifetime_savings)
            },
            'message': "Savings recorded successfully based on best deal comparison!"
        }

    return {
        'error': False,
        'data': {
            "saved_amount": 0,
            "message": "This is already the highest price or no comparison available."
        },
        'message': "No savings applicable."
    }
