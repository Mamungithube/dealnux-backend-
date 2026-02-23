import requests
from django.conf import settings
from django.core.cache import cache


class ClickBankService:

    def __init__(self):
        self.api_key = getattr(settings, 'CLICKBANK_API_KEY', '')
        self.dev_key = getattr(settings, 'CLICKBANK_DEV_KEY', 'DEV-123456789012345678901234567890123456')
        self.api_base_url = "https://api.clickbank.com/rest/1.3"

    def search_products(self, query='', category='', limit=10):
        """ClickBank public marketplace XML feed"""
        
        url = "https://accounts.clickbank.com/mkplSearchResult.htm"
        params = {
            'resultsPerPage': limit,
            'keywords': query,
            'sortField': 'GRAVITY'
        }
        if category:
            params['cat'] = category
        
        response = requests.get(url, params=params, timeout=30)
        print(f"Status: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type')}")
        print(f"Response: {response.text[:1000]}")
        
        return []

    def _parse_api_response(self, data):
        """Parse real ClickBank API JSON response"""
        products = []

        # ClickBank API response structure
        items = data.get('products', {}).get('product', [])

        # Single item হলে list এ convert
        if isinstance(items, dict):
            items = [items]

        for item in items:
            site = item.get('site', '')
            products.append({
                'site': site,
                'title': item.get('title', ''),
                'description': item.get('description', ''),
                'price': float(item.get('activateCharge', {}).get('amount', 0)),
                'commission': float(item.get('commission', {}).get('value', 0)),
                'gravity': float(item.get('popularity', {}).get('gravity', 0)),
                'vendor': item.get('vendor', site),
                'category': item.get('category', {}).get('name', ''),
                'url': f"https://hop.clickbank.net/?vendor={site}",
                'image_url': item.get('imageUrl', ''),
                'initial_sale': float(item.get('commission', {}).get('initialDollarSale', 0)),
                'rebuild': item.get('popularity', {}).get('rebill', 0),
            })

        return products

    def get_product_details(self, product_id):
        """Single product details"""
        cache_key = f'clickbank_product_{product_id}'
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            headers = {
                'Authorization': self.api_key,
                'developerApiKey': self.dev_key,
                'Accept': 'application/json'
            }

            response = requests.get(
                f"{self.api_base_url}/marketplace/search",
                headers=headers,
                params={'keywords': product_id, 'resultsPerPage': 1},
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                products = self._parse_api_response(data)
                if products:
                    cache.set(cache_key, products[0], 3600)
                    return products[0]

        except Exception as e:
            print(f"ClickBank Details Exception: {e}")

        return None

    def extract_product_data(self, item_data):
        return {
            'external_id': item_data.get('site', ''),
            'title': item_data.get('title', ''),
            'description': item_data.get('description', ''),
            'external_url': item_data.get('url', ''),
            'price': float(item_data.get('price', 0)),
            'currency': 'USD',
            'original_price': None,
            'discount_percentage': None,
            'condition': 'NEW',
            'quantity': 999999,
            'main_image': item_data.get('image_url', ''),
            'additional_images': [],
            'seller_username': item_data.get('vendor', ''),
            'seller_rating': float(item_data.get('gravity', 0)),
            'seller_feedback_count': 0,
            'item_location': 'Digital Product',
            'ships_from_country': 'US',
            'shipping_info': {
                'cost': 0,
                'currency': 'USD',
                'free_shipping': True,
                'estimated_days': 0
            },
            'returns_accepted': False,
            'return_period_days': 0,
            'specifications': {
                'Product Type': 'Digital Product',
                'Category': item_data.get('category', 'N/A'),
                'Gravity': str(item_data.get('gravity', 'N/A')),
                'Commission': f"${item_data.get('commission', 0)}",
                'Initial $/Sale': f"${item_data.get('initial_sale', 0)}",
                'Vendor': item_data.get('vendor', 'N/A'),
            },
            'brand': item_data.get('vendor', ''),
            'model_number': item_data.get('site', ''),
            'category_path': item_data.get('category', ''),
            'is_available': True,
        }

    def get_categories(self):
        return [
            {'code': 'ebusiness', 'name': 'E-Business & E-Marketing'},
            {'code': 'health', 'name': 'Health & Fitness'},
            {'code': 'money', 'name': 'Money & Employment'},
            {'code': 'software', 'name': 'Software & Services'},
            {'code': 'self-help', 'name': 'Self-Help'},
        ]

    # Mock data — শুধু fallback হিসেবে রাখুন
    def search_mock_products(self, query='', limit=10):
        mock_products = [
            {
                'site': 'prodname1',
                'title': 'Digital Marketing Mastery Course',
                'description': 'Complete guide to digital marketing',
                'price': 47.00, 'commission': 35.00, 'gravity': 156.5,
                'vendor': 'DigiMarketPro', 'category': 'E-Business & E-Marketing',
                'url': 'https://hop.clickbank.net/?vendor=prodname1',
                'image_url': '', 'initial_sale': 35.00, 'rebuild': 75
            },
            {
                'site': 'fitpro2023',
                'title': 'Ultimate Weight Loss System',
                'description': 'Proven weight loss program',
                'price': 37.00, 'commission': 28.00, 'gravity': 234.8,
                'vendor': 'HealthFitPro', 'category': 'Health & Fitness',
                'url': 'https://hop.clickbank.net/?vendor=fitpro2023',
                'image_url': '', 'initial_sale': 28.00, 'rebuild': 60
            },
        ]
        return mock_products[:limit]