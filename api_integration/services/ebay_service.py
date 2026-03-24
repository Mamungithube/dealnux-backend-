import requests
import re
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

_NON_USD_CURRENCY_CODES = {
    'HUF', 'EUR', 'GBP', 'CAD', 'AUD', 'JPY', 'CNY', 'KRW',
    'INR', 'BRL', 'MXN', 'CHF', 'SEK', 'NOK', 'DKK', 'PLN',
    'CZK', 'HKD', 'SGD', 'NZD', 'ZAR', 'TRY', 'RUB', 'THB',
}


class EbayRapidService:
    """
    Real-Time eBay Data via RapidAPI
    Host: real-time-ebay-data.p.rapidapi.com
    Endpoint: /search_get.php  (Search by URL)
    """

    def __init__(self):
        self.api_key = settings.RAPIDAPI_KEY
        self.host    = 'real-time-ebay-data.p.rapidapi.com'
        self.headers = {
            'x-rapidapi-key':  self.api_key,
            'x-rapidapi-host': self.host,
            'Content-Type':    'application/json',
        }

    def search_products(self, query, limit=10, tld='com'):
        url = f"https://{self.host}/search_get.php"

        # eBay search URL তৈরি করে `url` param হিসেবে পাঠাও
        ebay_search_url = (
            f"https://www.ebay.com/sch/i.html"
            f"?_nkw={query.replace(' ', '+')}"
            f"&_ipg=50"
            f"&LH_BIN=1"
        )

        params = {'url': ebay_search_url}

        try:
            response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=20
            )
            logger.debug(f"eBay status: {response.status_code}")
            logger.debug(f"eBay raw response: {response.text[:800]}")

            if response.status_code == 200:
                data = response.json()

                products = (
                    data.get('body', {}).get('products', [])
                    or data.get('products', [])
                    or data.get('results', [])
                    or data.get('items', [])
                    or []
                )

                logger.info(f"eBay search '{query}': {len(products)} results")
                return products[:limit]

            logger.error(f"eBay error {response.status_code}: {response.text[:300]}")
            return []

        except Exception as e:
            logger.error(f"eBay search exception: {e}")
            return []

    def get_product_details(self, item_url):
        url    = f"https://{self.host}/single_product_info_get"
        params = {'url': item_url}

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=20)
            if response.status_code == 200:
                data = response.json()
                return data.get('body', {}) or data or None
            logger.error(f"eBay details error {response.status_code}: {item_url[:80]}")
            return None

        except Exception as e:
            logger.error(f"eBay details exception: {e}")
            return None

    def _parse_price(self, price_raw):
        if not price_raw:
            return 0.0, 'USD'

        price_str = str(price_raw)
        detected_currency = 'USD'
        for code in _NON_USD_CURRENCY_CODES:
            if code in price_str.upper():
                detected_currency = code
                break

        clean = re.sub(r'[^\d,.\s]', '', price_str).strip()

        if '-' in clean:
            clean = clean.split('-')[0].strip()

        if ',' in clean and '.' in clean:
            if clean.rfind('.') > clean.rfind(','):
                clean = clean.replace(',', '')
            else:
                clean = clean.replace('.', '').replace(',', '.')
        elif ',' in clean:
            clean = clean.replace(' ', '').replace(',', '.')
        else:
            clean = clean.replace(' ', '')

        try:
            return float(clean), detected_currency
        except (ValueError, TypeError):
            return 0.0, detected_currency

    def extract_product_data(self, item):
        item_url      = item.get('url', '')
        item_id_match = re.search(r'/itm/(\d+)', item_url)
        external_id   = item_id_match.group(1) if item_id_match else item_url[:100]

        price_info = item.get('price', {}) or {}
        current    = price_info.get('current', {}) or {}

        raw_from = current.get('from', '0')
        raw_to   = current.get('to', '0')

        price_from, currency_from = self._parse_price(raw_from)
        price_to,   currency_to   = self._parse_price(raw_to)

        price    = price_from if price_from > 0 else price_to
        currency = currency_from if price_from > 0 else currency_to

        api_currency = current.get('currency', currency)

        original_price = None
        prev_price_raw = price_info.get('previousPrice') or price_info.get('trendingPrice')
        if prev_price_raw:
            prev, _ = self._parse_price(str(prev_price_raw))
            if prev > price:
                original_price = prev

        discount_percentage = None
        if original_price and price and original_price > price:
            discount_percentage = round(((original_price - price) / original_price) * 100, 2)

        sub_titles    = item.get('subTitles', []) or []
        condition_raw = ' '.join(sub_titles).lower()
        if 'new' in condition_raw or 'brand new' in condition_raw:
            condition = 'NEW'
        elif 'refurb' in condition_raw or 'renewed' in condition_raw:
            condition = 'REFURBISHED'
        elif 'open box' in condition_raw:
            condition = 'OPEN_BOX'
        elif 'used' in condition_raw or 'pre-owned' in condition_raw:
            condition = 'USED'
        else:
            condition = 'USED'

        shipping_msg  = str(item.get('shippingMessage', '') or '')
        free_shipping = 'free' in shipping_msg.lower()
        shipping_cost = 0 if free_shipping else self._parse_price(shipping_msg)[0]

        seller_info_raw = item.get('sellerInfo', '') or ''
        seller_parts    = str(seller_info_raw).split()
        seller_name     = seller_parts[0] if seller_parts else 'eBay Seller'
        seller_rating   = None
        rating_match    = re.search(r'(\d+(?:\.\d+)?)%', seller_info_raw)
        if rating_match:
            seller_rating = float(rating_match.group(1))

        reviews      = item.get('customerReviews', {}) or {}
        review_count = int(reviews.get('count', 0) or 0)
        bids_count   = int(item.get('bidsCount', 0) or 0)

        title = item.get('title', 'eBay Product').strip()

        return {
            'external_id':         external_id,
            'title':               title or 'eBay Product',
            'description':         ' | '.join(sub_titles) if sub_titles else '',
            'external_url':        item_url,
            'price':               price,
            'currency':            api_currency,
            '_price_raw':          raw_from,
            'original_price':      original_price,
            'discount_percentage': discount_percentage,
            'condition':           condition,
            'quantity':            1,
            'main_image':          item.get('image', ''),
            'additional_images':   [],
            'brand':               '',
            'model_number':        external_id,
            'category_path':       '',
            'gtin':                None,
            'asin':                None,
            'is_available':        True,
            'seller_username':     seller_name,
            'seller_rating':       seller_rating,
            'seller_feedback_count': review_count or bids_count,
            'item_location':       item.get('location', ''),
            'ships_from_country':  '',
            'returns_accepted':    True,
            'return_period_days':  30,
            'shipping_info': {
                'cost':           shipping_cost,
                'currency':       'USD',
                'free_shipping':  free_shipping,
                'estimated_days': 7,
            },
            'specifications': {
                'Store':         'eBay',
                'Item ID':       external_id,
                'Seller':        seller_name,
                'Seller Rating': f"{seller_rating}%" if seller_rating else 'N/A',
                'Reviews':       str(review_count),
                'Bids':          str(bids_count),
                'Condition':     condition,
                'Top Rated':     str(item.get('topRatedSeller', False)),
            },
        }