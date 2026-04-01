import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class WayfairService:
    """
    Wayfair API via RapidAPI
    Host: wayfair.p.rapidapi.com
    Response: data['data']['keyword']['results']['category']['browse']['products']
    """

    def __init__(self):
        self.api_key = settings.RAPIDAPI_KEY
        self.host    = 'wayfair.p.rapidapi.com'
        self.headers = {
            'x-rapidapi-key':  self.api_key,
            'x-rapidapi-host': self.host,
            'Content-Type':    'application/json',
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Search by keyword
    # ─────────────────────────────────────────────────────────────────────────

    def search_products(self, query, limit=20, page=1):
        url    = f"https://{self.host}/products/v2/search"
        params = {
            'keyword':      query.replace('-', ' '),
            'itemsPerPage': str(min(limit, 48)),
            'page':         str(page),
            'domain':       'com',
        }

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                logger.info(f"Wayfair JSON Keys: {list(data.keys())}")

                products = []
                
                d = data.get('data', {})
                if d:
                    # প্যাথ ১: keyword -> results -> products
                    k_res = d.get('keyword') or d.get('keyword_search') or {}
                    products = k_res.get('results', {}).get('products', [])

                    if not products:
                        products = d.get('category', {}).get('browse', {}).get('products', [])
                    
                    if not products:
                        products = d.get('results', {}).get('products', [])

                if not products:
                    def find_products_recursive(obj):
                        if isinstance(obj, dict):
                            if 'products' in obj and isinstance(obj['products'], list):
                                return obj['products']
                            for v in obj.values():
                                found = find_products_recursive(v)
                                if found: return found
                        return None
                    products = find_products_recursive(data) or []

                logger.info(f"Wayfair search result: {len(products)} products extracted")
                return products
            
            logger.error(f"Wayfair API Error: {response.status_code}")
            return []

        except Exception as e:
            logger.error(f"Wayfair Service Exception: {e}")
            return []
    # ─────────────────────────────────────────────────────────────────────────
    # Data Extraction
    # ─────────────────────────────────────────────────────────────────────────

    def extract_product_data(self, item):
        """
        Wayfair API response কে standard DB format এ convert করে।

        Response fields:
        - sku: product ID (e.g. 'W117447079')
        - name: product title
        - url: product URL
        - manufacturer.name: brand
        - pricing.customerPrice.display.value: current price
        - pricing.listPrice.unitPrice.value: original price
        - customer_reviews: {rating_count, average_rating_value}
        - shipping.messages: shipping info
        - inventory.stockStatus: availability
        """

        # ── ID ───────────────────────────────────────────────────────────────
        external_id = str(item.get('sku') or '')

        # ── Price ────────────────────────────────────────────────────────────
        pricing         = item.get('pricing', {}) or {}
        customer_price  = pricing.get('customerPrice', {}) or {}
        display_price   = customer_price.get('display', {}) or {}
        unit_price      = customer_price.get('unitPrice', {}) or {}

        try:
            price = float(
                display_price.get('value')
                or unit_price.get('value')
                or 0
            )
        except (ValueError, TypeError):
            price = 0.0

        # ── Original Price ───────────────────────────────────────────────────
        list_price_info = pricing.get('listPrice', {}) or {}
        list_unit       = list_price_info.get('unitPrice', {}) or {}
        original_price  = None
        try:
            list_val = float(list_unit.get('value') or 0)
            if list_val > price:
                original_price = list_val
        except (ValueError, TypeError):
            pass

        # ── Discount ─────────────────────────────────────────────────────────
        discount_percentage = None
        if original_price and price and original_price > price:
            discount_percentage = round(
                ((original_price - price) / original_price) * 100, 2
            )

        # ── Brand ────────────────────────────────────────────────────────────
        manufacturer = item.get('manufacturer', {}) or {}
        brand        = manufacturer.get('name') or manufacturer.get('shortName') or ''

        # ── Title ────────────────────────────────────────────────────────────
        title = (item.get('name') or 'Wayfair Product').strip()
        if brand and not title.lower().startswith(brand.lower()):
            title = f"{brand} {title}".strip()

        # ── URL ──────────────────────────────────────────────────────────────
        external_url = item.get('url') or f"https://www.wayfair.com/product/{external_id}"

        # ── Image ────────────────────────────────────────────────────────────
        lead_image = item.get('leadImage', {}) or {}
        image_id   = lead_image.get('id', '')
        main_image = (
            f"https://assets.wfcdn.com/im/{image_id}/compr-r85/resize-h800-w800%5Ecompr-r85/{image_id}/image.jpg"
            if image_id else ''
        )

        # ── Rating ───────────────────────────────────────────────────────────
        reviews     = item.get('customer_reviews', {}) or {}
        rating_val  = reviews.get('average_rating_value', 0) or 0
        review_count = int(reviews.get('rating_count', 0) or 0)
        try:
            seller_rating = float(rating_val) * 20  # 5-star → 0-100
        except (ValueError, TypeError):
            seller_rating = None

        # ── Shipping ─────────────────────────────────────────────────────────
        shipping_info = item.get('shipping', {}) or {}
        messages      = shipping_info.get('messages', []) or []
        free_shipping = any(
            'free' in str(m.get('text', '')).lower()
            for m in messages
        )

        # ── Availability ─────────────────────────────────────────────────────
        inventory   = item.get('inventory', {}) or {}
        is_available = inventory.get('stockStatus', '') == 'IN_STOCK'

        # ── Promo ────────────────────────────────────────────────────────────
        promo_text = item.get('promo_text') or ''

        return {
            'external_id':    external_id,
            'title':          title,
            'description':    promo_text,
            'external_url':   external_url,

            'price':               price,
            'currency':            'USD',
            'original_price':      original_price,
            'discount_percentage': discount_percentage,

            'condition':  'NEW',
            'quantity':   int(item.get('quantity', {}).get('minimumOrderQuantity', 1) or 1),
            'main_image': main_image,
            'additional_images': [],
            'brand':         brand,
            'model_number':  external_id,
            'category_path': '',

            'gtin': None,
            'asin': None,

            'is_available': is_available,

            'seller_username':       'Wayfair',
            'seller_rating':         seller_rating,
            'seller_feedback_count': review_count,

            'item_location':      'United States',
            'ships_from_country': 'US',

            'returns_accepted':   True,
            'return_period_days': 30,

            'shipping_info': {
                'cost':           0,
                'currency':       'USD',
                'free_shipping':  free_shipping,
                'estimated_days': 5,
            },

            'specifications': {
                'Store':    'Wayfair',
                'SKU':      external_id,
                'Brand':    brand or 'N/A',
                'Rating':   str(rating_val) if rating_val else 'N/A',
                'Reviews':  str(review_count),
                'In Stock': str(is_available),
                'Promo':    promo_text or 'N/A',
            },
        }