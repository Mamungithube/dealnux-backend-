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
from .product_matcher import calculate_match_score 

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

    # ── ELECTRONICS ───────────────────────────────────────────────────────
    (['smartphone', 'iphone', 'android phone', 'mobile phone', 'cell phone'],
     'smartphones-cell-phones'),
    (['laptop', 'notebook', 'macbook', 'chromebook'],
     'laptops'),
    (['desktop', 'pc tower', 'all-in-one computer'],
     'desktop-computers'),
    (['tablet', 'ipad', 'kindle fire', 'e-reader'],
     'tablets-e-readers'),
    (['monitor', 'display screen', 'lcd screen', 'led monitor'],
     'monitors-displays'),
    (['cpu', 'motherboard', 'graphics card', 'gpu', 'computer component'],
     'computer-components-parts'),
    (['keyboard', 'computer mouse', 'usb hub', 'computer accessory'],
     'computer-accessories'),
    (['printer', 'ink cartridge', 'toner cartridge', 'scanner'],
     'printers-scanners-ink'),
    (['router', 'wifi extender', 'network switch', 'modem', 'networking'],
     'networking-wi-fi'),
    (['hard drive', 'ssd', 'flash drive', 'memory card', 'storage device'],
     'storage-devices'),
    (['headphone', 'headset', 'earphone', 'earbud', 'airpod', 'speaker', 'earbuds'],
     'audio-headphones'),
    (['dslr', 'mirrorless camera', 'digital camera', 'camera lens', 'tripod'],
     'cameras-photography'),
    (['action camera', 'camcorder', 'gopro', 'video camera'],
     'camcorders-action-cameras'),
    (['smartwatch', 'fitness tracker', 'apple watch', 'galaxy watch', 'fitness band'],
     'smartwatches-fitness-bands'),
    (['vr headset', 'virtual reality', 'ar glasses', 'oculus', 'meta quest', 'vr glasses'],
     'virtual-reality-vr-ar'),
    (['television', '4k tv', 'oled tv', 'qled tv', 'smart tv', 'tv stand'],
     'tv-home-theater'),
    (['projector', 'projection screen'],
     'projectors-screens'),
    (['smart plug', 'smart bulb', 'smart lock', 'smart home', 'alexa', 'google home'],
     'smart-home-devices'),
    (['security camera', 'doorbell camera', 'cctv', 'home security', 'surveillance'],
     'home-security-surveillance'),
    (['playstation', 'xbox', 'nintendo switch', 'ps5', 'ps4', 'gaming console', 'video game console'],
     'video-games-consoles'),
    (['gaming mouse', 'gaming keyboard', 'gaming headset', 'gaming chair', 'gaming accessory'],
     'gaming-accessories'),
    (['drone', 'quadcopter', 'rc car', 'remote control car', 'rc plane'],
     'drones-rc-vehicles'),
    (['battery pack', 'power bank', 'usb charger', 'wireless charger', 'solar charger'],
     'batteries-chargers'),
    (['usb cable', 'hdmi cable', 'charging cable', 'adapter', 'converter cable'],
     'cables-adapters'),

    # ── MEN'S FASHION ─────────────────────────────────────────────────────
    (['men\'s shirt', 'men\'s jacket', 'men\'s pants', 'men\'s suit',
      'men\'s clothing', 'mens clothing', 'men clothing', 'for men',
      'man shirt', 'man pants', 'men\'s hoodie', 'men\'s coat'],
     'mens-clothing'),
    (['men\'s shoe', 'men\'s shoes', 'men\'s sneaker', 'men\'s boot',
      'men\'s loafer', 'men\'s sandal'],
     'mens-shoes-footwear'),
    (['men\'s watch', 'mens watch'],
     'mens-watches'),
    (['men\'s belt', 'men\'s wallet', 'men\'s tie', 'men\'s accessory'],
     'mens-accessories-belts'),
    (['men\'s sunglass', 'mens sunglasses'],
     'mens-sunglasses'),
    (['men\'s grooming', 'men\'s shaving', 'shaving kit', 'beard trimmer'],
     'mens-grooming-shaving'),
    (['men\'s underwear', 'men\'s boxer', 'men\'s brief', 'men\'s socks'],
     'mens-underwear-socks'),
    (['men\'s sportswear', 'men\'s activewear', 'men\'s gym wear', 'men\'s athletic'],
     'mens-sportswear-activewear'),
    (['men\'s suit', 'men\'s tuxedo', 'men\'s formal', 'men\'s blazer'],
     'mens-formal-wear'),
    (['men\'s backpack', 'men\'s bag', 'men\'s briefcase'],
     'mens-bags-backpacks'),

    # ── WOMEN'S FASHION ───────────────────────────────────────────────────
    (['women\'s dress', 'women\'s blouse', 'women\'s skirt', 'women\'s top',
      'women\'s pants', 'women\'s legging', 'women\'s hoodie', 'women\'s jacket',
      'women\'s clothing', 'womens clothing', 'women clothing',
      'ladies dress', 'ladies top', 'ladies clothing',
      'female clothing', 'for women', 'woman dress', 'woman top',
      'women\'s coat', 'women\'s cardigan'],
     'womens-clothing'),
    (['women\'s shoe', 'women\'s shoes', 'women\'s heel', 'women\'s heels',
      'women\'s boot', 'women\'s boots', 'women\'s sneaker', 'women\'s flat',
      'women\'s pump', 'ladies shoe', 'female shoe'],
     'womens-shoes-footwear'),
    (['handbag', 'purse', 'tote bag', 'clutch bag', 'women\'s wallet', 'shoulder bag'],
     'handbags-purses-wallets'),
    (['women\'s watch', 'ladies watch'],
     'womens-watches'),
    (['necklace', 'diamond ring', 'gold bracelet', 'fine jewelry', 'gold jewelry',
      'silver jewelry', 'gemstone', 'engagement ring'],
     'fine-jewelry'),
    (['fashion jewelry', 'costume jewelry', 'hair clip', 'hair band', 'scrunchie',
      'fashion accessory', 'women\'s accessory'],
     'fashion-jewelry-accessories'),
    (['lingerie', 'bra', 'underwear', 'pajama', 'sleepwear', 'nightgown'],
     'lingerie-sleepwear'),
    (['makeup', 'lipstick', 'foundation', 'mascara', 'eyeshadow', 'blush',
      'concealer', 'lip gloss', 'eyeliner', 'contour'],
     'beauty-makeup'),
    (['women\'s sportswear', 'women\'s activewear', 'women\'s yoga', 'women\'s athletic',
      'sports bra', 'leggings', 'yoga pants'],
     'womens-sportswear-activewear'),
    (['women\'s sunglass', 'ladies sunglasses'],
     'womens-sunglasses'),
    (['hair clip', 'headband', 'hair pin', 'hair tie', 'hair accessory'],
     'hair-accessories'),
    (['maternity', 'pregnancy clothing', 'nursing'],
     'maternity-clothing'),
    (['swimwear', 'bikini', 'swimsuit', 'cover-up', 'beach wear'],
     'swimwear-cover-ups'),
    (['plus size', 'plus size dress', 'plus size clothing'],
     'plus-size-fashion'),

    # ── HOME & KITCHEN ────────────────────────────────────────────────────
    (['sofa', 'armchair', 'dining table', 'office desk', 'bed frame',
      'bookshelf', 'wardrobe', 'cabinet', 'dresser'],
     'furniture'),
    (['wall art', 'picture frame', 'scented candle', 'decorative vase',
      'throw pillow', 'wall clock', 'home decor'],
     'home-decor-accents'),
    (['dinnerware', 'cutlery set', 'serving bowl', 'kitchen utensil', 'kitchen dining'],
     'kitchen-dining'),
    (['cookware set', 'frying pan', 'cooking pot', 'bakeware', 'baking pan', 'casserole'],
     'cookware-bakeware'),
    (['coffee maker', 'air fryer', 'instant pot', 'blender', 'toaster', 'microwave',
      'kitchen appliance'],
     'kitchen-appliances'),
    (['bed sheet', 'pillow case', 'duvet cover', 'comforter', 'bed pillow', 'bedding'],
     'bedding-pillows'),
    (['bath towel', 'hand towel', 'shower curtain', 'bath mat', 'bath accessory'],
     'bath-towels-accessories'),
    (['storage box', 'shelf organizer', 'closet organizer', 'storage basket'],
     'storage-organization'),
    (['cleaning spray', 'mop', 'broom', 'cleaning cloth', 'cleaning supplies'],
     'cleaning-supplies-tools'),
    (['laundry detergent', 'fabric softener', 'dryer sheet', 'laundry bag'],
     'laundry-fabric-care'),
    (['ceiling fan', 'floor lamp', 'table lamp', 'led bulb', 'chandelier', 'light fixture'],
     'lighting-ceiling-fans'),
    (['air conditioner', 'space heater', 'air purifier', 'humidifier', 'dehumidifier'],
     'heating-cooling-air-quality'),
    (['vacuum cleaner', 'robot vacuum', 'steam mop', 'floor cleaner'],
     'vacuums-floor-care'),
    (['refrigerator', 'washing machine', 'dishwasher', 'dryer', 'large appliance'],
     'large-appliances'),
    (['garden hose', 'lawn mower', 'plant pot', 'garden tool', 'garden fertilizer'],
     'patio-lawn-garden'),
    (['patio furniture', 'outdoor chair', 'garden bench', 'outdoor table', 'outdoor decor'],
     'outdoor-furniture-decor'),
    (['bbq grill', 'charcoal grill', 'gas grill', 'outdoor cooking', 'smoker'],
     'grills-outdoor-cooking'),
    (['power drill', 'circular saw', 'wrench set', 'screwdriver set', 'home improvement tool'],
     'tools-home-improvement'),
    (['pipe fitting', 'faucet', 'plumbing', 'hardware'],
     'plumbing-hardware'),
    (['area rug', 'carpet', 'floor mat', 'hardwood flooring'],
     'flooring-area-rugs'),
    (['curtain', 'window blind', 'window shade', 'window treatment'],
     'window-treatments'),
    (['dog food', 'cat food', 'pet toy', 'pet bed', 'aquarium', 'bird cage', 'pet leash'],
     'pet-supplies'),

    # ── HEALTH & BEAUTY ───────────────────────────────────────────────────
    (['moisturizer', 'face serum', 'sunscreen', 'face wash', 'face cream',
      'skincare', 'retinol', 'toner', 'face mask'],
     'skincare'),
    (['shampoo', 'conditioner', 'hair dryer', 'hair straightener',
      'hair growth', 'hair oil', 'hair care'],
     'hair-care'),
    (['perfume', 'cologne', 'fragrance', 'eau de toilette', 'body spray'],
     'fragrances-perfumes'),
    (['vitamin', 'multivitamin', 'fish oil', 'probiotic', 'omega', 'dietary supplement'],
     'vitamins-dietary-supplements'),
    (['protein powder', 'creatine', 'pre workout', 'bcaa', 'sports nutrition'],
     'sports-nutrition'),
    (['razor', 'deodorant', 'body wash', 'hand sanitizer', 'personal care'],
     'personal-care-hygiene'),
    (['toothbrush', 'toothpaste', 'mouthwash', 'dental floss', 'teeth whitening'],
     'oral-care'),
    (['blood pressure monitor', 'thermometer', 'glucose monitor', 'pulse oximeter',
      'medical supply', 'first aid kit'],
     'medical-supplies-equipment'),
    (['weight loss', 'diet pill', 'fat burner', 'appetite suppressant', 'slimming'],
     'weight-loss-slimming'),

    # ── SPORTS & OUTDOORS ─────────────────────────────────────────────────
    (['treadmill', 'dumbbell', 'barbell', 'yoga mat', 'resistance band',
      'pull up bar', 'gym equipment', 'exercise bike', 'rowing machine'],
     'exercise-fitness-equipment'),
    (['bicycle', 'bike helmet', 'cycling glove', 'bike lock', 'cycling'],
     'cycling-bicycles'),
    (['camping tent', 'sleeping bag', 'hiking backpack', 'hiking boot',
      'trekking pole', 'camping gear'],
     'camping-hiking-backpacking'),
    (['fishing rod', 'fishing reel', 'fishing lure', 'tackle box', 'fishing line'],
     'fishing-equipment'),
    (['swimming goggle', 'swim cap', 'surfboard', 'kayak', 'water sport'],
     'water-sports-swimming'),
    (['football', 'basketball', 'soccer ball', 'baseball glove', 'volleyball', 'team sport'],
     'team-sports'),
    (['golf club', 'golf ball', 'golf bag', 'golf glove'],
     'golf-equipment'),
    (['skateboard', 'kick scooter', 'longboard', 'roller skate'],
     'skateboarding-scooters'),

    # ── BABY & KIDS ───────────────────────────────────────────────────────
    (['baby monitor', 'baby carrier', 'baby swing', 'baby bouncer'],
     'baby-products-accessories'),
    (['stroller', 'baby stroller', 'pram', 'car seat', 'baby gear'],
     'baby-gear-strollers'),
    (['baby shoe', 'baby shoes', 'baby clothing', 'baby outfit', 'infant clothing',
      'toddler clothing', 'kids clothing'],
     'baby-clothing-shoes'),
    (['baby food', 'infant formula', 'baby cereal', 'baby snack'],
     'baby-food-formula'),
    (['diaper', 'baby wipe', 'diaper bag', 'potty trainer'],
     'diapering-potty-training'),
    (['crib', 'baby crib', 'nursery furniture', 'baby monitor', 'baby mobile'],
     'nursery-furniture-decor'),
    (['lego', 'building toy', 'lego set', 'lego block'],
     'building-toys-lego'),
    (['barbie', 'doll', 'dollhouse', 'baby doll'],
     'dolls-dollhouses'),
    (['puzzle', 'board game', 'card game', 'chess', 'jigsaw puzzle'],
     'puzzles-board-games'),
    (['action figure', 'superhero toy', 'collectible figure'],
     'action-figures-collectibles'),
    (['nerf gun', 'toy gun', 'stuffed animal', 'plush toy', 'toy'],
     'toys-games'),
    (['art kit for kids', 'craft kit', 'kids craft', 'kids art supply'],
     'arts-crafts-for-kids'),
    (['kids book', 'children book', 'educational toy', 'learning toy'],
     'kids-books-educational'),
    (['kids tablet', 'kids laptop', 'kids smartwatch', 'kids gadget'],
     'kids-electronics-gadgets'),
    (['backpack for kids', 'school bag', 'pencil case', 'school supply'],
     'school-supplies'),

    # ── AUTOMOTIVE ────────────────────────────────────────────────────────
    (['car charger', 'dash cam', 'car stereo', 'gps navigation', 'car speaker',
      'car electronics'],
     'car-electronics-gps'),
    (['car seat cover', 'steering wheel cover', 'car floor mat', 'car organizer'],
     'car-interior-accessories'),
    (['car wax', 'car wash', 'car polish', 'car detailing'],
     'car-care-detailing'),
    (['motor oil', 'engine oil', 'car fluid', 'coolant'],
     'motor-oil-fluids'),
    (['tire', 'car wheel', 'rim', 'alloy wheel'],
     'tires-wheels'),
    (['motorcycle helmet', 'motorcycle glove', 'motorcycle jacket', 'motorcycle part'],
     'motorcycle-parts-accessories'),

    # ── ARTS, CRAFTS & COLLECTIBLES ───────────────────────────────────────
    (['paint brush', 'acrylic paint', 'oil paint', 'watercolor', 'canvas',
      'art supply', 'art supplies', 'painting supply', 'sketching', 'drawing pencil'],
     'art-supplies-painting'),
    (['sewing machine', 'knitting needle', 'crochet hook', 'yarn', 'fabric'],
     'sewing-knitting-crochet'),
    (['scrapbook', 'paper craft', 'sticker', 'washi tape', 'craft paper'],
     'scrapbooking-paper-crafts'),
    (['diy craft kit', 'craft kit', 'diy kit'],
     'diy-craft-kits'),
    (['coin collection', 'commemorative coin', 'gold coin', 'silver coin'],
     'coins-currency'),
    (['pokemon card', 'magic the gathering', 'trading card', 'yugioh'],
     'trading-cards-pokemon-mtg'),
    (['antique', 'vintage item', 'collectible', 'rare item'],
     'antiques-vintage-items'),
    (['sports card', 'baseball card', 'basketball card', 'sports memorabilia'],
     'sports-cards-memorabilia'),
    (['autograph', 'signed jersey', 'signed photo', 'celebrity autograph'],
     'autographs-signed-items'),
    (['handmade', 'custom made', 'personalized item', 'handcrafted'],
     'handmade-custom-items'),
    (['pottery', 'ceramic', 'clay', 'porcelain'],
     'pottery-ceramics'),

    # ── BOOKS & ENTERTAINMENT ─────────────────────────────────────────────
    (['novel', 'fiction book', 'mystery book', 'thriller book', 'romance novel'],
     'fiction-books'),
    (['biography', 'history book', 'science book', 'non-fiction', 'self help book'],
     'non-fiction-educational-books'),
    (['children book', 'picture book', 'kids story book'],
     'childrens-books'),
    (['textbook', 'academic book', 'college textbook', 'study guide'],
     'textbooks-academic'),
    (['comic book', 'graphic novel', 'manga book'],
     'comics-graphic-novels'),
    (['movie dvd', 'blu ray', 'tv series dvd', 'film collection'],
     'movies-tv-shows'),
    (['vinyl record', 'cd album', 'music cd'],
     'music-vinyl-records'),
    (['guitar', 'piano', 'keyboard instrument', 'drum', 'violin', 'ukulele',
      'musical instrument'],
     'musical-instruments'),

    # ── FOOD & GROCERY ────────────────────────────────────────────────────
    (['chips', 'popcorn', 'beef jerky', 'granola bar', 'snack food', 'trail mix'],
     'snack-foods'),
    (['coffee bean', 'ground coffee', 'green tea', 'energy drink', 'juice', 'beverage'],
     'beverages-coffee'),
    (['pasta', 'rice', 'flour', 'canned food', 'pantry staple'],
     'pantry-staples-dry-goods'),
    (['organic food', 'natural food', 'gluten free', 'vegan food'],
     'organic-natural-foods'),
    (['chocolate', 'candy', 'gummy', 'lollipop', 'sweet'],
     'candy-chocolate'),

    # ── OFFICE & BUSINESS ─────────────────────────────────────────────────
    (['office chair', 'office desk', 'filing cabinet', 'office furniture'],
     'office-furniture'),
    (['pen', 'notebook', 'stapler', 'sticky note', 'office supply', 'stationery'],
     'office-supplies-stationery'),
    (['printer paper', 'printer cartridge', 'ink refill', 'toner'],
     'printer-cartridges-paper'),
    (['whiteboard', 'presentation board', 'flip chart', 'projector screen'],
     'presentation-whiteboards'),

    # ── TRAVEL & EXPERIENCES ─────────────────────────────────────────────
    (['suitcase', 'luggage', 'travel bag', 'carry on bag', 'rolling bag'],
     'luggage-travel-bags'),
    (['travel pillow', 'neck pillow', 'eye mask', 'travel blanket', 'travel comfort'],
     'travel-pillows-comfort'),
    (['travel adapter', 'travel bottle', 'packing cube', 'travel accessory'],
     'travel-accessories'),

    # ── WEDDING & EVENTS ──────────────────────────────────────────────────
    (['wedding dress', 'bridal gown', 'wedding veil', 'bridesmaid dress'],
     'wedding-dresses-accessories'),
    (['wedding decoration', 'wedding centerpiece', 'wedding flower'],
     'wedding-decorations'),
    (['party supply', 'birthday decoration', 'balloon', 'party banner'],
     'party-supplies-decorations'),
    (['christmas decoration', 'holiday ornament', 'halloween decoration',
      'festive decor'],
     'holiday-decorations'),
    (['gift wrap', 'gift box', 'ribbon', 'tissue paper', 'gift bag'],
     'gift-wrapping-packaging'),
    (['personalized gift', 'custom gift', 'engraved gift', 'monogram gift'],
     'personalized-custom-gifts'),
    (['flower bouquet', 'artificial flower', 'indoor plant', 'succulent'],
     'flowers-plants'),
]


def _resolve_category(category_path, title, cache):
    title_lower = (title or '').lower()

    # ── Step 1: category_path থেকে exact/partial match ───────────────────
    if category_path:
        parts = [p.strip() for p in category_path.split('>')]
        for part in parts:
            slug_key  = slugify(part)
            lower_key = part.lower()
            if slug_key in cache['by_slug']:
                return cache['by_slug'][slug_key]
            if lower_key in cache['by_name_lower']:
                return cache['by_name_lower'][lower_key]
        # partial match
        for part in parts:
            for cat_name_lower, cat_obj in cache['by_name_lower'].items():
                if len(cat_name_lower) >= 6 and (
                    cat_name_lower in part.lower()
                    or part.lower() in cat_name_lower
                ):
                    return cat_obj

    # ── Step 2: keyword match — padded for whole-word ────────────────────
    if title_lower:
        padded = f' {title_lower} '
        for keywords, target_slug in _KEYWORD_CATEGORY_MAP:
            for kw in keywords:
                if f' {kw} ' in padded or padded.startswith(f'{kw} ') or padded.endswith(f' {kw}'):
                    cat = cache['by_slug'].get(target_slug)
                    if cat:
                        return cat
                    readable = target_slug.replace('-', ' ')
                    for cat_name_lower, cat_obj in cache['by_name_lower'].items():
                        if readable in cat_name_lower or cat_name_lower in readable:
                            return cat_obj

    # ── Step 3: conservative fallback ────────────────────────────────────
    SKIP_WORDS = {'ring', 'fine', 'art', 'top', 'bag', 'set', 'kit',
                  'toy', 'cat', 'dog', 'pen', 'ram', 'ssd', 'tv'}
    if title_lower:
        for cat_name_lower, cat_obj in cache['by_name_lower'].items():
            name_words = set(cat_name_lower.split())
            if (len(cat_name_lower) >= 10
                    and len(name_words) >= 2
                    and not name_words & SKIP_WORDS
                    and cat_name_lower in title_lower):
                return cat_obj

    return None


def _find_matching_product(title, brand, gtin, asin):
    from .models import Product

    # ১. ইউনিক আইডি (GTIN/ASIN) দিয়ে খোঁজা (এটি সবথেকে নির্ভুল)
    if gtin:
        product = Product.objects.filter(gtin=gtin).first()
        if product: return product

    if asin:
        product = Product.objects.filter(asin=asin).first()
        if product: return product

    # ২. NLP ম্যাচিং (টাইটেল এবং ব্র্যান্ড দিয়ে)
    if title:
        # সার্চ সহজ করার জন্য ব্র্যান্ড দিয়ে ফিল্টার করে ক্যান্ডিডেট বের করি
        brand_query = Q()
        if brand:
            brand_query = Q(brand__icontains=brand.split()[0])
        
        # টাইটেলের প্রথম ২ শব্দ দিয়ে ডাটাবেজে সার্চ করি
        search_words = title.split()[:2]
        title_q = Q()
        for word in search_words:
            if len(word) > 2: title_q |= Q(title__icontains=word)

        candidates = Product.objects.filter(brand_query | title_q).only('id', 'title')

        best_match = None
        best_score = 0
        
        # সিঙ্ক করার সময় আমরা অনেক কড়া (Strict) হবো
        # যাতে Meta Quest 128GB আর 256GB আলাদা আইডি পায়
        REQUIRED_THRESHOLD = 85  # সেভ করার সময় ৮৫% এর নিচে মিললে আমরা ওটাকে নতুন প্রোডাক্ট ধরবো

        for cand in candidates:
            # আমাদের সেই পাওয়ারফুল NLP ফাংশনটি কল করছি
            score = calculate_match_score(title, cand.title)
            
            if score >= REQUIRED_THRESHOLD and score > best_score:
                best_score = score
                best_match = cand

        if best_match:
            return best_match

    # ৩. স্লাগ দিয়ে শেষ চেষ্টা
    slug = slugify(title)[:500]
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
    Universal save helper. ডাটাবেজে সেভ করার আগে প্রাইজ, ইমেজ ও ইউআরএল চেক করবে।
    """
    from .models import (
        Product, ProductListing, Category,
        PriceHistory, ProductImage, ProductSpecification,
    )

    # ── ১. ভ্যালিডেশন গার্ড (Strict Data Quality Check) ──────────────────────
    title = product_data.get('title', '').strip()
    price_val = float(product_data.get('price', 0) or 0)
    image_url = product_data.get('main_image', '').strip()
    external_url = product_data.get('external_url', '').strip()
    external_id = product_data.get('external_id')

    # কোনো একটি গুরুত্বপূর্ণ ফিল্ড মিসিং থাকলে সেভ না করে রিটার্ন করবে
    if not title or title == 'Unknown Product':
        logger.warning(f"Skipped: Missing Title")
        return None, None, False
    
    if price_val <= 0:
        logger.warning(f"Skipped: Invalid Price ({price_val}) for {title[:30]}")
        return None, None, False
    
    if not image_url or len(image_url) < 10: # ইমেজের লিঙ্ক খুব ছোট হলে ওটা ভুল হতে পারে
        logger.warning(f"Skipped: Missing Image for {title[:30]}")
        return None, None, False
        
    if not external_url or not external_id:
        logger.warning(f"Skipped: Missing URL/External ID for {title[:30]}")
        return None, None, False

    # ── ২. কারেন্সি হ্যান্ডলিং ──────────────────────────────────────────────
    raw_currency = product_data.get('currency')
    if not raw_currency and product_data.get('_price_raw'):
        import re
        match = re.search(r'[A-Z]{3}', product_data['_price_raw'].upper())
        if match:
            raw_currency = match.group()
    product_data['currency'] = raw_currency if raw_currency else 'USD'

    # eBay non-USD ফিল্টার (যদি দরকার হয়)
    if not is_valid_usd_price(product_data.get('_price_raw', ''), price_val):
        return None, None, False

    # ── ৩. বাকি সেভিং লজিক (আগে যা ছিল তাই থাকবে) ──────────────────────
    brand = (product_data.get('brand') or '').strip()
    gtin  = (product_data.get('gtin') or '').strip() or None
    asin  = (product_data.get('asin') or '').strip() or None

    if not brand and title:
        brand = ' '.join(title.split()[:2])

    # ক্যাটাগরি রেজল্ভ করা
    if all_categories is None:
        all_categories = list(Category.objects.all())

    if category_slug:
        category = next((c for c in all_categories if c.slug == category_slug), None)
    else:
        category = _resolve_category(
            product_data.get('category_path'), title, _get_category_cache()
        )

    # প্রোডাক্ট এবং লিস্টিং সেভ করা (Atomic Transaction)
    with transaction.atomic():
        # আমাদের সেই নতুন Strict NLP Matcher ব্যবহার করবে _find_matching_product
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