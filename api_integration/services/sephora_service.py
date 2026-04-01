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
            # GET রিকোয়েস্টে Content-Type না রাখাই ভালো
        }

    def search_products(self, query, limit=20, page=1):
        url = f"https://{self.host}/search-by-keyword"
        
        # Sephora ড্যাশ ছাড়া স্পেস পছন্দ করে
        clean_query = query.replace('-', ' ').strip()
        
        # প্যারামিটারগুলো স্ক্রিনশট অনুযায়ী একদম নিখুঁত করা হলো
        params = {
            'keyword':     clean_query,
            'pageSize':    int(limit),  # স্ট্রিং না দিয়ে ইন্টিজার দিচ্ছি
            'currentPage': int(page),   # স্ট্রিং না দিয়ে ইন্টিজার দিচ্ছি
            'sortBy':      'BEST_SELLING'
        }

        try:
            # params এর বদলে সরাসরি এন্ডপয়েন্টে রিকোয়েস্ট
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                products = []
                
                # ডাইনামিক প্যাথ ডিটেকশন
                if isinstance(data, dict):
                    products = data.get('data', {}).get('products') or data.get('products') or []
                    
                logger.info(f"Sephora Success: {len(products)} items found for '{clean_query}'")
                return products
            
            # ৫০০ এরর আসলে লগে ডিটেইল দেখা যাবে
            logger.error(f"Sephora API Error {response.status_code}: {response.text}")
            return []

        except Exception as e:
            logger.error(f"Sephora Service Exception: {e}")
            return []

    def extract_product_data(self, item):
        # আইডি এবং টাইটেল
        external_id = str(item.get('productId') or item.get('id') or item.get('skuId') or '')
        title = (item.get('productName') or item.get('displayName') or 'Sephora Product').strip()
        
        # ইমেজ
        main_image = item.get('heroImage') or item.get('image450') or ''
        
        # প্রাইস (রেজেক্স দিয়ে ক্লিন করা)
        price_raw = item.get('currentSku', {}).get('listPrice') or item.get('price') or '0'
        price_val = 0.0
        try:
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
            'condition':      'NEW',
            'seller_username': 'Sephora',
            'shipping_info':  {'cost': 0, 'free_shipping': price_val >= 50},
        }