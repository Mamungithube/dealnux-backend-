import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class AmazonService:
    """
    Real-Time Amazon Data via RapidAPI
    Host: real-time-amazon-data.p.rapidapi.com
    """

    def __init__(self):
        self.api_key = settings.RAPIDAPI_KEY
        self.host = 'real-time-amazon-data.p.rapidapi.com'
        self.headers = {
            'x-rapidapi-host': self.host,
            'x-rapidapi-key': self.api_key
        }

    def search_products(self, query, limit=10):
        """GET /search — Search Amazon products with query.  Returns list of product dicts, or [] on failure.
        """
        url = f"https://{self.host}/search"
        params = {
            'query': query,
            'page': '1',
            'country': 'US',
            'sort_by': 'RELEVANCE',
            'product_condition': 'ALL',
            'is_prime': 'false',
            'deals_and_discounts': 'NONE',
        }
        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=20)
            # print(f"API Response: {response.json()}")
            logger.debug(f"Amazon search status: {response.status_code}")
            if response.status_code == 200:
                data = response.json().get('data', {})
                products = data.get('products', [])
                logger.info(
                    f"Amazon search '{query}': {len(products)} results")
                return products[:limit]
            logger.error(
                f"Amazon search error {response.status_code}: {response.text[:300]}")
            return []
        except Exception as e:
            logger.error(f"Amazon search exception: {e}")
            return []

    def get_product_details(self, asin, country='US'):
        """
        GET /product-details — Gets full product details with ASIN.
        """
        url = f"https://{self.host}/product-details"
        params = {'asin': asin, 'country': country}
        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=20)
            if response.status_code == 200:
                return response.json().get('data', {})
            logger.error(
                f"Amazon product-details error {response.status_code}: {asin}")
            return None
        except Exception as e:
            logger.error(f"Amazon product-details exception ({asin}): {e}")
            return None

    def get_product_offers(self, asin, country='US', limit=10):
        """
        GET /product-offers — ASIN এর seller offers আনে।
        """
        url = f"https://{self.host}/product-offers"
        params = {
            'asin': asin,
            'country': country,
            'limit': str(limit),
            'page': '1',
        }
        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=20)
            if response.status_code == 200:
                return response.json().get('data', {})
            return None
        except Exception as e:
            logger.error(f"Amazon product-offers exception ({asin}): {e}")
            return None

    def extract_product_data(self, item):
        """
        Converts Amazon raw item dict to our DB-compatible standard format.
        Works with both search result items and product-details items.
        """
        # ── Price ────────────────────────────────────────────────────────────
        price_str = (
            item.get('product_price')
            or item.get('price')
            or item.get('buybox_price')
            or '0'
        )
        try:
            price = float(
                str(price_str)
                .replace('$', '')
                .replace(',', '')
                .strip()
            )
        except (ValueError, TypeError):
            price = 0.0

        # ── Original / list price ─────────────────────────────────────────
        original_price_str = (
            item.get('product_original_price')
            or item.get('original_price')
            or item.get('list_price')
        )
        original_price = None
        if original_price_str:
            try:
                original_price = float(
                    str(original_price_str)
                    .replace('$', '')
                    .replace(',', '')
                    .strip()
                )
            except (ValueError, TypeError):
                original_price = None

        # ── If price is 0, replace with original_price ─────────────────────
        if price == 0.0 and original_price:
            price = original_price
            original_price = None

        # ── Discount ──────────────────────────────────────────────────────
        discount_percentage = None
        if original_price and price and original_price > price:
            discount_percentage = round(
                ((original_price - price) / original_price) * 100, 2
            )

        # ── Rating / reviews ─────────────────────────────────────────────
        rating_raw = item.get('product_star_rating') or item.get('rating') or 0
        try:
            seller_rating = float(str(rating_raw).split()[
                                  0]) * 20  # 5-star → 0-100 scale
        except (ValueError, TypeError):
            seller_rating = None

        review_count_raw = item.get(
            'product_num_ratings') or item.get('reviews_count') or 0
        try:
            review_count = int(str(review_count_raw).replace(',', '').strip())
        except (ValueError, TypeError):
            review_count = 0

        # ── Images ───────────────────────────────────────────────────────
        main_image = (
            item.get('product_photo')
            or item.get('main_image')
            or item.get('thumbnail')
            or ''
        )
        additional_images = item.get('product_photos', []) or []
        if isinstance(additional_images, list):
            additional_images = [
                img for img in additional_images if img != main_image][:9]

        # ── ASIN / external ID ───────────────────────────────────────────
        external_id = (
            item.get('asin')
            or item.get('product_asin')
            or item.get('id')
            or ''
        )

        # ── Brand ────────────────────────────────────────────────────────
        brand = (
            item.get('product_brand')
            or ''
        )

        # ── Availability ─────────────────────────────────────────────────
        availability_raw = item.get(
            'product_availability') or item.get('availability') or ''
        is_available = item.get('is_available', True)
        if isinstance(availability_raw, str):
            is_available = 'in stock' in availability_raw.lower() or is_available

        # ── Condition ────────────────────────────────────────────────────
        condition_map = {
            'new': 'NEW',
            'used': 'USED',
            'refurbished': 'REFURBISHED',
            'open box': 'OPEN_BOX',
        }
        condition_raw = str(item.get('condition', 'New')).lower()
        condition = condition_map.get(condition_raw, 'NEW')

        # ── Shipping ─────────────────────────────────────────────────────
        shipping_raw = item.get('delivery') or item.get('shipping') or ''
        free_shipping = 'free' in str(shipping_raw).lower(
        ) or price >= 25  # Amazon free shipping threshold

        return {
            'external_id': external_id,
            'asin': external_id,   # ← Amazon এ external_id মানেই ASIN
            'gtin': (
                item.get('upc')
                or item.get('ean')
                or item.get('gtin')
                or None
            ),
            'title': (
                item.get('product_title')
                or item.get('title')
                or item.get('name')
                or 'Amazon Product'
            ),
            'description': (
                item.get('product_description')
                or item.get('description')
                or item.get('about_product')
                or ''
            ),
            'external_url': (
                item.get('product_url')
                or item.get('url')
                or (f"https://www.amazon.com/dp/{external_id}" if external_id else '')
            ),

            'price': price,
            'currency': 'USD',
            'original_price': original_price,
            'discount_percentage': discount_percentage,
            'condition': condition,
            'quantity': int(item.get('quantity') or item.get('stock_quantity') or 1),
            'main_image': main_image,
            'additional_images': additional_images,
            'seller_username': 'Amazon',
            'seller_rating': seller_rating,
            'seller_feedback_count': review_count,
            'item_location': 'United States',
            'ships_from_country': 'US',
            'brand': brand,
            'has_coupon': bool(
                item.get('has_coupon', False)
                or item.get('coupon_text')
                or item.get('coupon_badge_text')
            ),
            'coupon_text':    item.get('coupon_text') or item.get('coupon_badge_text') or '',
            'deal_badge':     (
                item.get('deal_badge')
                or item.get('deal_text')
                or item.get('product_badge')  # ← এটা যোগ করুন
                or ''
            ),
            'is_best_seller': bool(item.get('is_best_seller', False)),
            'model_number': (
                item.get('model_number')
                or item.get('model')
                or item.get('asin')
                or external_id
            ),
            'category_path': (
                self.get_category_from_details(item.get('asin', ''))
                or item.get('category')
                or item.get('product_category')
                or ''
            ),
            'is_available': bool(is_available),
            'returns_accepted': True,
            'return_period_days': 30,
            'shipping_info': {
                'cost': 0,
                'currency': 'USD',
                'free_shipping': free_shipping,
                'estimated_days': 5 if free_shipping else 7,
            },
            'specifications': {
                'Brand': brand or 'N/A',
                'ASIN': external_id or 'N/A',
                'Rating': str(item.get('product_star_rating') or 'N/A'),
                'Reviews': str(review_count),
                'Store': 'Amazon',
            },
        }
    
    def get_category_from_details(self, asin, country='US'):

        try:
            details = self.get_product_details(asin, country=country)
            if not details:
                return ''
            breadcrumb = details.get('category_path') or []
            if isinstance(breadcrumb, list) and breadcrumb:
                names = [node.get('name', '') for node in breadcrumb if node.get('name')]
                names.reverse() 
                return ' > '.join(names)
            cat = details.get('category')
            if isinstance(cat, dict) and cat.get('name'):
                return cat['name']
            return ''
        except Exception as e:
            logger.error(f"Amazon category fetch failed for {asin}: {e}")
            return ''


    def get_promo_code_details(self, promo_code, country='US'):
        """
        GET /promo-code-details — Get promo code details.
        Response: {promo_title, is_promo_available, discount_percentage, products[]}
        """
        url = f"https://{self.host}/promo-code-details"
        params = {
            'promo_code': promo_code,
            'country': country,
        }
        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=20
            )
            if response.status_code == 200:
                return response.json().get('data', {})
            logger.error(f"Amazon promo error {response.status_code}: {promo_code}")
            return None
        except Exception as e:
            logger.error(f"Amazon promo exception ({promo_code}): {e}")
            return None
    def get_deals(self, limit=20, country='US'):
        """
        GET /deals — Amazon deals with coupon/discount info
        """
        url = f"https://{self.host}/deals-and-offers"
        params = {
            'limit': str(limit),
            'country': country,
            'deal_type': 'COUPON',
        }
        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=20)
            if response.status_code == 200:
                return response.json().get('data', {}).get('deals', [])
            logger.error(f"Amazon deals error {response.status_code}")
            return []
        except Exception as e:
            logger.error(f"Amazon deals exception: {e}")
            return []
