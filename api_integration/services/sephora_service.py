import requests
import re
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
            'Content-Type':    'application/json',
        }

    def search_products(self, query, limit=20, page=1):
        url = f"https://{self.host}/search-by-keyword"
        
        # কুয়েরি ক্লিন করা
        clean_query = query.replace('-', ' ').strip()
        
        params = {
            'keyword':     clean_query,
            'pageSize':    str(min(limit, 60)),
            'currentPage': str(page),
            # sortBy সরিয়ে দিয়েছি কারণ অনেক সময় এটি ০ রেজাল্ট দেয়
        }

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # লগে কি (Keys) গুলো দেখি কী আসছে
                logger.info(f"Sephora API Raw Keys: {list(data.keys()) if isinstance(data, dict) else 'List'}")

                products = []
                if isinstance(data, dict):
                    # প্যাথ ১: data -> products
                    products = data.get('data', {}).get('products', [])
                    # প্যাথ ২: সরাসরি products
                    if not products:
                        products = data.get('products', [])
                    # প্যাথ ৩: যদি কোনো 'list' থাকে
                    if not products:
                        for k, v in data.items():
                            if isinstance(v, list):
                                products = v
                                break
                
                logger.info(f"Sephora Search Result for '{clean_query}': {len(products)} items found")
                return products
            
            logger.error(f"Sephora API Status {response.status_code}: {response.text}")
            return []

        except Exception as e:
            logger.error(f"Sephora Service Error: {e}")
            return []

    def extract_product_data(self, item):
        # আইডি এবং টাইটেল
        external_id = str(item.get('productId') or item.get('id') or item.get('skuId') or '')
        title = (item.get('productName') or item.get('displayName') or 'Sephora Product').strip()
        
        # ব্র্যান্ড
        brand = item.get('brandName') or 'Sephora'
        
        # ইমেজ
        main_image = item.get('heroImage') or item.get('image450') or item.get('image250') or ''
        
        # প্রাইস পার্সিং
        price_val = 0
        sku_data = item.get('currentSku', {}) or {}
        price_raw = sku_data.get('listPrice') or item.get('price') or '0'
        
        try:
            # স্ট্রিং থেকে সংখ্যা বের করা (e.g. "$26.00" -> 26.0)
            nums = re.findall(r'\d+\.?\d*', str(price_raw).replace(',', ''))
            price_val = float(nums[0]) if nums else 0.0
        except:
            price_val = 0.0

        target_url = item.get('targetUrl') or ''
        return {
            'external_id':    external_id,
            'title':          title,
            'description':    '',
            'external_url':   f"https://www.sephora.com{target_url}" if target_url.startswith('/') else target_url,
            'price':          price_val,
            'currency':       'USD',
            'main_image':     main_image,
            'brand':          brand,
            'is_available':   True,
            'shipping_info':  {'cost': 0, 'free_shipping': True},
        }