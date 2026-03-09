import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class ShopifyService:
    """
    Shopify Fast Scraper via RapidAPI
    Host: shopify-fast-scraper.p.rapidapi.com
    """

    def __init__(self):
        self.api_key = settings.RAPIDAPI_KEY
        self.host = 'shopify-fast-scraper.p.rapidapi.com'
        self.headers = {
            'x-rapidapi-host': self.host,
            'x-rapidapi-key': self.api_key
        }
        # Default stores — query দিয়ে filter হবে
        self.default_stores = [
            'https://shop.flipperzero.one',
            'https://row.gymshark.com',
        ]
        self.default_store = self.default_stores[0]

    def search_products(self, query, limit=10):
        """
        GET /store?url=STORE_URL&page=1
        query তে store URL দিলে সেই store থেকে আনবে,
        না দিলে default stores থেকে আনবে এবং title দিয়ে filter করবে।
        """
        store_url = query if query.startswith('http') else None
        stores_to_search = [store_url] if store_url else self.default_stores

        all_products = []

        for store in stores_to_search:
            try:
                url = f'https://{self.host}/store'
                params = {
                    'url': store,
                    'page': '1',
                    'groupByCollection': 'false'
                }
                response = requests.get(url, headers=self.headers, params=params, timeout=20)
                logger.debug(f"Shopify [{store}] status: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()

                    # Response structure handle
                    if isinstance(data, dict):
                        products = (
                            data.get('products')
                            or data.get('data', {}).get('products')
                            or []
                        )
                    elif isinstance(data, list):
                        products = data
                    else:
                        logger.error(f"Shopify unexpected response type: {type(data)}")
                        continue

                    # store URL টা প্রতিটা product এ attach করো
                    for p in products:
                        p['_store_url'] = store

                    all_products.extend(products)

                else:
                    logger.error(f"Shopify Error {response.status_code} [{store}]: {response.text[:300]}")

            except Exception as e:
                logger.error(f"Shopify Exception [{store}]: {e}")

            if len(all_products) >= limit:
                break

        # text query দিয়ে filter
        if not (query or '').startswith('http') and query.strip():
            q = query.lower()
            all_products = [
                p for p in all_products
                if q in (p.get('title') or '').lower()
                or q in str(p.get('product_type') or '').lower()
                or q in str(p.get('tags') or '').lower()
                or q in str(p.get('vendor') or '').lower()
            ]

        return all_products[:limit]

    def extract_product_data(self, item, store_url=None):
        """Shopify product data কে আমাদের DB format এ convert করে"""
        store = (
            store_url
            or item.get('_store_url')
            or self.default_store
        )
        if not store.startswith('http'):
            store = self.default_store

        variants = item.get('variants', [])
        price = 0.0
        original_price = None

        if variants:
            try:
                price = float(variants[0].get('price', 0) or 0)
            except (ValueError, TypeError):
                price = 0.0
            try:
                compare_price = variants[0].get('compare_at_price')
                if compare_price:
                    original_price = float(compare_price)
            except (ValueError, TypeError):
                original_price = None

        discount_percentage = None
        if original_price and price and original_price > price:
            discount_percentage = round(((original_price - price) / original_price) * 100, 2)

        images = item.get('images', [])
        main_image = ''
        if images:
            first = images[0]
            main_image = first.get('src', '') if isinstance(first, dict) else str(first)

        additional_images = []
        for img in images[1:6]:
            src = img.get('src', '') if isinstance(img, dict) else str(img)
            if src:
                additional_images.append(src)

        is_available = any(v.get('available', False) for v in variants) if variants else True
        total_quantity = sum(int(v.get('inventory_quantity') or 0) for v in variants)

        external_id = str(item.get('id', ''))
        handle = item.get('handle', '')
        brand = item.get('vendor', '') or ''

        return {
            'external_id': external_id,
            'title': item.get('title', '') or '',
            'description': item.get('body_html', '') or '',
            'external_url': f"{store}/products/{handle}" if handle else store,
            'price': price,
            'currency': 'USD',
            'original_price': original_price,
            'discount_percentage': discount_percentage,
            'condition': 'NEW',
            'quantity': total_quantity,
            'main_image': main_image,
            'additional_images': additional_images,
            'seller_username': brand,
            'seller_rating': None,
            'seller_feedback_count': 0,
            'item_location': 'Online Store',
            'ships_from_country': 'US',
            'brand': brand,
            'model_number': external_id,
            'category_path': item.get('product_type', '') or '',
            'is_available': is_available,
            'returns_accepted': True,
            'return_period_days': 30,
            'shipping_info': {
                'cost': 0,
                'currency': 'USD',
                'free_shipping': True,
                'estimated_days': 7,
            },
            'specifications': {
                'Product Type': item.get('product_type') or 'N/A',
                'Vendor': brand or 'N/A',
                'Tags': str(item.get('tags') or 'N/A'),
                'Variants Count': str(len(variants)),
                'Store': store,
            },
        }