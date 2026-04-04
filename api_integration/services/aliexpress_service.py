import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class AliExpressService:
    """
    AliExpress True API via RapidAPI
    Host: aliexpress-true-api.p.rapidapi.com
    Search: /api/v3/products → data['products']['product'] list
    Details: /api/v3/product-info → list[0]
    """

    def __init__(self):
        self.api_key = settings.RAPIDAPI_KEY
        self.host    = 'aliexpress-true-api.p.rapidapi.com'
        self.headers = {
            'x-rapidapi-key':  self.api_key,
            'x-rapidapi-host': self.host,
            'Content-Type':    'application/json',
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Search
    # ─────────────────────────────────────────────────────────────────────────

    def search_products(self, query, limit=10, page=1):
        """  Search AliExpress products by keyword. Response: data['products']['product'] — list  """

        url    = f"https://{self.host}/api/v3/products"
        params = {
            'keywords':        query,
            'target_currency': 'USD',
            'target_language': 'EN',
            'ship_to_country': 'US',
            'page_no':         str(page),
            'page_size':       str(min(limit, 50)),
        }

        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=20
            )
            logger.debug(f"AliExpress search '{query}': {response.status_code}")

            if response.status_code == 200:
                data     = response.json()
                products = data.get('products', {}).get('product', [])
                logger.info(f"AliExpress search '{query}': {len(products)} results")
                return products[:limit]

            logger.error(f"AliExpress search error {response.status_code}: {response.text[:300]}")
            return []

        except Exception as e:
            logger.error(f"AliExpress search exception: {e}")
            return []

    # ─────────────────────────────────────────────────────────────────────────
    # Product Details
    # ─────────────────────────────────────────────────────────────────────────

    def get_product_details(self, product_id):
        """ Get AliExpress product details using product_id."""
        url    = f"https://{self.host}/api/v3/product-info"
        params = {
            'product_id':      str(product_id),
            'target_currency': 'USD',
            'target_language': 'EN',
            'ship_to_country': 'US',
        }

        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=20
            )
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and data:
                    return data[0]
                if isinstance(data, dict):
                    return data
                    
            logger.error(f"AliExpress details error {response.status_code}: {product_id}")
            return None

        except Exception as e:
            logger.error(f"AliExpress details exception ({product_id}): {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # Data Extraction
    # ─────────────────────────────────────────────────────────────────────────

    def extract_product_data(self, item):
        """
        AliExpress API response কে standard DB format এ convert করে।

        Response fields:
        - product_id: ID
        - product_title: title
        - target_sale_price: current price (USD)
        - target_original_price: original price (USD)
        - discount: '3%'
        - product_main_image_url: main image
        - product_small_image_urls.string: additional images
        - product_detail_url: product URL
        - shop_name: seller
        - first_level_category_name: category
        - second_level_category_name: sub-category
        - lastest_volume: sold count
        - evaluate_rate: rating %
        """

        # ── ID ───────────────────────────────────────────────────────────────
        external_id = str(item.get('product_id') or item.get('sku_id') or '')

        # ── Price ────────────────────────────────────────────────────────────
        price_raw = (
            item.get('target_sale_price')
            or item.get('target_app_sale_price')
            or item.get('sale_price')
            or '0'
        )
        try:
            price = float(str(price_raw).replace(',', '').strip())
        except (ValueError, TypeError):
            price = 0.0

        # ── Original Price ───────────────────────────────────────────────────
        orig_raw = (
            item.get('target_original_price')
            or item.get('original_price')
        )
        original_price = None
        if orig_raw:
            try:
                orig = float(str(orig_raw).replace(',', '').strip())
                if orig > price:
                    original_price = orig
            except (ValueError, TypeError):
                pass

        # ── Discount ─────────────────────────────────────────────────────────
        discount_percentage = None
        discount_raw = item.get('discount', '0%')
        try:
            discount_percentage = float(str(discount_raw).replace('%', '').strip())
            if discount_percentage == 0:
                discount_percentage = None
        except (ValueError, TypeError):
            discount_percentage = None

        # ── Images ───────────────────────────────────────────────────────────
        main_image = item.get('product_main_image_url') or ''
        small_images = item.get('product_small_image_urls', {}) or {}
        additional_images = small_images.get('string', []) or []
        if isinstance(additional_images, list):
            additional_images = [
                img for img in additional_images if img != main_image
            ][:9]

        # ── URL ──────────────────────────────────────────────────────────────
        external_url = (
            item.get('product_detail_url')
            or item.get('promotion_link')
            or f"https://www.aliexpress.com/item/{external_id}.html"
        )

        # ── Category ─────────────────────────────────────────────────────────
        category_path = (
            item.get('first_level_category_name', '')
            + (' > ' + item.get('second_level_category_name', '')
               if item.get('second_level_category_name') else '')
        )

        # ── Rating ───────────────────────────────────────────────────────────
        evaluate_rate = item.get('evaluate_rate', '0%')
        try:
            seller_rating = float(str(evaluate_rate).replace('%', '').strip())
        except (ValueError, TypeError):
            seller_rating = None

        # ── Sales volume ─────────────────────────────────────────────────────
        try:
            review_count = int(item.get('lastest_volume') or 0)
        except (ValueError, TypeError):
            review_count = 0

        return {
            'external_id':    external_id,
            'title':          item.get('product_title') or 'AliExpress Product',
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
            'brand':         item.get('shop_name') or '',
            'model_number':  external_id,
            'category_path': category_path,

            'gtin': None,
            'asin': None,

            'is_available': True,

            'seller_username':       item.get('shop_name') or 'AliExpress',
            'seller_rating':         seller_rating,
            'seller_feedback_count': review_count,

            'item_location':      'China',
            'ships_from_country': 'CN',

            'returns_accepted':   True,
            'return_period_days': 15,

            'shipping_info': {
                'cost':           0,
                'currency':       'USD',
                'free_shipping':  True,
                'estimated_days': 15,
            },

            'specifications': {
                'Store':       'AliExpress',
                'Product ID':  external_id,
                'Shop':        item.get('shop_name') or 'N/A',
                'Category':    item.get('first_level_category_name') or 'N/A',
                'Sub-Category': item.get('second_level_category_name') or 'N/A',
                'Discount':    str(item.get('discount') or '0%'),
                'Sold':        str(review_count),
                'Rating':      str(evaluate_rate),
            },
        }