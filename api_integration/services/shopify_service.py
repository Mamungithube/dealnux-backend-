import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class ShopifyService:
    """
    Shopify Store Scraper via RapidAPI
    Host: shopify-store-scraper.p.rapidapi.com
    Subscribe: https://rapidapi.com/domainarcher/api/shopify-store-scraper
    """

    def __init__(self):
        self.api_key = settings.RAPIDAPI_KEY
        self.host = 'shopify-store-scraper.p.rapidapi.com'  # ✅ Official host
        self.headers = {
            'x-rapidapi-host': self.host,
            'x-rapidapi-key': self.api_key
        }
        self.default_store = 'https://row.gymshark.com'

    def search_products(self, query, limit=10):
        """
        Official endpoint: GET /shopify-products?url=STORE_URL&page=1
        query তে store URL দিলে সেই store থেকে আনবে,
        না দিলে default store থেকে আনবে এবং title দিয়ে filter করবে
        """
        store_url = query if query.startswith('http') else self.default_store

        url = f'https://{self.host}/shopify-products'
        params = {'url': store_url, 'page': '1'}

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=20)
            logger.debug(f"Shopify status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict):
                    products = data.get('products', [])
                elif isinstance(data, list):
                    products = data
                else:
                    logger.error(f"Shopify unexpected response: {type(data)}")
                    return []

                # query টা URL না হলে title দিয়ে client-side filter করো
                if not query.startswith('http') and query.strip():
                    q = query.lower()
                    products = [
                        p for p in products
                        if q in p.get('title', '').lower()
                        or q in str(p.get('product_type', '')).lower()
                        or q in str(p.get('tags', '')).lower()
                    ]

                return products[:limit]

            logger.error(f"Shopify Error {response.status_code}: {response.text[:300]}")
            return []

        except Exception as e:
            logger.error(f"Shopify Exception: {e}")
            return []

    def get_product(self, store_url, handle):
        """
        Official endpoint: GET /product?url=STORE_URL&handle=PRODUCT_HANDLE
        Example: /product?url=https://row.gymshark.com&handle=gymshark-studio-leggings
        """
        url = f'https://{self.host}/product'
        params = {'url': store_url, 'handle': handle}
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=20)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Shopify get_product Exception: {e}")
            return None

    def extract_product_data(self, item, store_url=None):
        """Shopify product data কে আমাদের DB format এ convert করে"""
        store = store_url if store_url and store_url.startswith('http') else self.default_store

        variants = item.get('variants', [])
        price = 0.0
        if variants:
            try:
                price = float(variants[0].get('price', 0) or 0)
            except (ValueError, TypeError):
                price = 0.0

        images = item.get('images', [])
        main_image = images[0].get('src', '') if images else ''
        is_available = any(v.get('available', False) for v in variants) if variants else True
        total_quantity = sum(int(v.get('inventory_quantity', 0) or 0) for v in variants)

        return {
            'external_id': str(item.get('id', '')),
            'title': item.get('title', ''),
            'description': item.get('body_html', '') or '',
            'external_url': f"{store}/products/{item.get('handle', '')}",
            'price': price,
            'currency': 'USD',
            'original_price': None,
            'discount_percentage': None,
            'condition': 'NEW',
            'quantity': total_quantity,
            'main_image': main_image,
            'additional_images': [img.get('src', '') for img in images[1:6]],
            'seller_username': item.get('vendor', '') or '',
            'seller_rating': None,
            'seller_feedback_count': 0,
            'item_location': 'Online Store',
            'ships_from_country': 'US',
            'brand': item.get('vendor', '') or '',
            'model_number': str(item.get('id', '')),
            'category_path': item.get('product_type', ''),
            'is_available': is_available,
            'returns_accepted': True,
            'return_period_days': 30,
            'shipping_info': {
                'cost': 0,
                'currency': 'USD',
                'free_shipping': True,
                'estimated_days': 7
            },
            'specifications': {
                'Product Type': item.get('product_type', 'N/A'),
                'Vendor': item.get('vendor', 'N/A'),
                'Tags': str(item.get('tags', 'N/A')),
                'Variants Count': str(len(variants)),
            }
        }