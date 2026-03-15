import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class BestBuyService:
    """
    BestBuy USA API via RapidAPI
    Host: bestbuy-usa.p.rapidapi.com
    Response: data['data']['products'] — list
    """

    def __init__(self):
        self.api_key = settings.RAPIDAPI_KEY
        self.host    = 'bestbuy-usa.p.rapidapi.com'
        self.headers = {
            'x-rapidapi-key':  self.api_key,
            'x-rapidapi-host': self.host,
            'Content-Type':    'application/json',
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Search
    # ─────────────────────────────────────────────────────────────────────────

    def search_products(self, query, limit=10):
        url    = f"https://{self.host}/search"
        params = {'query': query}

        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=20
            )
            logger.debug(f"BestBuy search '{query}': {response.status_code}")

            if response.status_code == 200:
                data     = response.json()
                products = data.get('data', {}).get('products', [])
                logger.info(f"BestBuy search '{query}': {len(products)} results")
                return products[:limit]

            logger.error(f"BestBuy search error {response.status_code}: {response.text[:300]}")
            return []

        except Exception as e:
            logger.error(f"BestBuy search exception: {e}")
            return []

    # ─────────────────────────────────────────────────────────────────────────
    # Data Extraction
    # ─────────────────────────────────────────────────────────────────────────

    def extract_product_data(self, item):
        """
        BestBuy API response কে standard DB format এ convert করে।

        Response fields:
        - skuId: product ID
        - title: product title
        - model: model number
        - imageUrl: main image
        - url: product URL (has duplicate domain bug — fix করা হয়েছে)
        - color: color
        - price.customerPrice: current price
        - price.previousPrice: original price
        - ratings.score: rating (5-star)
        - ratings.count: review count
        - variations: color variants
        """

        # ── ID ───────────────────────────────────────────────────────────────
        external_id = str(item.get('skuId') or '')

        # ── Price ────────────────────────────────────────────────────────────
        price_info = item.get('price', {}) or {}
        try:
            price = float(price_info.get('customerPrice') or 0)
        except (ValueError, TypeError):
            price = 0.0

        # ── Original Price ───────────────────────────────────────────────────
        original_price = None
        try:
            prev = float(price_info.get('previousPrice') or 0)
            if prev > price:
                original_price = prev
        except (ValueError, TypeError):
            pass

        # ── Discount ─────────────────────────────────────────────────────────
        discount_percentage = None
        try:
            disc = price_info.get('discount')
            if disc:
                discount_percentage = float(str(disc).replace('%', '').strip())
        except (ValueError, TypeError):
            pass

        if not discount_percentage and original_price and price and original_price > price:
            discount_percentage = round(
                ((original_price - price) / original_price) * 100, 2
            )

        # ── URL ──────────────────────────────────────────────────────────────
        # API তে URL bug আছে: "https://www.bestbuy.comhttps://www.bestbuy.com/..."
        raw_url      = item.get('url') or ''
        external_url = raw_url.replace(
            'https://www.bestbuy.comhttps://', 'https://'
        )
        if not external_url:
            external_url = f"https://www.bestbuy.com/sku/{external_id}"

        # ── Images ───────────────────────────────────────────────────────────
        main_image = item.get('imageUrl') or ''

        # variations থেকে additional images
        variations         = item.get('variations', []) or []
        additional_images  = []
        for v in variations:
            img = v.get('imageUrl') or ''
            if img and img != main_image:
                additional_images.append(img)
        additional_images = additional_images[:9]

        # ── Rating ───────────────────────────────────────────────────────────
        ratings      = item.get('ratings', {}) or {}
        rating_score = ratings.get('score', 0) or 0
        review_count = int(ratings.get('count', 0) or 0)
        try:
            seller_rating = float(rating_score) * 20  # 5-star → 0-100
        except (ValueError, TypeError):
            seller_rating = None

        # ── Title & Brand ─────────────────────────────────────────────────────
        title = item.get('title') or 'BestBuy Product'
        # Title এর প্রথম শব্দ brand হিসেবে নাও
        brand = title.split(' - ')[0].split(',')[0].strip() if title else ''

        return {
            'external_id':    external_id,
            'title':          title,
            'description':    '',
            'external_url':   external_url,

            'price':               price,
            'currency':            'USD',
            'original_price':      original_price,
            'discount_percentage': discount_percentage,

            'condition':  'NEW',
            'quantity':   1,
            'main_image': main_image,
            'additional_images': additional_images,
            'brand':         brand,
            'model_number':  item.get('model') or external_id,
            'category_path': '',

            'gtin': None,
            'asin': None,

            'is_available': True,

            'seller_username':       'BestBuy',
            'seller_rating':         seller_rating,
            'seller_feedback_count': review_count,

            'item_location':      'United States',
            'ships_from_country': 'US',

            'returns_accepted':   True,
            'return_period_days': 15,

            'shipping_info': {
                'cost':           0,
                'currency':       'USD',
                'free_shipping':  True,
                'estimated_days': 3,
            },

            'specifications': {
                'Store':   'BestBuy',
                'SKU':     external_id,
                'Model':   item.get('model') or 'N/A',
                'Color':   item.get('color') or 'N/A',
                'Rating':  str(rating_score),
                'Reviews': str(review_count),
            },
        }