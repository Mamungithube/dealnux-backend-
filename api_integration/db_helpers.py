"""
db_helpers.py
─────────────
views.py ও tasks.py উভয়েই এই module use করে।
Circular import ভাঙতে save logic এখানে রাখা হয়েছে।
"""

import time
import logging
from django.db import transaction
from django.utils.text import slugify
from django.db.models import Q

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Category Cache  (thread-safe নয়, single-worker dev এর জন্য যথেষ্ট;
#                  production multi-worker এ Django cache framework use করো)
# ─────────────────────────────────────────────────────────────────────────────

_CATEGORY_CACHE = None


def _get_category_cache():
    global _CATEGORY_CACHE
    now = time.time()
    if _CATEGORY_CACHE is None or (now - _CATEGORY_CACHE['loaded_at']) > 300:
        from .models import Category
        qs = Category.objects.all().only('id', 'name', 'slug')
        _CATEGORY_CACHE = {
            'by_slug':       {cat.slug: cat for cat in qs},
            'by_name_lower': {cat.name.lower(): cat for cat in qs},
            'all':           list(qs),
            'loaded_at':     now,
        }
    return _CATEGORY_CACHE


# ── Keyword → Category slug map ──────────────────────────────────────────────
_KEYWORD_CATEGORY_MAP = [
    # ── Shoes / Footwear (generic — must come before gender-specific) ─────────
    (['shoe', 'shoes', 'sneaker', 'sneakers', 'boot', 'boots',
      'loafer', 'loafers', 'heel', 'heels', 'sandal', 'sandals',
      'slipper', 'slippers', 'footwear', 'trainer', 'trainers',
      'wedge shoe', 'platform shoe', 'clog', 'clogs',
      'golf shoe', 'running shoe', 'walking shoe'], 'footwear'),

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

    # Fashion — Men
    (['men\'s shirt', 'men\'s jacket', 'men\'s pants', 'men\'s suit', 'men\'s clothing'], 'mens-clothing'),
    (['men\'s shoe', 'men\'s sneaker', 'men\'s boot'], 'mens-shoes'),
    (['men\'s watch'], 'mens-watches'),
    (['men\'s belt', 'men\'s wallet', 'men\'s tie'], 'mens-accessories-belts'),

    # Fashion — Women
    (['women\'s dress', 'women\'s blouse', 'women\'s skirt', 'women\'s clothing'], 'womens-clothing'),
    (['women\'s shoe', 'women\'s heel', 'women\'s boot', 'women\'s sneaker'], 'womens-shoes'),
    (['handbag', 'purse', 'tote bag', 'clutch bag', 'women\'s wallet'], 'handbags-wallets'),
    (['necklace', 'ring', 'bracelet', 'earring', 'fine jewelry', 'diamond'], 'fine-jewelry'),
    (['makeup', 'lipstick', 'foundation', 'mascara', 'eyeshadow', 'blush', 'concealer'], 'beauty-makeup'),

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
    (['blood pressure', 'thermometer', 'glucose monitor', 'medical', 'first aid'], 'medical-supplies-equipment'),
    (['razor', 'deodorant', 'body wash', 'hand sanitizer', 'personal care'], 'personal-care-hygiene'),

    # Sports
    (['treadmill', 'dumbbell', 'barbell', 'yoga mat', 'resistance band', 'gym', 'fitness'], 'exercise-fitness-equipment'),
    (['bicycle', 'cycling', 'bike helmet'], 'cycling-bicycles'),
    (['tent', 'sleeping bag', 'backpack', 'hiking', 'camping'], 'camping-hiking'),
    (['fishing rod', 'fishing reel', 'fishing lure', 'tackle box'], 'fishing-equipment'),
    (['football', 'basketball', 'soccer', 'baseball', 'volleyball', 'team sport'], 'team-sports'),

    # Kids & Baby
    (['baby', 'infant', 'newborn', 'diaper', 'baby monitor', 'baby food'], 'baby-products-accessories'),
    (['toy', 'lego', 'barbie', 'action figure', 'stuffed animal', 'nerf'], 'toys-games'),

    # Automotive
    (['car charger', 'dash cam', 'car stereo', 'gps navigation', 'car electronics'], 'car-electronics-gps'),

    # Food & Household
    (['snack', 'chips', 'candy', 'cookie', 'popcorn', 'nuts', 'jerky'], 'snack-foods'),
    (['coffee', 'tea', 'energy drink', 'protein shake', 'beverage'], 'beverages-coffee'),
    (['cleaning', 'detergent', 'dish soap', 'paper towel', 'trash bag', 'household'], 'household-cleaning-supplies'),
]


def _resolve_category(category_path, title, cache):
    title_lower = (title or '').lower()
    print(f"DEBUG: 3rd Party Category Path: {category_path}") # এটি আপনার কনসোলে দেখাবে
    print(f"DEBUG: Product Title: {title}")

    if category_path:
        clean_name = category_path.split('>')[0].strip()
        slug_key   = slugify(clean_name)
        lower_key  = clean_name.lower()

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
    from .models import Product

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
            'black', 'white', 'blue', 'pink', 'green', 'yellow',
            'red', 'purple', 'silver', 'gold', 'titanium',
            'premium', 'excellent', 'good', 'fair', 'condition',
        }

        def get_keywords(t):
            words = t.lower().replace('-', ' ').replace('&', '').replace('amp', '').split()
            return {w for w in words if len(w) > 2 and w not in noise_words}

        title_keywords = get_keywords(title_lower)
        best_match = None
        best_score = 0

        for existing in brand_products:
            existing_keywords = get_keywords(existing.title.lower())
            if not existing_keywords or not title_keywords:
                continue
            intersection = len(title_keywords & existing_keywords)
            union        = len(title_keywords | existing_keywords)
            score        = intersection / union if union > 0 else 0
            if score > 0.35 and score > best_score:
                best_score = score
                best_match = existing

        if best_match:
            return best_match

    slug = slugify(title)[:500]
    from .models import Product
    return Product.objects.filter(slug=slug).first()


# ─────────────────────────────────────────────────────────────────────────────
# eBay currency validation — non-USD listings বাদ দাও
# ─────────────────────────────────────────────────────────────────────────────

# eBay international responses এ এই currency codes আসতে পারে
_NON_USD_INDICATORS = [
    'HUF', 'EUR', 'GBP', 'CAD', 'AUD', 'JPY', 'CNY', 'KRW',
    'INR', 'BRL', 'MXN', 'CHF', 'SEK', 'NOK', 'DKK', 'PLN',
    'CZK', 'HKD', 'SGD', 'NZD', 'ZAR', 'TRY', 'RUB', 'THB',
]

MAX_REASONABLE_PRICE = 5000.0   # এর বেশি হলে anomaly হিসেবে ধরব


def is_valid_usd_price(price_raw_str, price_float):
    """
    If True, price valid USD.
    If False, skip — non-USD currency or anomaly.
    """
    raw = str(price_raw_str or '').upper()
    for code in _NON_USD_INDICATORS:
        if code in raw:
            return False
    if price_float > MAX_REASONABLE_PRICE:
        logger.warning(f"Price anomaly detected: {price_float} — skipping listing")
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Core save helper
# ─────────────────────────────────────────────────────────────────────────────

def save_generic_product_to_db(product_data, platform, query=None, category_slug=None, all_categories=None):
    """
    Universal save helper for all platforms.
    No circular import — both views.py and tasks.py can use it. 
    """
    from .models import (
        Product, ProductListing, Category,
        PriceHistory, ProductImage, ProductSpecification,
    )
    raw_currency = product_data.get('currency')
    if not raw_currency and product_data.get('_price_raw'):
        import re
        # স্ট্রিং থেকে ৩ অক্ষরের কারেন্সি কোড খোঁজা (যেমন: EUR, HUF, GBP)
        match = re.search(r'[A-Z]{3}', product_data['_price_raw'].upper())
        if match:
            raw_currency = match.group()
    product_data['currency'] = raw_currency if raw_currency else 'USD'

    
    external_id = product_data.get('external_id')
    if not external_id:
        return None, None, False

    title = product_data.get('title', 'Unknown Product')
    brand = (product_data.get('brand') or '').strip()
    gtin  = (product_data.get('gtin') or '').strip() or None
    asin  = (product_data.get('asin') or '').strip() or None

    if not brand and title != 'Unknown Product':
        brand = ' '.join(title.split()[:2])

    # ── Price validation (non-USD / anomaly guard) ────────────────────────
    price_val     = float(product_data.get('price', 0) or 0)
    price_raw_str = product_data.get('_price_raw', '')   # service set করলে
    if not is_valid_usd_price(price_raw_str, price_val):
        logger.info(f"Skipped listing (price invalid): {title[:50]} | price={price_val}")
        return None, None, False

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

    # ── Product find or create ────────────────────────────────────────────
    with transaction.atomic():
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

        # ── Listing ───────────────────────────────────────────────────────
        shipping = product_data.get('shipping_info', {})
        listing, listing_created = ProductListing.objects.update_or_create(
            platform    = platform,
            external_id = external_id,
            defaults    = {
                'product':           product,
                'external_url':      product_data.get('external_url', ''),
                'price':             price_val,
                'currency':          product_data.get('currency', 'USD'),
                'original_price':    product_data.get('original_price'),
                'discount_percentage': product_data.get('discount_percentage'),
                'condition':         product_data.get('condition', 'NEW'),
                'quantity':          int(product_data.get('quantity') or 1),
                'seller_username':   product_data.get('seller_username', 'Merchant'),
                'seller_rating':     product_data.get('seller_rating'),
                'seller_feedback_count': product_data.get('seller_feedback_count', 0),
                'item_location':     product_data.get('item_location', ''),
                'ships_from_country': product_data.get('ships_from_country', ''),
                'shipping_cost':     shipping.get('cost', 0),
                'shipping_currency': shipping.get('currency', 'USD'),
                'free_shipping':     bool(shipping.get('free_shipping', False)),
                'estimated_delivery_days': shipping.get('estimated_days'),
                'returns_accepted':  product_data.get('returns_accepted', False),
                'return_period_days': product_data.get('return_period_days'),
                'is_available':      bool(product_data.get('is_available', True)),
            }
        )

        # ── Price History ─────────────────────────────────────────────────
        if listing_created:
            PriceHistory.objects.create(
                listing=listing, price=listing.price, currency=listing.currency
            )

        # ── Images (only on first create) ─────────────────────────────────
        additional_images = product_data.get('additional_images', [])
        if additional_images and created:
            for order, img_url in enumerate(additional_images[:10]):
                if img_url:
                    ProductImage.objects.get_or_create(
                        product=product,
                        image_url=img_url,
                        defaults={'order': order}
                    )

        # ── Specifications ────────────────────────────────────────────────
        specs = product_data.get('specifications', {})
        if specs:
            for name, value in specs.items():
                ProductSpecification.objects.update_or_create(
                    product=product,
                    name=name,
                    defaults={'value': str(value)}
                )

    return product, listing, created