import requests
from django.conf import settings

class WalmartService:
    def __init__(self):
        self.client_id = settings.WALMART_CLIENT_ID
        self.client_secret = settings.WALMART_CLIENT_SECRET

    def search_products(self, query, limit=10):
        # Walmart Affiliate API URL (Client এর দেওয়া URL বসান)
        url = "https://developer.api.walmart.com/api-proxy/service/affil/product/v2/search"
        headers = {"WM_SEC.KEY_VERSION": "1", "WM_CONSUMER.ID": self.client_id} # Auth লজিক ক্লায়েন্টের ডক অনুযায়ী দিবেন
        params = {"query": query, "numItems": limit}
        try:
            response = requests.get(url, headers=headers, params=params)
            return response.json().get('items',[]) if response.status_code == 200 else []
        except:
            return[]

    def extract_product_data(self, item):
        return {
            'external_id': str(item.get('itemId', '')),
            'title': item.get('name', ''),
            'description': item.get('shortDescription', ''),
            'external_url': item.get('productUrl', ''),
            'price': item.get('salePrice', 0),
            'currency': 'USD',
            'condition': 'NEW',
            'main_image': item.get('thumbnailImage', ''),
            'brand': item.get('brandName', ''),
            'is_available': item.get('availableOnline', True),
        }