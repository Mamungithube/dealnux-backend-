import requests
import re
import json
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class SephoraService:
    def __init__(self):
        self.api_key = settings.RAPIDAPI_KEY
        self.host    = 'real-time-sephora-api.p.rapidapi.com'
        self.headers = {
            'x-rapidapi-key':  self.api_key,
            'x-rapidapi-host': self.host,
            # User-Agent যোগ করা হয়েছে যাতে ব্রাউজার হিসেবে গণ্য হয়
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        }

    def search_products(self, query, limit=20, page=1):
        url = f"https://{self.host}/search-by-keyword"
        clean_query = query.replace('-', ' ').strip()
        
        params = {
            'keyword':     clean_query,
            'pageSize':    int(limit),
            'currentPage': int(page),
            'sortBy':      'BEST_SELLING'
        }

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            
            # যদি এপিআই সাকসেস না হয়
            if response.status_code != 200:
                logger.error(f"Sephora API HTTP {response.status_code}: {response.text[:200]}")
                return []

            # রেসপন্স টেক্সট চেক করা
            content = response.text.strip()
            if not content:
                logger.error("Sephora API returned an empty response body.")
                return []

            # সেফলি JSON পার্স করা
            try:
                data = response.json()
            except json.JSONDecodeError:
                logger.error(f"Sephora JSON Decode Error. Raw content: {content[:200]}")
                return []

            # ডাটা এক্সট্রাকশন (ডিপ রিকভারি লজিক)
            products = []
            if isinstance(data, dict):
                # প্যাথ ১: data -> products
                products = data.get('data', {}).get('products') or data.get('products') or []
                
                # প্যাথ ২: যদি লিস্টটা অন্য কোথাও লুকিয়ে থাকে (Recursive Search)
                if not products:
                    def find_list(obj):
                        if isinstance(obj, list): return obj
                        if isinstance(obj, dict):
                            for v in obj.values():
                                res = find_list(v)
                                if res: return res
                        return None
                    products = find_list(data) or []

            logger.info(f"Sephora Live Check: Found {len(products)} products for '{clean_query}'")
            return products

        except Exception as e:
            logger.error(f"Sephora Service Critical Error: {e}")
            return []

    def extract_product_data(self, item):
        # আইডি এবং টাইটেল
        external_id = str(item.get('productId') or item.get('id') or item.get('skuId') or '')
        title = (item.get('productName') or item.get('displayName') or 'Sephora Product').strip()
        
        # ইমেজ
        main_image = item.get('heroImage') or item.get('image450') or item.get('image250') or ''
        
        # প্রাইস হ্যান্ডলিং
        price_raw = item.get('currentSku', {}).get('listPrice') or item.get('price') or '0'
        price_val = 0.0
        try:
            # $26.00 থেকে শুধু সংখ্যা বের করা
            nums = re.findall(r'\d+\.?\d*', str(price_raw).replace(',', ''))
            price_val = float(nums[0]) if nums else 0.0
        except: pass

        target_url = item.get('targetUrl') or ''
        return {
            'external_id':    external_id,
            'title':          title,
            'description':    '',
            'external_url':   f"https://www.sephora.com{target_url}" if target_url.startswith('/') else target_url,
            'price':          price_val,
            'currency':       'USD',
            'main_image':     main_image,
            'brand':          item.get('brandName', 'Sephora'),
            'is_available':   True,
            'shipping_info':  {'cost': 0, 'free_shipping': price_val >= 50},
        }