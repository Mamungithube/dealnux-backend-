import requests
import time
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class HomeDepotService:
    """
    Home Depot Product Lookup via RapidAPI
    Host: home-depot-product-lookup.p.rapidapi.com
    Subscribe: https://rapidapi.com/maple-rope-maple-rope-default/api/home-depot-product-lookup

    ⚠️ এই API শুধু numeric productId দিয়ে কাজ করে — text search সম্ভব না।
    hourly_fixed_category_sync এ text query আসলে এই platform skip হবে।
    """

    def __init__(self):
        self.api_key = settings.RAPIDAPI_KEY
        self.host = 'home-depot-product-lookup.p.rapidapi.com'
        self.headers = {
            'Content-Type': 'application/json',
            'x-rapidapi-host': self.host,
            'x-rapidapi-key': self.api_key
        }

    def search_products(self, query, limit=10):
        """
        ⚠️ এই API তে text search নেই।
        শুধু numeric productId দিলে কাজ করবে।
        Text query দিলে empty list রিটার্ন করবে।
        """
        # Numeric ID হলেই শুধু call করবে
        if not str(query).strip().isdigit():
            logger.warning(
                f"HomeDepot API requires numeric productId, got: '{query}'. Skipping."
            )
            return []

        details = self.get_product_details(str(query).strip())
        return [details] if details else []

    def get_product_details(self, product_id, zip_code="19090"):
        """
        Official flow — ২ step async:
        Step 1: POST /rapidapi-homedepot-product-lookup  → asyncId পাবে
        Step 2: POST /rapidapi-homedepot-product-lookup-results  → actual data
        """
        # ── Step 1: Request initiate ──────────────────────────────────────────
        init_url = f'https://{self.host}/rapidapi-homedepot-product-lookup'
        init_payload = {
            'zip': zip_code,
            'productId': str(product_id)
        }

        try:
            init_res = requests.post(
                init_url,
                json=init_payload,
                headers=self.headers,
                timeout=20
            )
            logger.debug(f"HomeDepot Step1 status: {init_res.status_code}")
            logger.debug(f"HomeDepot Step1 response: {init_res.text[:300]}")

            if init_res.status_code != 200:
                logger.error(f"HomeDepot Step1 Error {init_res.status_code}: {init_res.text[:300]}")
                return None

            async_id = init_res.json().get('asyncId')
            if not async_id:
                logger.error(f"HomeDepot: asyncId not found in response: {init_res.text[:300]}")
                return None

        except Exception as e:
            logger.error(f"HomeDepot Step1 Exception: {e}")
            return None

        # ── Step 2: Poll for result ───────────────────────────────────────────
        result_url = f'https://{self.host}/rapidapi-homedepot-product-lookup-results'
        result_payload = {'asyncId': async_id}

        for attempt in range(4):  # ৪ বার চেক করবে
            time.sleep(3)
            try:
                res = requests.post(
                    result_url,
                    json=result_payload,
                    headers=self.headers,
                    timeout=20
                )
                logger.debug(f"HomeDepot Step2 attempt {attempt+1} status: {res.status_code}")

                if res.status_code == 200:
                    data = res.json()
                    # Data ready কিনা চেক করো
                    if data and data != {'status': 'pending'}:
                        return data
                    logger.debug(f"HomeDepot: data not ready yet (attempt {attempt+1})")

            except Exception as e:
                logger.error(f"HomeDepot Step2 Exception (attempt {attempt+1}): {e}")

        logger.error(f"HomeDepot: data not ready after 4 attempts for productId={product_id}")
        return None

    def extract_product_data(self, item):
        """Home Depot product data কে আমাদের DB format এ convert করে"""

        # Price বের করা
        price = 0.0
        price_raw = (
            item.get('price')
            or item.get('regularPrice')
            or item.get('specialPrice')
        )
        if isinstance(price_raw, dict):
            price = float(price_raw.get('value', 0) or 0)
        elif price_raw:
            try:
                price = float(str(price_raw).replace('$', '').replace(',', '').strip())
            except (ValueError, TypeError):
                price = 0.0

        # Product ID
        product_id = str(
            item.get('itemId')
            or item.get('productId')
            or item.get('id')
            or ''
        )

        # Image
        main_image = (
            item.get('image')
            or item.get('imageUrl')
            or item.get('thumbnail')
            or ''
        )
        if isinstance(main_image, list):
            main_image = main_image[0] if main_image else ''

        brand = (
            item.get('brand')
            or item.get('brandName')
            or item.get('manufacturer')
            or ''
        )

        return {
            'external_id': product_id,
            'title': (
                item.get('name')
                or item.get('title')
                or item.get('productName')
                or 'Home Depot Product'
            ),
            'description': item.get('description') or item.get('longDescription') or '',
            'external_url': item.get('url') or f"https://www.homedepot.com/p/{product_id}",
            'price': price,
            'currency': 'USD',
            'original_price': float(item.get('listPrice', 0) or 0) or None,
            'discount_percentage': None,
            'condition': 'NEW',
            'quantity': int(item.get('availableQuantity') or item.get('quantity') or 1),
            'main_image': main_image,
            'additional_images': [],
            'seller_username': 'Home Depot',
            'seller_rating': float(item.get('rating') or item.get('averageRating') or 0) or None,
            'seller_feedback_count': int(item.get('reviewCount') or item.get('totalReviews') or 0),
            'item_location': 'United States',
            'ships_from_country': 'US',
            'brand': brand,
            'model_number': item.get('modelNumber') or item.get('model') or product_id,
            'category_path': item.get('category') or item.get('categoryName') or '',
            'is_available': bool(
                item.get('isAvailable', True)
                or item.get('availableOnline', True)
                or item.get('available', True)
            ),
            'returns_accepted': True,
            'return_period_days': 90,
            'shipping_info': {
                'cost': 0,
                'currency': 'USD',
                'free_shipping': True,
                'estimated_days': 5
            },
            'specifications': {
                'Brand': brand or 'N/A',
                'Model': item.get('modelNumber') or 'N/A',
                'Store': 'Home Depot',
                'Rating': str(item.get('rating') or 'N/A'),
                'Reviews': str(item.get('reviewCount') or '0'),
            }
        }