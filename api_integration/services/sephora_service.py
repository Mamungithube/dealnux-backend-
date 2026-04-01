import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class SephoraService:
    """
    Real-Time Sephora API via RapidAPI
    Host: real-time-sephora-api.p.rapidapi.com
    """

    def __init__(self):
        self.api_key = settings.RAPIDAPI_KEY
        self.host    = 'real-time-sephora-api.p.rapidapi.com'
        self.headers = {
            'x-rapidapi-key':  self.api_key,
            'x-rapidapi-host': self.host,
            'Content-Type':    'application/json',
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Search by keyword
    # ─────────────────────────────────────────────────────────────────────────

    def search_products(self, query, limit=10, page=1):
        url    = f"https://{self.host}/search-by-keyword"
        params = {
            'keyword':     query,
            'sortBy':      'BEST_SELLING',
            'currentPage': str(page),
            'pageSize':    str(min(limit, 60)),
        }
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=20)
            logger.debug(f"Sephora search '{query}': {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    logger.info(f"Sephora search '{query}': {len(data)} results")
                    return data[:limit]
                if isinstance(data, dict):
                    products = data.get('products', []) or data.get('data', []) or []
                    return products[:limit]

            logger.error(f"Sephora search error {response.status_code}: {response.text[:300]}")
            return []

        except Exception as e:
            logger.error(f"Sephora search exception: {e}")
            return []

    # ─────────────────────────────────────────────────────────────────────────
    # Search by category
    # ─────────────────────────────────────────────────────────────────────────

    def search_by_category(self, category_id, limit=10, page=1):
        """
        Search Sephora products by categoryId.
        """
        url    = f"https://{self.host}/search-by-category"
        params = {
            'categoryId':  category_id,
            'sortBy':      'BEST_SELLING',
            'currentPage': str(page),
            'pageSize':    str(min(limit, 60)),
        }

        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=20
            )
            if response.status_code == 200:
                data = response.json()
                return (
                    data.get('products', [])
                    or data.get('data', {}).get('products', [])
                    or []
                )[:limit]

            logger.error(f"Sephora category error {response.status_code}: {category_id}")
            return []

        except Exception as e:
            logger.error(f"Sephora category exception: {e}")
            return []

    # ─────────────────────────────────────────────────────────────────────────
    # Search by brand
    # ─────────────────────────────────────────────────────────────────────────

    def search_by_brand(self, brand_name, limit=10, page=1):
        """
        brand name দিয়ে Sephora products search করো।
        """
        url    = f"https://{self.host}/search-by-brand"
        params = {
            'brandName':   brand_name,
            'sortBy':      'BEST_SELLING',
            'currentPage': str(page),
            'pageSize':    str(min(limit, 60)),
        }

        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=20
            )
            if response.status_code == 200:
                data = response.json()
                return (
                    data.get('products', [])
                    or data.get('data', {}).get('products', [])
                    or []
                )[:limit]

            logger.error(f"Sephora brand error {response.status_code}: {brand_name}")
            return []

        except Exception as e:
            logger.error(f"Sephora brand exception: {e}")
            return []

    # ─────────────────────────────────────────────────────────────────────────
    # Product Details
    # ─────────────────────────────────────────────────────────────────────────

    def get_product_details(self, product_id):
        """
        productId দিয়ে full details আনো।
        """
        url    = f"https://{self.host}/product-details"
        params = {'productId': product_id}

        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=20
            )
            if response.status_code == 200:
                data = response.json()
                return (
                    data.get('product', {})
                    or data.get('data', {})
                    or data
                    or None
                )
            logger.error(f"Sephora details error {response.status_code}: {product_id}")
            return None

        except Exception as e:
            logger.error(f"Sephora details exception ({product_id}): {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # Data Extraction
    # ─────────────────────────────────────────────────────────────────────────

    def extract_product_data(self, item):
        """
        Sephora API response কে আমাদের standard DB format এ convert করে।
        """

        # ── ID ───────────────────────────────────────────────────────────────
        external_id = str(
            item.get('productId')
            or item.get('id')
            or item.get('skuId')
            or ''
        )

        # ── Price ────────────────────────────────────────────────────────────
        sku       = item.get('currentSku', {}) or {}
        price_raw = sku.get('listPrice') or item.get('listPrice') or item.get('price') or '0'

        try:
            price_str = str(price_raw).replace('$', '').replace(',', '').strip()

            # Range হলে যেমন "$39.00 - $59.00" — সবচেয়ে কম দাম নাও
            if ' - ' in price_str:
                price_str = price_str.split(' - ')[0].strip()

            price = float(price_str)
        except (ValueError, TypeError):
            price = 0.0

        # ── Sale Price ───────────────────────────────────────────────────────
        sale_price_raw = (
            item.get('currentSku', {}).get('salePrice')
            or item.get('salePrice')
        )
        original_price = None
        if sale_price_raw:
            try:
                sale_price = float(
                    str(sale_price_raw)
                    .replace('$', '')
                    .replace(',', '')
                    .strip()
                )
                if sale_price < price:
                    original_price = price
                    price          = sale_price
            except (ValueError, TypeError):
                pass

        # ── Discount ─────────────────────────────────────────────────────────
        discount_percentage = None
        if original_price and price and original_price > price:
            discount_percentage = round(
                ((original_price - price) / original_price) * 100, 2
            )

        # ── Rating ───────────────────────────────────────────────────────────
        rating_raw = (
            item.get('rating')
            or item.get('reviews', {}).get('rating')
            or 0
        )
        try:
            seller_rating = float(str(rating_raw)) * 20  # 5-star → 0-100
        except (ValueError, TypeError):
            seller_rating = None

        # ── Review count ─────────────────────────────────────────────────────
        review_raw = (
            item.get('reviews')
            or item.get('numReviews')
            or item.get('reviewCount')
            or 0
        )
        if isinstance(review_raw, dict):
            review_raw = review_raw.get('total', 0) or 0
        try:
            review_count = int(str(review_raw).replace(',', '').strip())
        except (ValueError, TypeError):
            review_count = 0

        # ── Images ───────────────────────────────────────────────────────────
        main_image = (
            item.get('heroImage')
            or item.get('image')
            or item.get('imageUrl')
            or item.get('currentSku', {}).get('skuImages', {}).get('image450')
            or ''
        )
        additional_images = item.get('images', []) or []
        if isinstance(additional_images, list):
            additional_images = [
                img for img in additional_images if img != main_image
            ][:9]

        # ── Brand ────────────────────────────────────────────────────────────
        brand = (
            item.get('brandName')
            or item.get('brand', {}).get('displayName')
            or item.get('brand')
            or ''
        )
        if isinstance(brand, dict):
            brand = brand.get('displayName', '')

        # ── Category ─────────────────────────────────────────────────────────
        category_path = (
            item.get('parentCategory', {}).get('displayName')
            or item.get('category')
            or 'Beauty & Makeup'
        )
        if isinstance(category_path, dict):
            category_path = category_path.get('displayName', 'Beauty & Makeup')

        # ── URL ──────────────────────────────────────────────────────────────
        url_path   = item.get('targetUrl') or item.get('url') or ''
        external_url = (
            f"https://www.sephora.com{url_path}"
            if url_path and not url_path.startswith('http')
            else url_path
        )
        if not external_url and external_id:
            external_url = f"https://www.sephora.com/product/{external_id}"

        # ── Availability ─────────────────────────────────────────────────────
        is_available = item.get('isAvailable', True)
        if isinstance(is_available, str):
            is_available = is_available.lower() != 'false'

        return {
            # ── Core ─────────────────────────────────────────────────────────
            'external_id':  external_id,
            'title': (
                item.get('displayName')
                or item.get('productName')
                or item.get('name')
                or 'Sephora Product'
            ),
            'description': (
                item.get('longDescription')
                or item.get('shortDescription')
                or item.get('description')
                or ''
            ),
            'external_url': external_url,

            # ── Price ────────────────────────────────────────────────────────
            'price':               price,
            'currency':            'USD',
            'original_price':      original_price,
            'discount_percentage': discount_percentage,

            # ── Product Info ─────────────────────────────────────────────────
            'condition':     'NEW',
            'quantity':      int(item.get('quantity') or 1),
            'main_image':    main_image,
            'additional_images': additional_images,
            'brand':         brand,
            'model_number':  external_id,
            'category_path': category_path,

            # ── Identifiers ──────────────────────────────────────────────────
            'gtin': item.get('upc') or item.get('ean') or None,
            'asin': None,

            # ── Availability ─────────────────────────────────────────────────
            'is_available': bool(is_available),

            # ── Seller ───────────────────────────────────────────────────────
            'seller_username':       'Sephora',
            'seller_rating':         seller_rating,
            'seller_feedback_count': review_count,

            # ── Location ─────────────────────────────────────────────────────
            'item_location':      'United States',
            'ships_from_country': 'US',

            # ── Returns ──────────────────────────────────────────────────────
            'returns_accepted':   True,
            'return_period_days': 60,

            # ── Shipping ─────────────────────────────────────────────────────
            'shipping_info': {
                'cost':           0,
                'currency':       'USD',
                'free_shipping':  price >= 50,  # Sephora free shipping on $50+
                'estimated_days': 5,
            },

            # ── Specifications ────────────────────────────────────────────────
            'specifications': {
                'Store':     'Sephora',
                'Product ID': external_id,
                'Brand':     brand or 'N/A',
                'Rating':    str(item.get('rating') or 'N/A'),
                'Reviews':   str(review_count),
                'Category':  category_path,
            },
        }