import re
import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class TargetService:
    """
    Target.com Shopping API via RapidAPI
    Host: target-com-shopping.p.rapidapi.com
    Endpoint: /search
    Response: data['data'] — list of product dicts
    """

    def __init__(self):
        self.api_key  = settings.RAPIDAPI_KEY
        self.host     = 'target-com-shopping.p.rapidapi.com'
        self.headers  = {
            'x-rapidapi-key':  self.api_key,
            'x-rapidapi-host': self.host,
        }
        self.store_id = '1122'  # Default Target store ID

    # ─────────────────────────────────────────────────────────────────────────
    # Search
    # ─────────────────────────────────────────────────────────────────────────

    def search_products(self, query, limit=10, offset=0):
        """
        Keyword : Search for target product.
        Response: data['data'] — flat list of product dicts
        """
        url    = f"https://{self.host}/search"
        params = {
            'keyword': query,
            'count':   str(min(limit, 24)),
            'storeId': self.store_id,
            'offset':  str(offset),
        }

        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=20
            )
            logger.debug(f"Target search '{query}': {response.status_code}")

            if response.status_code == 200:
                data = response.json()

                if data.get('status') == 'success':
                    products = data.get('data', []) or []
                else:
                    # fallback — পুরনো nested structure
                    products = (
                        data.get('data', {})
                            .get('search', {})
                            .get('products', [])
                    )

                logger.info(f"Target search '{query}': {len(products)} results")
                return products[:limit]

            logger.error(
                f"Target search error {response.status_code}: {response.text[:300]}"
            )
            return []

        except Exception as e:
            logger.error(f"Target search exception: {e}")
            return []

    # ─────────────────────────────────────────────────────────────────────────
    # Product Details (optional — this API does not have a separate details endpoint)
    # ─────────────────────────────────────────────────────────────────────────

    def get_product_details(self, tcin):
        """
        tcin দিয়ে search করে প্রথম result return করে।
        নতুন API তে dedicated details endpoint নেই।
        """
        items = self.search_products(tcin, limit=1)
        if items:
            return items[0]
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Data Extraction — New flat response structure
    # ─────────────────────────────────────────────────────────────────────────

    def extract_product_data(self, item):
        """
        নতুন Target API response কে standard DB format এ convert করে।

        New response structure:
        - item['title']           : product title
        - item['brand']           : brand name
        - item['product_url']     : full Target URL
        - item['primary_image']   : main image URL
        - item['all_images']      : list of image URLs
        - item['price']['current']: current price (string, e.g. "$999.99" or "Price Varies")
        - item['price']['original']: original price or null
        - item['bullet_descriptions']: list of HTML bullet strings
        - item['soft_bullets']    : list of feature strings
        - item['rating']          : float or null
        - item['reviews_count']   : int or null
        - item['tcin']            : product ID
        """

        # ── ID ───────────────────────────────────────────────────────────────
        external_id = str(item.get('tcin') or '')

        # Fallback to extract TCIN from product_url
        if not external_id:
            url_str = item.get('product_url', '')
            match   = re.search(r'/A-(\d+)', url_str)
            if match:
                external_id = match.group(1)

        # ── Title ────────────────────────────────────────────────────────────
        title = item.get('title') or 'Target Product'

        # ── Brand ────────────────────────────────────────────────────────────
        brand = item.get('brand') or ''

        # ── Price ────────────────────────────────────────────────────────────
        price_info  = item.get('price', {}) or {}
        price_raw   = price_info.get('current') or ''
        price       = self._parse_price(price_raw)
        orig_raw    = self._parse_price(price_info.get('original'))

        # "Price Varies" — carrier/contract phone, price unknown
        is_price_varies = isinstance(price_raw, str) and 'varies' in price_raw.lower()

        original_price      = None
        discount_percentage = None

        if orig_raw and price and orig_raw > price:
            original_price      = orig_raw
            discount_percentage = round(
                ((original_price - price) / original_price) * 100, 2
            )

        # ── Images ───────────────────────────────────────────────────────────
        main_image = item.get('primary_image') or ''
        alt_images = item.get('all_images') or []
        # Remove primary_image from alt_images (to avoid duplicates)
        alt_images = [img for img in alt_images if img != main_image]

        # ── URL ──────────────────────────────────────────────────────────────
        external_url = item.get('product_url') or ''
        if not external_url and external_id:
            external_url = f"https://www.target.com/p/-/A-{external_id}"

        # ── Rating & Reviews ─────────────────────────────────────────────────
        # The rating field can be a dict: {'average': 4.35, 'count': 2389}
        rating_raw   = item.get('rating')
        review_count = item.get('reviews_count') or 0

        if isinstance(rating_raw, dict):
            rating_val   = rating_raw.get('average') or rating_raw.get('rating') or 0
            review_count = rating_raw.get('count') or review_count
        else:
            rating_val = rating_raw or 0

        try:
            seller_rating = float(rating_val) * 20 if rating_val else None 
        except (ValueError, TypeError):
            seller_rating = None

        try:
            review_count = int(review_count)
        except (ValueError, TypeError):
            review_count = 0

        # ── Description — from bullet_descriptions ───────────────────────────
        bullets     = item.get('bullet_descriptions') or []
        description = ' '.join(
            re.sub(r'<[^>]+>', '', b) for b in bullets[:5]
        ) if bullets else ''

        # If there is no bullet, try soft_bullets.
        if not description:
            soft = item.get('soft_bullets') or []
            description = ' '.join(soft[:3])

        # ── Category path ────────────────────────────────────────────────────
        category_path = item.get('category', '') or 'General Merchandise'

        # ── Specifications — key-value parse from bullet_descriptions ────────
        specs = {'Store': 'Target', 'Brand': brand or 'N/A'}
        if external_id:
            specs['TCIN'] = external_id
        if rating_val:
            try:
                specs['Rating'] = str(round(float(rating_val), 2))
            except (ValueError, TypeError):
                pass
        specs['Reviews'] = str(review_count)

        for bullet in bullets[:10]:
            clean = re.sub(r'<[^>]+>', '', bullet)
            if ':' in clean:
                k, _, v = clean.partition(':')
                specs[k.strip()] = v.strip()

        return {
            'external_id':    external_id,
            'title':          title,
            'description':    description,
            'external_url':   external_url,

            'price':               price,
            'currency':            'USD',
            'original_price':      original_price,
            'discount_percentage': discount_percentage,

            'condition':  'NEW',
            'quantity':   1,
            'main_image': main_image,
            'additional_images': alt_images[:9],
            'brand':         brand,
            'model_number':  external_id,
            'category_path': category_path,

            'gtin': None,
            'asin': None,

            'is_available': not is_price_varies, 

            'seller_username':       'Target',
            'seller_rating':         seller_rating,
            'seller_feedback_count': review_count,

            'item_location':      'United States',
            'ships_from_country': 'US',

            'returns_accepted':   True,
            'return_period_days': 90, 

            'shipping_info': {
                'cost':           0,
                'currency':       'USD',
                'free_shipping':  (price >= 35) if (price and not is_price_varies) else False,
                'estimated_days': 5,
            },

            'specifications': specs,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_price(raw) -> float:

        if raw is None:
            return 0.0
        if isinstance(raw, (int, float)):
            return float(raw)
        # Put numbers + dot from string
        cleaned = re.sub(r'[^\d.]', '', str(raw))
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0