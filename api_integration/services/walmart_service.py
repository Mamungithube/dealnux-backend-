import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class WalmartService:

    def __init__(self):
        self.api_key = settings.RAPIDAPI_KEY
        self.host    = 'realtime-walmart-data.p.rapidapi.com'
        self.headers = {
            'x-rapidapi-key':  self.api_key,
            'x-rapidapi-host': self.host,
            'Content-Type':    'application/json'
        }

    def search_products(self, query, limit=10, page=1):
        url    = f"https://{self.host}/search"
        params = {"keyword": query, "page": str(page), "sortBy": "best_match"}
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=20)
            if response.status_code == 200:
                return response.json().get('results', [])[:limit]
            logger.error(f"Walmart search error {response.status_code}")
            return []
        except Exception as e:
            logger.error(f"Walmart Search Exception: {e}")
            return []

    def get_product_details(self, item_id):
        """
        There is no separate product-details endpoint in the Walmart API.
        Searching with usItemId will only return an exact match.
        Searching with 'id' (e.g. 745Y6SRSVFSX) does not work.
        """
        results = self.search_products(str(item_id), limit=5)

        if results:
            # Find exact match
            for item in results:
                if (item.get('usItemId') == str(item_id) or
                        item.get('id') == str(item_id)):
                    return item
            # If you don't get exact, give the first one.
            return results[0]

        return None

    def extract_product_data(self, item):
        # ── ID ───────────────────────────────────────────────────────────────
        # usItemId first — this is what will be used to search get_product_details later
        external_id = str(
            item.get('usItemId')
            or item.get('id')
            or item.get('item_id')
            or item.get('product_id')
            or item.get('itemId')
            or ''
        )

        # ── Price ────────────────────────────────────────────────────────────
        # price is often an empty string, fallback to originalPrice
        price_raw = (
            item.get('price')
            or item.get('salePrice')
            or item.get('originalPrice')
            or '0'
        )
        if isinstance(price_raw, dict):
            price = float(price_raw.get('amount') or 0)
        else:
            try:
                price = float(
                    str(price_raw).replace('$', '').replace(',', '').strip()
                )
            except (ValueError, TypeError):
                price = 0.0

        # ── Original Price ───────────────────────────────────────────────────
        original_price = None
        original_raw = item.get('originalPrice')
        if original_raw:
            try:
                original_price = float(
                    str(original_raw).replace('$', '').replace(',', '').strip()
                )
            except (ValueError, TypeError):
                original_price = None

        # price 0 হলে original দিয়ে replace
        if price == 0.0 and original_price:
            price = original_price
            original_price = None

        # ── Discount ─────────────────────────────────────────────────────────
        discount_percentage = None
        savings_raw = item.get('savings')
        if savings_raw:
            try:
                savings = float(
                    str(savings_raw).replace('$', '').replace(',', '').strip()
                )
                base = original_price or price
                if base > 0:
                    discount_percentage = round((savings / base) * 100, 2)
            except (ValueError, TypeError):
                pass

        # ── Rating ───────────────────────────────────────────────────────────
        rating_raw = item.get('rating') or 0
        try:
            seller_rating = float(str(rating_raw)) * 20  # 5-star → 0-100
        except (ValueError, TypeError):
            seller_rating = None

        # ── Availability ─────────────────────────────────────────────────────
        availability = str(item.get('availability', '')).lower()
        is_available = 'in stock' in availability or availability == ''

        return {
            'external_id':         external_id,
            'title':               item.get('name') or item.get('title') or 'Walmart Product',
            'description':         item.get('shortDescription') or item.get('description') or '',
            'external_url':        item.get('canonicalUrl') or item.get('product_page_url') or f"https://www.walmart.com/ip/{external_id}",
            'price':               price,
            'currency':            'USD',
            'original_price':      original_price,
            'discount_percentage': discount_percentage,
            'condition':           'NEW',
            'quantity':            1,
            'main_image':          item.get('image') or item.get('main_image') or '',
            'additional_images':   [],
            'brand':               item.get('brand') or item.get('sellerName') or '',
            'model_number':        external_id,
            'category_path':       item.get('category_path') or '',
            'is_available':        is_available,
            'seller_username':     item.get('sellerName') or 'Walmart',
            'seller_rating':       seller_rating,
            'seller_feedback_count': int(item.get('numberOfReviews') or 0),
            'item_location':       'United States',
            'ships_from_country':  'US',
            'returns_accepted':    True,
            'return_period_days':  90,
            'gtin':                None,
            'asin':                None,
            'shipping_info': {
                'cost':           0,
                'currency':       'USD',
                'free_shipping':  True,
                'estimated_days': 3,
            },
            'specifications': {
                'Store':   'Walmart',
                'Item ID': external_id,
                'Seller':  item.get('sellerName') or 'Walmart',
                'Reviews': str(item.get('numberOfReviews') or 0),
                'Rating':  str(item.get('rating') or 'N/A'),
            },
        }