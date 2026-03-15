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
from api_integration.services.sephora_service import SephoraService
from .services.ebay_service import EbayRapidService 
from api_integration.services.target_service import TargetService
from api_integration.services.wayfair_service import WayfairService
from api_integration.services.aliexpress_service import AliExpressService
from api_integration.services.bestbuy_service import BestBuyService
from .tasks import sync_all_platforms_task, sync_ebay_task, sync_clickbank_task
from django.core.cache import cache
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
from .services.ebay_service import EbayRapidService as EbayService
from .services.clickbank_service import ClickBankService
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.utils.text import slugify

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
#       Category Cache — To stop repeated DB calls inside a loop
# ============================================================================

_CATEGORY_CACHE = None 

def _get_category_cache():
    """
        All Categories are loaded into memory once.
        Each sync request will only make 1 DB call.
        Refreshes old cache if it is older than 5 minutes.
    """
    global _CATEGORY_CACHE
    now = time.time()

    if _CATEGORY_CACHE is None or (now - _CATEGORY_CACHE['loaded_at']) > 300:
        qs = Category.objects.all().only('id', 'name', 'slug')
        _CATEGORY_CACHE = {
            'by_slug': {cat.slug: cat for cat in qs},
            'by_name_lower': {cat.name.lower(): cat for cat in qs},
            'all': list(qs),
            'loaded_at': now,
        }
        logger.debug(f"Category cache refreshed: {len(_CATEGORY_CACHE['all'])} categories loaded")

    return _CATEGORY_CACHE


# ── Keyword → Category slug map ─────────────────────────────────────────────
# If these keywords are present in the product title, the corresponding category slug will be found.
# The slugs must match the slugify(name) of your Category seeder script.

_KEYWORD_CATEGORY_MAP = [
    # Electronics
    (['smartphone', 'iphone', 'android phone', 'mobile phone'], 'smartphones'),
    (['laptop', 'notebook', 'macbook', 'chromebook'], 'laptops'),
    (['desktop', 'pc tower', 'all-in-one computer'], 'desktop-computers'),
    (['tablet', 'ipad', 'kindle fire'], 'tablets'),
    (['headphone', 'headset', 'earphone', 'earbud', 'airpod', 'earbuds', 'in-ear'], 'audio-headphones'),
    (['camera', 'dslr', 'mirrorless', 'webcam', 'camcorder'], 'cameras-photo'),
    (['smartwatch', 'fitness tracker', 'apple watch', 'galaxy watch'], 'smartwatches'),
    (['tv ', 'television', '4k tv', 'oled', 'qled', 'monitor', 'projector'], 'tv-home-theater'),
    (['video game', 'gaming console', 'playstation', 'xbox', 'nintendo', 'ps5', 'ps4'], 'video-games-consoles'),
    (['keyboard', 'mouse', 'usb hub', 'hard drive', 'ssd', 'ram', 'computer accessory'], 'computer-accessories'),
    (['printer', 'ink cartridge', 'toner', 'scanner'], 'printers-ink'),
    (['drone', 'quadcopter', 'rc car', 'remote control'], 'drones-rc'),
    (['smart home', 'alexa', 'google home', 'smart plug', 'smart bulb', 'ring doorbell'], 'smart-home-devices'),
    (['phone case', 'mobile case', 'tpu case', 'screen protector', 'tempered glass', 'lcd display', 'digitizer'], 'computer-accessories'),

    # Fashion — Men
    (['men\'s shirt', 'men\'s jacket', 'men\'s pants', 'men\'s suit', 'men\'s clothing'], 'mens-clothing'),
    (['men\'s shoe', 'men\'s sneaker', 'men\'s boot'], 'mens-shoes'),
    (['men\'s watch'], 'mens-watches'),
    (['men\'s belt', 'men\'s wallet', 'men\'s tie'], 'mens-accessories-belts'),
    (['men\'s sunglasses'], 'mens-sunglasses'),

    # Fashion — Women
    (['women\'s dress', 'women\'s blouse', 'women\'s skirt', 'women\'s clothing'], 'womens-clothing'),
    (['women\'s shoe', 'women\'s heel', 'women\'s boot', 'women\'s sneaker'], 'womens-shoes'),
    (['handbag', 'purse', 'tote bag', 'clutch bag', 'women\'s wallet'], 'handbags-wallets'),
    (['women\'s watch', 'ladies watch'], 'womens-watches'),
    (['necklace', 'ring', 'bracelet', 'earring', 'fine jewelry', 'diamond'], 'fine-jewelry'),
    (['makeup', 'lipstick', 'foundation', 'mascara', 'eyeshadow', 'blush', 'concealer'], 'beauty-makeup'),
    (['lingerie', 'bra', 'panty', 'sleepwear', 'pajama'], 'lingerie-sleepwear'),

    # Home
    (['sofa', 'chair', 'table', 'desk', 'bed frame', 'bookshelf', 'furniture'], 'furniture'),
    (['home decor', 'wall art', 'picture frame', 'candle', 'vase', 'rug', 'curtain'], 'home-decor'),
    (['cookware', 'kitchen', 'blender', 'air fryer', 'instant pot', 'knife set', 'dining'], 'kitchen-dining'),
    (['bedding', 'pillow', 'mattress', 'comforter', 'sheet set', 'towel', 'bath'], 'bedding-bath'),
    (['garden', 'outdoor', 'patio', 'lawn mower', 'plant pot', 'hose'], 'garden-outdoor'),
    (['tool', 'drill', 'saw', 'wrench', 'screwdriver', 'home improvement', 'power tool'], 'tools-home-improvement'),
    (['ceiling fan', 'light fixture', 'lamp', 'led bulb', 'chandelier'], 'lighting-ceiling-fans'),
    (['pet food', 'dog', 'cat', 'pet toy', 'pet bed', 'aquarium', 'bird cage'], 'pet-supplies'),

    # Health & Beauty
    (['moisturizer', 'serum', 'sunscreen', 'face wash', 'skincare', 'toner', 'retinol'], 'skincare'),
    (['shampoo', 'conditioner', 'hair dryer', 'hair straightener', 'hair care'], 'hair-care'),
    (['perfume', 'cologne', 'fragrance', 'eau de toilette'], 'fragrances-perfumes'),
    (['vitamin', 'supplement', 'protein powder', 'fish oil', 'probiotic', 'omega'], 'vitamins-dietary-supplements'),
    (['toothbrush', 'toothpaste', 'mouthwash', 'dental floss', 'oral care'], 'oral-care'),
    (['blood pressure', 'thermometer', 'glucose monitor', 'medical', 'first aid', 'mask'], 'medical-supplies-equipment'),
    (['razor', 'deodorant', 'body wash', 'hand sanitizer', 'personal care'], 'personal-care-hygiene'),

    # Sports
    (['treadmill', 'dumbbell', 'barbell', 'yoga mat', 'resistance band', 'gym', 'fitness'], 'exercise-fitness-equipment'),
    (['bicycle', 'cycling', 'bike helmet', 'cycling jersey'], 'cycling-bicycles'),
    (['tent', 'sleeping bag', 'backpack', 'hiking', 'camping'], 'camping-hiking'),
    (['fishing rod', 'fishing reel', 'fishing lure', 'tackle box'], 'fishing-equipment'),
    (['swim', 'kayak', 'surfboard', 'water sport'], 'water-sports'),
    (['football', 'basketball', 'soccer', 'baseball', 'volleyball', 'team sport'], 'team-sports'),
    (['golf club', 'golf ball', 'golf bag', 'golf equipment'], 'golf-equipment'),

    # Kids & Baby
    (['baby', 'infant', 'newborn', 'diaper', 'baby monitor', 'baby food'], 'baby-products-accessories'),
    (['toy', 'lego', 'barbie', 'action figure', 'stuffed animal', 'nerf'], 'toys-games'),
    (['kids clothing', 'boys shirt', 'girls dress', 'children\'s apparel'], 'kids-clothing'),
    (['board game', 'puzzle', 'card game', 'chess', 'jigsaw'], 'puzzles-board-games'),
    (['stroller', 'car seat', 'baby carrier', 'high chair', 'baby gear'], 'baby-gear-strollers'),

    # Automotive
    (['car charger', 'dash cam', 'car stereo', 'gps navigation', 'car electronics'], 'car-electronics-gps'),
    (['car cover', 'seat cover', 'floor mat', 'steering wheel cover', 'car interior'], 'car-interior-accessories'),
    (['car wax', 'car wash', 'car exterior', 'window tint'], 'car-exterior-accessories'),
    (['motorcycle', 'helmet', 'riding gear', 'motorbike'], 'motorcycle-parts-accessories'),
    (['car jack', 'battery jumper', 'automotive tool', 'tire inflator'], 'automotive-tools-equipment'),

    # Books & Media
    (['novel', 'fiction book', 'thriller book', 'mystery book'], 'fiction-books'),
    (['textbook', 'non-fiction', 'educational book', 'self help book'], 'non-fiction-educational-books'),
    (['dvd', 'blu-ray', 'movie', 'tv show box set'], 'movies-tv-shows'),
    (['vinyl record', 'cd album', 'music cd'], 'music-vinyl-records'),
    (['guitar', 'piano', 'keyboard instrument', 'drum', 'violin', 'musical instrument'], 'musical-instruments'),

    # Food & Household
    (['snack', 'chips', 'candy', 'cookie', 'popcorn', 'nuts', 'jerky'], 'snack-foods'),
    (['coffee', 'tea', 'energy drink', 'protein shake', 'beverage'], 'beverages-coffee'),
    (['cleaning', 'detergent', 'dish soap', 'paper towel', 'trash bag', 'household'], 'household-cleaning-supplies'),

    # Digital / ClickBank
    (['digital marketing', 'affiliate', 'clickbank', 'make money online', 'e-marketing'], 'e-business-e-marketing'),
    (['self-help', 'personal development', 'mindset', 'motivation', 'productivity'], 'self-help-personal-development'),
    (['software', 'antivirus', 'vpn', 'app subscription', 'saas'], 'software-services'),
    (['online course', 'e-learning', 'udemy', 'masterclass', 'certification'], 'online-courses'),
    (['weight loss', 'diet plan', 'keto', 'fat burner', 'slimming'], 'vitamins-dietary-supplements'),
]

def _resolve_category(category_path, title, cache):
    """
        Matches the best category from category_path and title.
        Doesn't make any DB calls — just uses an in-memory dictionary.

        Priority order:
        1. category_path → slug exact match
        2. category_path → name exact match
        3. category_path → partial match
        4. title → keyword map (most reliable for Amazon/Walmart/Shopify)
        5. title → category name partial match (fallback)
    """
    title_lower = (title or '').lower()

    if category_path:
        clean_name = category_path.split('>')[0].strip()
        slug_key = slugify(clean_name)
        lower_key = clean_name.lower()

        if slug_key in cache['by_slug']:
            return cache['by_slug'][slug_key]

        if lower_key in cache['by_name_lower']:
            return cache['by_name_lower'][lower_key]

        for cat_name_lower, cat_obj in cache['by_name_lower'].items():
            if cat_name_lower in lower_key or lower_key in cat_name_lower:
                return cat_obj

    if title_lower:
        for keywords, target_slug in _KEYWORD_CATEGORY_MAP:
            for kw in keywords:
                if kw in title_lower:
                    cat = cache['by_slug'].get(target_slug)
                    if cat:
                        return cat
                    for cat_name_lower, cat_obj in cache['by_name_lower'].items():
                        if target_slug.replace('-', ' ') in cat_name_lower:
                            return cat_obj

    if title_lower:
        for cat_name_lower, cat_obj in cache['by_name_lower'].items():
            if len(cat_name_lower) >= 5 and cat_name_lower in title_lower:
                return cat_obj

    return None

def _find_matching_product(title, brand, gtin, asin):
    """
    Search for existing products by GTIN → ASIN → Brand+Title similarity.
        Auto-merges variations of the same product.
    """

    if gtin:
        product = Product.objects.filter(gtin=gtin).first()
        if product:
            return product

    if asin:
        product = Product.objects.filter(asin=asin).first()
        if product:
            return product

    if brand and title:
        brand_lower = brand.lower().strip()
        title_lower = title.lower().strip()

        brand_products = Product.objects.filter(
            Q(brand__iexact=brand_lower) |
            Q(brand__icontains=brand_lower.split()[0]) |
            Q(title__icontains=brand_lower.split()[0])  
        ).only('id', 'title', 'brand', 'gtin', 'asin')

        noise_words = {
                    'for', 'the', 'a', 'an', 'and', 'or', 'with', 'by', 'in',
                    'of', 'to', 'dry', 'damaged', 'color', 'treated', 'hair',
                    'fine', 'thick', 'medium', 'mini', 'large', 'small',
                    'lightweight', 'nourishing', 'moisturizing', 'hydrating',
                    'strengthening', 'repairing', 'protective', 'sulfate',
                    'free', 'vegan', 'certified', 'formula', 'set', '-',
                    'unlocked', 'locked', 'us', 'version', 'esim', 'sim',
                    'renewed', 'refurbished', 'restored', 'pre', 'owned',
                    'prepaid', 'wireless', 'smartphone', 'phone', '5g', '4g',
                    'tmobile', 'verizon', 'att', 'sprint', 'straight', 'talk',
                    'total', 'tracfone', 'boost', 'cricket', 'metro',
                    'black', 'white', 'blue', 'pink', 'green', 'yellow',
                    'red', 'purple', 'silver', 'gold', 'titanium', 'lavender',
                    'midnight', 'starlight', 'mist', 'cosmic', 'desert',
                    'premium', 'excellent', 'good', 'fair', 'condition',
                }

        def get_keywords(t):
            words = t.lower().replace('-', ' ').replace('&', '').replace('amp', '').split()
            return {w for w in words if len(w) > 2 and w not in noise_words}

        title_keywords = get_keywords(title_lower)

        best_match  = None
        best_score  = 0

        for existing in brand_products:
            existing_keywords = get_keywords(existing.title.lower())

            if not existing_keywords or not title_keywords:
                continue

            # Jaccard similarity
            intersection = len(title_keywords & existing_keywords)
            union        = len(title_keywords | existing_keywords)
            score        = intersection / union if union > 0 else 0

            if score > 0.35 and score > best_score:
                best_score  = score
                best_match  = existing

        if best_match:
            logger.debug(
                f"Auto-merged: '{title[:40]}' → '{best_match.title[:40]}' "
                f"(score={best_score:.2f}, brand={brand})"
            )
            return best_match

    slug = slugify(title)[:500]
    return Product.objects.filter(slug=slug).first()

def save_generic_product_to_db(product_data, platform, query=None, category_slug=None, all_categories=None):
    """
    Advanced Search Save Helper — Amazon, Walmart, Sephora, HomeDepot.
        Automatically merges by matching brand + title.
    """
    external_id = product_data.get('external_id')
    if not external_id:
        return None, None, False

    title = product_data.get('title', 'Unknown Product')
    brand = (product_data.get('brand') or '').strip()
    gtin  = (product_data.get('gtin') or '').strip() or None
    asin  = (product_data.get('asin') or '').strip() or None

    if not brand and title != 'Unknown Product':
        brand = ' '.join(title.split()[:2])

    # ── Category ──────────────────────────────────────────────────────────
    category = None
    if all_categories is None:
        all_categories = list(Category.objects.all())

    if category_slug:
        category = next((c for c in all_categories if c.slug == category_slug), None)
    else:
        category = _resolve_category(
            product_data.get('category_path'), title, _get_category_cache()
        )
    product = _find_matching_product(title, brand, gtin, asin)

    if product:
        created        = False
        updated_fields = []

        if gtin and not product.gtin:
            product.gtin = gtin
            updated_fields.append('gtin')
        if asin and not product.asin:
            product.asin = asin
            updated_fields.append('asin')
        if brand and not product.brand:
            product.brand = brand
            updated_fields.append('brand')
        if not product.category and category:
            product.category = category
            updated_fields.append('category')

        if updated_fields:
            product.save(update_fields=updated_fields)

    else:
        created   = True
        base_slug = slugify(title)[:490]
        slug = (
            f"{base_slug}-{str(external_id)[:8]}"
            if Product.objects.filter(slug=base_slug).exists()
            else base_slug
        )
        product = Product.objects.create(
            title        = title,
            slug         = slug,
            brand        = brand,
            model_number = product_data.get('model_number') or external_id,
            main_image   = product_data.get('main_image', ''),
            category     = category,
            gtin         = gtin,
            asin         = asin,
        )

    # ── Listing ───────────────────────────────────────────────────────────
    shipping = product_data.get('shipping_info', {})
    listing, listing_created = ProductListing.objects.update_or_create(
        platform=platform,
        external_id=external_id,
        defaults={
            'product':          product,
            'external_url':     product_data.get('external_url', ''),
            'price':            product_data.get('price', 0),
            'currency':         product_data.get('currency', 'USD'),
            'original_price':   product_data.get('original_price'),
            'discount_percentage': product_data.get('discount_percentage'),
            'condition':        product_data.get('condition', 'NEW'),
            'quantity':         int(product_data.get('quantity') or 1),
            'seller_username':  product_data.get('seller_username', 'Merchant'),
            'seller_rating':    product_data.get('seller_rating'),
            'seller_feedback_count': product_data.get('seller_feedback_count', 0),
            'item_location':    product_data.get('item_location', ''),
            'ships_from_country': product_data.get('ships_from_country', ''),
            'shipping_cost':    shipping.get('cost', 0),
            'shipping_currency': shipping.get('currency', 'USD'),
            'free_shipping':    bool(shipping.get('free_shipping', False)),
            'estimated_delivery_days': shipping.get('estimated_days'),
            'returns_accepted': product_data.get('returns_accepted', False),
            'return_period_days': product_data.get('return_period_days'),
            'is_available':     bool(product_data.get('is_available', True)),
        }
    )

    # ── Price History ─────────────────────────────────────────────────────
    if listing_created:
        PriceHistory.objects.create(
            listing=listing, price=listing.price, currency=listing.currency
        )

    # ── Images ────────────────────────────────────────────────────────────
    additional_images = product_data.get('additional_images', [])
    if additional_images and created:
        for order, img_url in enumerate(additional_images[:10]):
            if img_url:
                ProductImage.objects.get_or_create(
                    product=product,
                    image_url=img_url,
                    defaults={'order': order}
                )

    # ── Specifications ────────────────────────────────────────────────────
    specs = product_data.get('specifications', {})
    if specs:
        for name, value in specs.items():
            ProductSpecification.objects.update_or_create(
                product=product,
                name=name,
                defaults={'value': str(value)}
            )

    return product, listing, created
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

    gtin         = (product_data.get('gtin') or '').strip() or None
    brand        = (product_data.get('brand') or '').strip()
    model_number = (product_data.get('model_number') or '').strip()
    title        = product_data.get('title', 'Unknown Product')
    product = None

    if gtin:
        product = Product.objects.filter(gtin=gtin).first()

    if not product and brand and model_number:
        product = Product.objects.filter(
            brand__iexact=brand,
            model_number__iexact=model_number
        ).first()

    if not product:
        product, _ = Product.objects.get_or_create(
            title=title,
            defaults={
                'description': product_data.get('description', '') or '',
                'brand': brand,
                'model_number': model_number,
                'main_image': product_data.get('main_image', '') or '',
                'gtin': gtin,
            }
        )
    else:
        if gtin and not product.gtin:
            product.gtin = gtin
            product.save(update_fields=['gtin'])

    # ── Listing ──────────────────────────────────────────────────────────
    shipping_info = product_data.get('shipping_info', {})

    listing, listing_created = ProductListing.objects.update_or_create(
        product=product,
        platform=platform,
        external_id=product_data.get('external_id'),
        defaults={
            'external_url':           product_data.get('external_url', ''),
            'price':                  product_data.get('price', 0),
            'currency':               product_data.get('currency', 'USD'),
            'original_price':         product_data.get('original_price'),
            'discount_percentage':    product_data.get('discount_percentage'),
            'condition':              product_data.get('condition', 'NEW'),
            'quantity':               product_data.get('quantity', 0),
            'seller_username':        product_data.get('seller_username', ''),
            'seller_rating':          product_data.get('seller_rating'),
            'seller_feedback_count':  product_data.get('seller_feedback_count', 0),
            'item_location':          product_data.get('item_location', ''),
            'ships_from_country':     product_data.get('ships_from_country', ''),
            'shipping_cost':          shipping_info.get('cost', 0),
            'shipping_currency':      shipping_info.get('currency', 'USD'),
            'free_shipping':          shipping_info.get('free_shipping', False),
            'estimated_delivery_days':shipping_info.get('estimated_days'),
            'returns_accepted':       product_data.get('returns_accepted', False),
            'return_period_days':     product_data.get('return_period_days'),
            'is_available':           product_data.get('is_available', True),
        }
    )

    # ── Price History ─────────────────────────────────────────────────────
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

    # ── Images ────────────────────────────────────────────────────────────
    if product_data.get('additional_images'):
        ProductImage.objects.filter(product=product).delete()
        for order, image_url in enumerate(product_data['additional_images'][:10]):
            ProductImage.objects.create(product=product, image_url=image_url, order=order)

    # ── Specifications ────────────────────────────────────────────────────
    if product_data.get('specifications'):
        ProductSpecification.objects.filter(product=product).delete()
        for name, value in product_data['specifications'].items():
            ProductSpecification.objects.create(product=product, name=name, value=value)

    return product, listing, listing_created



# ============================================================================
#   Platform-specific sync helpers
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


def _generic_sync_loop(items, platform, external_id_key, save_callable, use_category_cache=False, query=None):
    result = _build_result_template('', platform.code, 0)
    cat_cache = list(Category.objects.all())

    for item in items:
        external_id = item.get(external_id_key)
        if not external_id: continue
        result['external_ids'].append(external_id)

        try:
            with transaction.atomic():
                product, listing, created = save_callable(
                    item, 
                    platform, 
                    query=query, 
                    all_categories=cat_cache
                )

                if product and listing:
                    if created: result['synced'] += 1
                    else: result['updated'] += 1
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
                else: result['failed'] += 1
        except Exception as e:
            result['failed'] += 1
            logger.error(f"Sync failed for ID {external_id}: {str(e)}")

    return result


def sync_ebay_products(platform, query, limit):
    """
        eBay timeout is high so run it in background task.
    """
    from .tasks import sync_ebay_task
    task = sync_ebay_task.delay(query, limit)
    
    return success_response({
        'query':        query,
        'platform':     'ebay',
        'task_id':      task.id,
        'message':      'eBay sync started in background (takes ~60s)',
        'check_status': f'/api/v1/fetch-products/task-status/{task.id}/',
    }, message="eBay sync started")


# def sync_clickbank_products(platform, query, limit):
#     clickbank_service = ClickBankService()
#     search_results = clickbank_service.search_mock_products(query, limit)

#     if not search_results:
#         return error_response("No ClickBank products found", code=404)

#     normalized_items = []
#     for item in search_results:
#         try:
#             normalized_items.append(clickbank_service.extract_product_data(item))
#         except Exception:
#             continue

#     result = _generic_sync_loop(
#         normalized_items, platform, 'external_id', save_clickbank_product_to_db,
#         use_category_cache=False
#     )
#     result['query'] = query
#     result['limit'] = limit
#     return success_response(result, message="ClickBank sync completed")


def _normalize_and_sync_generic(service, platform, query, limit, success_msg, not_found_msg):
    items = service.search_products(query, limit=limit)

    if not items:
        return error_response(not_found_msg, code=404)

    normalized = []
    query_words = set(query.lower().split())

    for item in items:
        try:
            product_data = service.extract_product_data(item)

            # ── Relevance check ──────────────────────────────────────────
            # title বা brand এ query এর অন্তত একটা word থাকতে হবে
            title_lower = (product_data.get('title') or '').lower()
            brand_lower = (product_data.get('brand') or '').lower()

            is_relevant = any(
                word in title_lower or word in brand_lower
                for word in query_words
                if len(word) > 2  # ছোট words বাদ
            )

            if not is_relevant:
                logger.debug(f"Skipped irrelevant: '{product_data.get('title', '')[:50]}'")
                continue

            normalized.append(product_data)
        except Exception:
            continue

    if not normalized:
        return error_response(not_found_msg, code=404)

    result = _generic_sync_loop(
        normalized, platform, 'external_id', save_generic_product_to_db,
        use_category_cache=True,
        query=query
    )
    result['query'] = query
    result['limit'] = limit
    return success_response(result, message=success_msg)


def sync_walmart_products(platform, query, limit):
    service = WalmartService()
    items = service.search_products(query, limit=limit)
    
    if not items:
        return error_response("No Walmart products found", code=404)

    all_categories = list(Category.objects.all())
    
    normalized = []
    for item in items:
        try:
            p_data = service.extract_product_data(item)
            normalized.append(p_data)
        except: continue

    result = _generic_sync_loop(normalized, platform, 'external_id', save_generic_product_to_db)
    result['query'] = query
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

    result = _generic_sync_loop(
        normalized, platform, 'external_id', save_generic_product_to_db,
        use_category_cache=True,
        query=query  # ← query pass হচ্ছে
    )
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

    result = _generic_sync_loop(
        normalized, platform, 'external_id', save_generic_product_to_db,
        use_category_cache=True
    )
    result['query'] = query
    result['limit'] = limit
    return success_response(result, message="Shopify sync completed")


# def sync_homedepot_products(platform, query, limit):
#     """
#     Home Depot sync — only works with numeric productId.
#     """
#     if not str(query).strip().isdigit():
#         logger.info(f"HomeDepot skipped for non-numeric query: '{query}'")
#         result = _build_result_template(query, 'homedepot', limit)
#         result['note'] = 'HomeDepot requires numeric productId — text query skipped'
#         return success_response(result, message="Home Depot sync skipped (non-numeric query)")

#     return _normalize_and_sync_generic(
#         HomeDepotService(), platform, query, limit,
#         success_msg="Home Depot sync completed",
#         not_found_msg="No Home Depot products found",
#     )

def sync_sephora_products(platform, query, limit):
    return _normalize_and_sync_generic(
        SephoraService(), platform, query, limit,
        success_msg="Sephora sync completed",
        not_found_msg="No Sephora products found",
    )

def sync_target_products(platform, query, limit):
    return _normalize_and_sync_generic(
        TargetService(), platform, query, limit,
        success_msg="Target sync completed",
        not_found_msg="No Target products found",
    )
def sync_wayfair_products(platform, query, limit):
    return _normalize_and_sync_generic(
        WayfairService(), platform, query, limit,
        success_msg="Wayfair sync completed",
        not_found_msg="No Wayfair products found",
    )
def sync_aliexpress_products(platform, query, limit):
    return _normalize_and_sync_generic(
        AliExpressService(), platform, query, limit,
        success_msg="AliExpress sync completed",
        not_found_msg="No AliExpress products found",
    )

def sync_bestbuy_products(platform, query, limit):
    return _normalize_and_sync_generic(
        BestBuyService(), platform, query, limit,
        success_msg="BestBuy sync completed",
        not_found_msg="No BestBuy products found",
    )
# ── Register sync functions ──────────────────────────────────────────────────

PLATFORM_SYNC_CONFIG = {
    'ebay': {'sync_func': sync_ebay_products, 'name': 'eBay'},
    # 'clickbank': {'sync_func': sync_clickbank_products,  'name': 'ClickBank'},
    # 'walmart':   {'sync_func': sync_walmart_products,    'name': 'Walmart'},
    'amazon':    {'sync_func': sync_amazon_products,     'name': 'Amazon'},
    'sephora': {'sync_func': sync_sephora_products, 'name': 'Sephora'},
    'target': {'sync_func': sync_target_products, 'name': 'Target'},
    'wayfair': {'sync_func': sync_wayfair_products, 'name': 'Wayfair'},
    'aliexpress': {'sync_func': sync_aliexpress_products, 'name': 'AliExpress'},
    'bestbuy': {'sync_func': sync_bestbuy_products, 'name': 'BestBuy'},
    # 'shopify':   {'sync_func': sync_shopify_products,    'name': 'Shopify'},
    # 'homedepot': {'sync_func': sync_homedepot_products,  'name': 'Home Depot'},
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
    serializer_class = PlatformSerializer
    lookup_field = 'code'

    def get_queryset(self):
        # local seller platforms ও দেখাও
        return Platform.objects.filter(
            api_enabled=True
        ) | Platform.objects.filter(
            code__startswith='local-seller-'
        )


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
    platform_code = request.GET.get('platform', 'amazon')

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
        return error_response(
            f'Platform "{platform_code}" is not supported for sync', code=400
        )

    return sync_func(platform, query, limit)

@api_view(['POST'])
def bulk_sync_products(request):
    platform_code = request.data.get('platform')
    product_ids   = request.data.get('product_ids') or request.data.get('external_ids', [])
 
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
            if platform_code == 'ebay':
                raw = service.search_products(str(external_id), limit=1)
                if not raw:
                    result['failed'] += 1
                    continue
                product_data = service.extract_product_data(raw[0])
                product_data['external_id'] = external_id
                with transaction.atomic():
                    product, listing, created = save_generic_product_to_db(
                        product_data, platform
                    )
 
            elif platform_code == 'walmart':
                item_data = service.get_product_details(external_id)
                if not item_data:
                    result['failed'] += 1
                    continue
                product_data = service.extract_product_data(item_data)
                product_data['external_id'] = external_id
                with transaction.atomic():
                    product, listing, created = save_generic_product_to_db(
                        product_data, platform
                    )
 
            else:
                hits = service.search_products(str(external_id), limit=1)
                if not hits:
                    result['failed'] += 1
                    continue
                raw_item     = hits[0]
                product_data = (
                    service.extract_product_data(raw_item)
                    if hasattr(service, 'extract_product_data') else raw_item
                )
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
            logger.error(f"Failed to bulk sync {external_id}: {e}", exc_info=True)
 
    return success_response(result, message="Bulk sync completed")


@api_view(['POST'])
def sync_from_search_results(request):
    query         = request.data.get('query', '')
    limit         = min(int(request.data.get('limit', 10)), 50)
    platform_code = request.data.get('platform', 'ebay')
 
    if not query:
        return error_response('Query is required', code=400)
 
    try:
        platform = Platform.objects.get(code=platform_code)
    except Platform.DoesNotExist:
        return error_response(f'Platform "{platform_code}" not found', code=404)
 
    if platform_code == 'ebay':
        service    = EbayRapidService()
        raw_items  = service.search_products(query, limit=limit)
        items      = [service.extract_product_data(i) for i in (raw_items or [])]
        id_key     = 'external_id'
        search_results = {'total': len(items)}
 
    elif platform_code == 'clickbank':
        service        = ClickBankService()
        items          = service.search_mock_products(query, limit)
        id_key         = 'site'
        search_results = {'total': len(items)}
 
    elif platform_code == 'walmart':
        service        = WalmartService()
        items          = service.search_products(query, limit=limit)
        id_key         = 'itemId'
        search_results = {'total': len(items)}
 
    elif platform_code == 'amazon':
        service        = AmazonService()
        items          = service.search_products(query, limit=limit)
        id_key         = 'asin'
        search_results = {'total': len(items)}
 
    elif platform_code == 'shopify':
        service        = ShopifyService()
        items          = service.search_products(query, limit=limit)
        id_key         = 'id'
        search_results = {'total': len(items)}
 
    else:
        return error_response(f'Platform "{platform_code}" sync not implemented', code=501)
 
    needs_cat_cache = platform_code not in ('ebay', 'clickbank')
    cat_cache       = _get_category_cache() if needs_cat_cache else None
 
    result = {
        'query':       query,
        'platform':    platform_code,
        'total_found': search_results.get('total', len(items)) if isinstance(search_results, dict) else len(items),
        'items_fetched': len(items),
        'synced':      0,
        'updated':     0,
        'skipped':     0,
        'failed':      0,
        'products':    [],
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
                    'title':      existing.product.title,
                    'price':      float(existing.price),
                    'currency':   existing.currency,
                    'status':     'already_exists',
                })
                continue
 
            with transaction.atomic():
                if platform_code == 'ebay':
                    # eBay: item is already extracted (dict with external_id etc.)
                    product, listing, created = save_generic_product_to_db(
                        item, platform, cat_cache
                    )
                elif platform_code == 'clickbank':
                    product_data = service.extract_product_data(item)
                    product, listing, created = save_clickbank_product_to_db(product_data, platform)
                else:
                    product_data = service.extract_product_data(item)
                    product, listing, created = save_generic_product_to_db(
                        product_data, platform, cat_cache
                    )
 
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
                    'title':      product.title,
                    'slug':       product.slug,
                    'price':      float(listing.price),
                    'currency':   listing.currency,
                    'seller':     listing.seller_username,
                    'condition':  listing.condition,
                    'status':     status_text,
                })
            else:
                result['failed'] += 1
 
        except Exception as e:
            result['failed'] += 1
            logger.error(f"Failed to sync {external_id}: {e}", exc_info=True)
 
    return success_response(result, message="Sync from search completed")
 

@api_view(['GET'])
def get_external_ids(request):
    query         = request.GET.get('q', '')
    limit         = min(int(request.GET.get('limit', 10)), 50)
    platform_code = request.GET.get('platform', 'ebay')
 
    if not query:
        return error_response('Query parameter "q" is required', code=400)
 
    if platform_code == 'all':
        all_items = []
        errors    = {}
 
        # ── eBay ─────────────────────────────────────────────────────────────
        try:
            ebay_service = EbayRapidService()
            raw_ebay     = ebay_service.search_products(query, limit=limit)
            for item in (raw_ebay or []):
                d = ebay_service.extract_product_data(item)
                all_items.append({
                    'external_id': d.get('external_id', ''),
                    'platform':    'ebay',
                    'title':       d.get('title'),
                    'price':       d.get('price', 0),
                    'currency':    'USD',
                    'condition':   d.get('condition'),
                    'url':         d.get('external_url', ''),
                    'image':       d.get('main_image', ''),
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
                    'platform':    'clickbank',
                    'title':       item.get('title'),
                    'price':       item.get('price'),
                    'currency':    'USD',
                    'condition':   'NEW',
                    'url':         item.get('url'),
                })
        except Exception as e:
            logger.error(f"ClickBank search failed: {e}")
            errors['clickbank'] = str(e)
 
        # ── Amazon ────────────────────────────────────────────────────────────
        try:
            amazon_service = AmazonService()
            amazon_items   = amazon_service.search_products(query, limit=limit)
            for item in (amazon_items or []):
                price_raw = item.get('product_price') or item.get('price') or '0'
                try:
                    price_val = float(str(price_raw).replace('$', '').replace(',', '').strip())
                except (ValueError, TypeError):
                    price_val = 0.0
                all_items.append({
                    'external_id': item.get('asin'),
                    'platform':    'amazon',
                    'title':       item.get('product_title') or item.get('title'),
                    'price':       price_val,
                    'currency':    'USD',
                    'condition':   'NEW',
                    'url':         item.get('product_url') or item.get('url'),
                    'image':       item.get('product_photo') or item.get('thumbnail'),
                    'rating':      item.get('product_star_rating'),
                })
        except Exception as e:
            logger.error(f"Amazon search failed: {e}")
            errors['amazon'] = str(e)
 
        # ── Walmart ───────────────────────────────────────────────────────────
        try:
            walmart_service = WalmartService()
            walmart_items   = walmart_service.search_products(query, limit=limit)
            for item in (walmart_items or []):
                all_items.append({
                    'external_id': str(item.get('usItemId') or item.get('id') or ''),
                    'platform':    'walmart',
                    'title':       item.get('name') or item.get('title'),
                    'price':       item.get('price') or item.get('originalPrice') or 0,
                    'currency':    'USD',
                    'condition':   'NEW',
                    'url':         item.get('canonicalUrl') or item.get('productUrl') or '',
                    'image':       item.get('image') or item.get('main_image'),
                })
        except Exception as e:
            logger.error(f"Walmart search failed: {e}")
            errors['walmart'] = str(e)
 
        # ── Sephora ───────────────────────────────────────────────────────────
        try:
            sephora_service = SephoraService()
            sephora_items   = sephora_service.search_products(query, limit=limit)
            for item in (sephora_items or []):
                d = sephora_service.extract_product_data(item)
                all_items.append({
                    'external_id': d.get('external_id', ''),
                    'platform':    'sephora',
                    'title':       d.get('title'),
                    'price':       d.get('price', 0),
                    'currency':    'USD',
                    'condition':   'NEW',
                    'url':         d.get('external_url', ''),
                    'image':       d.get('main_image', ''),
                })
        except Exception as e:
            logger.error(f"Sephora search failed: {e}")
            errors['sephora'] = str(e)
 
        response_data = {
            'query':          query,
            'platform':       'all',
            'items_returned': len(all_items),
            'items':          all_items,
        }
        if errors:
            response_data['platform_errors'] = errors
 
        return success_response(response_data, message="External IDs fetched")
 
    # ── Single platform ───────────────────────────────────────────────────────
    platform_config = {
        'ebay':      (EbayRapidService, 'external_id'),
        'clickbank': (ClickBankService, 'site'),
        'walmart':   (WalmartService,   'usItemId'),
        'amazon':    (AmazonService,    'asin'),
        'sephora':   (SephoraService,   'external_id'),
    }
 
    if platform_code not in platform_config:
        return error_response(f'Platform "{platform_code}" not supported', code=400)
 
    service_class, id_key = platform_config[platform_code]
    service               = service_class()
 
    if platform_code == 'ebay':
        raw_items      = service.search_products(query, limit=limit)
        items          = [service.extract_product_data(i) for i in (raw_items or [])]
        search_results = {'total': len(items)}
    elif platform_code == 'clickbank':
        items          = service.search_mock_products(query, limit)
        search_results = {'total': len(items)}
    elif platform_code == 'sephora':
        raw_items      = service.search_products(query, limit=limit)
        items          = [service.extract_product_data(i) for i in (raw_items or [])]
        search_results = {'total': len(items)}
    else:
        items          = service.search_products(query, limit=limit) or []
        search_results = {'total': len(items)}
 
    external_ids = []
    items_detail = []
 
    for item in items:
        item_id = item.get(id_key)
        external_ids.append(item_id)
        items_detail.append({
            'external_id': item_id,
            'title':       item.get('title') or item.get('name'),
            'price':       item.get('price', 0),
            'currency':    'USD',
            'condition':   item.get('condition', 'NEW'),
            'url':         item.get('external_url') or item.get('url') or item.get('canonicalUrl', ''),
            'image':       item.get('main_image') or item.get('image', ''),
        })
 
    return success_response({
        'query':          query,
        'platform':       platform_code,
        'total_found':    search_results.get('total', len(items)) if isinstance(search_results, dict) else len(items),
        'items_returned': len(items),
        'external_ids':   external_ids,
        'items':          items_detail,
        'bulk_sync_body': {
            'platform':    platform_code,
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


@api_view(['GET'])
def smart_search(request):
    query = request.GET.get('q', '')
    limit = min(int(request.GET.get('limit', 10)), 50)

    if not query:
        return error_response('q is required', code=400)

    cache_key = f'smart_search_v3_{query}_{limit}'
    cached = cache.get(cache_key)
    if cached:
        return success_response({
            'source': 'cache',
            'query': query,
            'results': cached,
        }, message="Results from cache")

    # DB তে আছে কিনা চেক করো
    existing_products = Product.objects.filter(
        Q(title__icontains=query) | Q(description__icontains=query),
        is_active=True,
        listings__is_available=True,
    ).prefetch_related('listings__platform').distinct()

    if existing_products.exists():
        # Background sync
        sync_all_platforms_task.delay(query, limit)

        results = []
        for product in existing_products[:limit]:
            listings = product.listings.filter(
                is_available=True
            ).select_related('platform').order_by('price')

            if not listings.exists():
                continue

            # Duplicate URL বাদ দাও
            seen_urls = set()
            price_comparison = []
            for listing in listings:
                if listing.external_url in seen_urls:
                    continue
                seen_urls.add(listing.external_url)
                price_comparison.append({
                    'platform':            listing.platform.name,
                    'platform_code':       listing.platform.code,
                    'price':               float(listing.price) if listing.price else 0,
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
            best_deal = valid_prices[0]
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
                'best_deal': {
                    'platform':      best_deal['platform'],
                    'platform_code': best_deal['platform_code'],
                    'price':         best_deal['price'],
                    'url':           best_deal['url'],
                    'free_shipping': best_deal['free_shipping'],
                },
                'price_comparison': valid_prices,
            })

        results.sort(key=lambda x: x['lowest_price'] or 0)
        cache.set(cache_key, results, 300)

        return success_response({
            'source':  'database',
            'query':   query,
            'count':   len(results),
            'note':    'Background sync started for fresh data',
            'results': results,
        }, message="Results from database")

    # DB তে নেই — sync করো
    task = sync_all_platforms_task.delay(query, limit)
    return success_response({
        'source':        'syncing',
        'query':         query,
        'task_id':       task.id,
        'message':       'Data fetching started from all platforms',
        'check_status':  f'/api/v1/fetch-products/task-status/{task.id}/',
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
    ).prefetch_related(
        'listings__platform'
    ).distinct()

    if sort == 'price_low':
        products = products.annotate(min_price=Min('listings__price')).order_by('min_price')
    elif sort == 'price_high':
        products = products.annotate(min_price=Min('listings__price')).order_by('-min_price')
    elif sort == 'newest':
        products = products.order_by('-created_at')
    elif sort == 'popular':
        products = products.annotate(listing_count=Count('listings')).order_by('-listing_count')
    else:
        products = products.annotate(min_price=Min('listings__price')).order_by('min_price')

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
        listings = product.listings.filter(is_available=True).select_related('platform')

        if platform_filter:
            listings = listings.filter(platform__code=platform_filter)

        if not listings.exists():
            continue

        price_comparison = []
        for listing in listings.order_by('price'):
            price_comparison.append({
                'platform': listing.platform.name,
                'platform_code': listing.platform.code,
                'price': float(listing.price),
                'currency': listing.currency,
                'original_price': float(listing.original_price) if listing.original_price else None,
                'discount_percentage': float(listing.discount_percentage) if listing.discount_percentage else None,
                'shipping_cost': float(listing.shipping_cost),
                'free_shipping': listing.free_shipping,
                'total_price': float(listing.get_total_price()),
                'condition': listing.condition,
                # 'seller': listing.seller_username,
                # 'seller_rating': float(listing.seller_rating) if listing.seller_rating else None,
                'url': listing.external_url,
                # 'last_updated': listing.last_checked,
            })

        best_deal = price_comparison[0] if price_comparison else None

        results.append({
            'product': {
                'id': product.id,
                'title': product.title,
                'slug': product.slug,
                # 'brand': product.brand,
                'main_image': product.main_image,
                'category': category.name,
                'category_slug': category.slug,
            },
            'best_deal': best_deal,
            'lowest_price': best_deal['price'] if best_deal else None,
            'platforms_count': len(price_comparison),
            'price_comparison': price_comparison,
        })

    # ── Best Overall Deal ──────────────────────────────────────
    valid_results = [r for r in results if r['lowest_price'] and r['lowest_price'] > 0]
    best_overall_deal = None
    if valid_results:
        best = min(valid_results, key=lambda x: x['lowest_price'])
        best_overall_deal = {
            'product_id': best['product']['id'],
            'title': best['product']['title'],
            'price': best['lowest_price'],
            'currency': best['best_deal']['currency'],
            'discount_percentage': best['best_deal']['discount_percentage'],
            'platform': best['best_deal']['platform'],
            'platform_code': best['best_deal']['platform_code'],
            'url': best['best_deal']['url'],
            'main_image': best['product']['main_image'],
        }

    return success_response({
        'category': {
            'id': category.id,
            'name': category.name,
            'slug': category.slug,
            'parent': category.parent.name if category.parent else None,
            'subcategories': list(children.values('id', 'name', 'slug')),
        },
        'pagination': {
            'total_products': total_count,
            'total_pages': total_pages,
            'current_page': page,
            'page_size': page_size,
            'has_next': page < total_pages,
            'has_prev': page > 1,
        },
        'sort': sort,
        'filters': {
            'platform': platform_filter,
        },
        'best_overall_deal': best_overall_deal,
        'results': results,
    }, message=f"Price comparison for '{category.name}'")