import requests
import re
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class SephoraService:
    """
    Real-Time Sephora API via RapidAPI
    Host: real-time-sephora-api.p.rapidapi.com
    Endpoint: /search-by-keyword
    """

    def __init__(self):
        self.api_key = settings.RAPIDAPI_KEY
        self.host    = 'real-time-sephora-api.p.rapidapi.com'
        self.headers = {
            'x-rapidapi-key':  self.api_key,
            'x-rapidapi-host': self.host,
            'Content-Type':    'application/json',
        }

    def search_products(self, query, limit=20, page=1):
        """
        Keyword search লজিক - যা আপনার স্ক্রিনশটের মতো ডাটা নিয়ে আসবে।
        """
        url = f"https://{self.host}/search-by-keyword"
        
        params = {
            'keyword':      query.replace('-', ' '),
            'pageSize':     str(min(limit, 60)), 
            'currentPage':  str(page),
            'sortBy':       'BEST_SELLING',   
        }

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # ── স্মার্ট ডাটা রিকভারি (ডিপ পার্সিং) ──
                # Real-Time এপিআই ডাটা কখনও 'products' আবার কখনও 'data' এর নিচে পাঠায়
                products = []
                
                if isinstance(data, dict):
                    # ১. সরাসরি প্যাথ চেক
                    products = data.get('products') or data.get('data', {}).get('products') or []
                    
                    # ২. যদি না পায়, তবে রিকার্সিভলি 'products' কি-টি খুঁজবে
                    if not products:
                        def find_list_recursive(obj, target_key):
                            if isinstance(obj, dict):
                                if target_key in obj and isinstance(obj[target_key], list):
                                    return obj[target_key]
                                for v in obj.values():
                                    found = find_list_recursive(v, target_key)
                                    if found: return found
                            return None
                        products = find_list_recursive(data, 'products') or []

                logger.info(f"Sephora Search: {len(products)} products found")
                return products[:limit]
            
            logger.error(f"Sephora API Error {response.status_code}: {response.text[:200]}")
            return []

        except Exception as e:
            logger.error(f"Sephora Service Exception: {e}")
            return []

    def extract_product_data(self, item):
        """
        নতুন এপিআই এর ডাইনামিক ডাটা ফরম্যাট অনুযায়ী এক্সট্রাকশন।
        """
        # আইডি এবং টাইটেল
        external_id = str(item.get('productId') or item.get('id') or item.get('skuId') or '')
        title = (item.get('productName') or item.get('displayName') or 'Sephora Product').strip()
        
        # ব্র্যান্ড
        brand = item.get('brandName') or item.get('brand', {}).get('displayName') or 'Sephora'
        
        # ইমেজ (নতুন এপিআই অনুযায়ী হিরো ইমেজ প্যাথ)
        main_image = item.get('heroImage') or item.get('image450') or item.get('image250') or ''
        if not main_image and 'currentSku' in item:
            main_image = item['currentSku'].get('skuImages', {}).get('image450', '')

        # প্রাইস পার্সিং ($26.00 বা 26 হিসেবে আসতে পারে)
        price_val = 0
        sku_data = item.get('currentSku', {}) or {}
        price_raw = sku_data.get('listPrice') or item.get('price') or '0'
        
        try:
            if isinstance(price_raw, str):
                # কারেন্সি সিম্বল এবং কমা সরিয়ে শুধু সংখ্যা নেওয়া
                price_match = re.search(r'\d+\.?\d*', price_raw.replace(',', ''))
                price_val = float(price_match.group()) if price_match else 0.0
            else:
                price_val = float(price_raw)
        except:
            price_val = 0.0

        # ইউআরএল জেনারেশন
        target_url = item.get('targetUrl') or item.get('url', '')
        external_url = f"https://www.sephora.com{target_url}" if target_url and target_url.startswith('/') else target_url

        return {
            'external_id':    external_id,
            'title':          title,
            'description':    item.get('shortDescription', ''),
            'external_url':   external_url or f"https://www.sephora.com/product/{external_id}",
            'price':          price_val,
            'currency':       'USD',
            'main_image':     main_image,
            'brand':          brand,
            'is_available':   True,
            'condition':      'NEW',
            'seller_username': 'Sephora',
            'shipping_info':  {'cost': 0, 'free_shipping': price_val >= 50},
            'specifications': {
                'Rating': str(item.get('rating', 'N/A')),
                'Reviews': str(item.get('reviews', '0')),
                'Store': 'Sephora'
            }
        }