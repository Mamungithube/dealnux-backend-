import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class AmazonService:
    def __init__(self):
        # .env ফাইল থেকে RAPIDAPI_KEY নিবে
        self.api_key = settings.RAPIDAPI_KEY
        self.host = 'real-time-amazon-data.p.rapidapi.com'
        self.headers = {
            'x-rapidapi-host': self.host,
            'x-rapidapi-key': self.api_key
        }

    def search_products(self, query, limit=10):
        """Amazon এ টেক্সট দিয়ে প্রোডাক্ট সার্চ করার জন্য

        Returns a list of product dicts or None if a request error occurred.
        """
        url = f"https://{self.host}/search"
        params = {
            'query': query,
            'page': '1',
            'country': 'US'
        }
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=15)
            if response.status_code != 200:
                logger.error(f"Amazon Search HTTP {response.status_code}: {response.text[:1000]}")
                return None

            data = response.json().get('data', {})
            if not isinstance(data, dict):
                logger.error(f"Amazon Search unexpected data format: {data}")
                return None

            products = data.get('products', [])
            if not isinstance(products, list):
                logger.error(f"Amazon Search products not a list: {products}")
                return None

            return products[:limit]  # লিমিট অনুযায়ী ডাটা রিটার্ন করবে

        except Exception as e:
            logger.error(f"Amazon Search Exception: {e}")
            return None


    def get_product_details(self, asin):
        """নির্দিষ্ট ASIN দিয়ে প্রোডাক্টের বিস্তারিত আনার জন্য"""
        url = f"https://{self.host}/product-details"
        params = {'asin': asin, 'country': 'US'}
        try:
            response = requests.get(url, headers=self.headers, params=params)
            if response.status_code == 200:
                return response.json().get('data', {})
            return None
        except Exception as e:
            logger.error(f"Amazon Product Details Error: {e}")
            return None

    def extract_product_data(self, item):
        """Amazon এর JSON ডাটাকে আমাদের ডাটাবেজ মডেলে কনভার্ট করা"""
        price_str = item.get('product_price')
        # price অনেক সময় স্ট্রিং হিসেবে "$29.99" আসতে পারে, সেটা ক্লিন করার জন্য
        try:
            price = float(str(price_str).replace('$', '').replace(',', '').strip()) if price_str else 0.0
        except ValueError:
            price = 0.0

        return {
            'external_id': item.get('asin', ''),
            'title': item.get('product_title', ''),
            'description': item.get('product_description', ''),
            'external_url': item.get('product_url', ''),
            'price': price,
            'currency': 'USD', # Amazon US ডাটা
            'condition': 'NEW',
            'main_image': item.get('product_photo', ''),
            'brand': item.get('product_brand', ''), # অনেক সময় ডাইরেক্ট ব্রান্ড থাকে না
            'is_available': item.get('is_available', True),
        }