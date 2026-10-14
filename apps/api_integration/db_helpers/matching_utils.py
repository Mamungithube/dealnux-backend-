import re
import logging
from django.utils.text import slugify
from django.db.models import Q
from ..product_matcher import calculate_match_score

logger = logging.getLogger(__name__)


_BRAND_NOISE = [
    'restored', 'renewed', 'refurbished', 'pre-owned', 'used',
    'new listing', 'new', 'sealed', 'oem', 'generic', 'unbranded',
    'lot of', 'pack of', 'set of', '2 pack', '3 pack', '4 pack',
    'lot', 'bundle', 'combo', 'kit', 'original', 'latest',
]


_NOT_A_BRAND = {
    'racing', 'simulator', 'cockpit', 'gaming', 'desktop', 'laptop',
    'wireless', 'bluetooth', 'portable', 'digital', 'smart', 'mini',
    'professional', 'premium', 'luxury', 'deluxe', 'heavy', 'duty',
    'latest', 'dual', 'triple', 'original', 'genuine', 'official',
    'replacement', 'compatible', 'universal', 'adjustable', 'folding',
    'upgraded', 'improved', 'advanced', 'automatic', 'manual',
}


def _clean_brand(brand: str, title: str) -> str:
    if not brand:
        brand = ''

    brand_lower = brand.lower().strip()

    cleaned = brand_lower
    for noise in _BRAND_NOISE:
        cleaned = re.sub(r'\b' + re.escape(noise) + r'\b', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    cleaned_words = cleaned.split()
    valid_words = [w for w in cleaned_words if w.lower() not in _NOT_A_BRAND and len(w) > 1]

    if valid_words and len(' '.join(valid_words)) > 2:
        title_words = title.split()
        brand_candidate = ' '.join(valid_words)
        for i in range(1, min(4, len(title_words) + 1)):
            prefix = ' '.join(title_words[:i]).lower()
            if brand_candidate in prefix or prefix in brand_candidate:
                return ' '.join(title_words[:i])
        return brand_candidate.title()

    if title:
        skip = {
            'new', 'the', 'a', 'an', 'for', 'restored', 'renewed',
            'refurbished', 'sealed', 'lot', 'pack', 'set', 'bundle',
            'original', 'latest', 'racing', 'simulator', 'gaming',
            'desktop', 'laptop', 'wireless', 'bluetooth', 'portable',
            'digital', 'smart', 'professional', 'premium', 'upgraded',
        }
        words = title.split()
        brand_words = []
        for w in words[:5]:
            clean_w = re.sub(r'[^\w®™]', '', w)
            if not clean_w or clean_w.lower() in skip or len(clean_w) < 2:
                break 
            if clean_w[0].isupper() or clean_w[0].isdigit():
                brand_words.append(w)
            else:
                break
            if len(brand_words) == 3:
                break
        return ' '.join(brand_words) if brand_words else ''

    return ''


def _find_matching_product(title, brand, gtin, asin):
    from ..models import Product

    if gtin:
        product = Product.objects.filter(gtin=gtin).first()
        if product:
            return product

    if asin:
        product = Product.objects.filter(asin=asin).first()
        if product:
            return product

    if title:
        brand_query = Q()
        if brand:
            brand_query = Q(brand__icontains=brand.split()[0])

        # Search the database using the first 2 words of the title.
        search_words = [w for w in title.split()[:4] if len(w) > 2]
        title_q = Q()
        for word in search_words:
            if len(word) > 2:
                title_q |= Q(title__icontains=word)

        candidates = Product.objects.filter(
            brand_query | title_q).only('id', 'title')

        best_match = None
        best_score = 0

        REQUIRED_THRESHOLD = 72

        for cand in candidates:
            score = calculate_match_score(title, cand.title)

            if score >= REQUIRED_THRESHOLD and score > best_score:
                best_score = score
                best_match = cand

        if best_match:
            return best_match

    slug = slugify(title)[:500]
    return Product.objects.filter(slug=slug).first()


# ─────────────────────────────────────────────────────────────────────────────
# eBay currency validation — exclude non-USD listings
# ─────────────────────────────────────────────────────────────────────────────

# These currency codes may appear in eBay international responses
_NON_USD_INDICATORS = [
    'HUF', 'EUR', 'GBP', 'CAD', 'AUD', 'JPY', 'CNY', 'KRW',
    'INR', 'BRL', 'MXN', 'CHF', 'SEK', 'NOK', 'DKK', 'PLN',
    'CZK', 'HKD', 'SGD', 'NZD', 'ZAR', 'TRY', 'RUB', 'THB',
]

MAX_REASONABLE_PRICE = 5000.0


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
        logger.warning(
            f"Price anomaly detected: {price_float} — skipping listing")
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Rating helper — normalize to 5-star scale
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_rating(raw_rating):
    """
    Services store seller_rating in different scales:
      - Amazon/Walmart: 0–5 star  → keep as-is
      - Wayfair/Sephora/Target/BestBuy: 0–100 (multiplied by 20) → divide by 20
    If value > 5, assume 0–100 scale and convert.
    Returns float rounded to 1 decimal, or 0.0 on failure.
    """
    try:
        r = float(raw_rating)
        if r <= 0:
            return 0.0
        return round(r / 20, 1) if r > 5 else round(r, 1)
    except (ValueError, TypeError):
        return 0.0
