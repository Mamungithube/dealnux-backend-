import requests
import re
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class EbayRapidService:
    """
    Real-Time eBay Data via RapidAPI
    Host: real-time-ebay-data.p.rapidapi.com
    Endpoints: /search_more, /single_product_info_get
    """

    def __init__(self):
        self.api_key = settings.RAPIDAPI_KEY
        self.host    = 'real-time-ebay-data.p.rapidapi.com'
        self.headers = {
            'x-rapidapi-key':  self.api_key,
            'x-rapidapi-host': self.host,
            'Content-Type':    'application/json',
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Search
    # ─────────────────────────────────────────────────────────────────────────

    def search_products(self, query, limit=10, tld='com'):
        """
        keyword দিয়ে eBay products search করো।
        Response: data['body']['products'] — list of product dicts
        """
        url    = f"https://{self.host}/search_more"
        params = {
            'query': query,
            'tld':   tld,
        }

        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=20
            )
            logger.debug(f"eBay Rapid search '{query}': {response.status_code}")

            if response.status_code == 200:
                data     = response.json()
                products = data.get('body', {}).get('products', [])
                logger.info(f"eBay Rapid search '{query}': {len(products)} results")
                return products[:limit]

            logger.error(f"eBay Rapid search error {response.status_code}: {response.text[:300]}")
            return []

        except Exception as e:
            logger.error(f"eBay Rapid search exception: {e}")
            return []

    # ─────────────────────────────────────────────────────────────────────────
    # Product Details
    # ─────────────────────────────────────────────────────────────────────────

    def get_product_details(self, item_url):
        """
        eBay item URL দিয়ে full product details আনো।
        """
        url    = f"https://{self.host}/single_product_info_get"
        params = {'url': item_url}

        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=20
            )
            if response.status_code == 200:
                data = response.json()
                return data.get('body', {}) or data or None
            logger.error(f"eBay Rapid details error {response.status_code}: {item_url[:80]}")
            return None

        except Exception as e:
            logger.error(f"eBay Rapid details exception: {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # Price Parsing Helper
    # ─────────────────────────────────────────────────────────────────────────

    def _parse_price(self, price_raw):
        """
        Price string থেকে float বের করো।
        Handles: '$131.99', '131 911,26 HUF', '131.99', range 'from-to'
        """
        if not price_raw:
            return 0.0

        price_str = str(price_raw)

        # $ বা currency symbol বাদ দাও
        price_str = re.sub(r'[^\d,.\s]', '', price_str).strip()

        # range হলে (e.g. "131.99 - 199.99") প্রথম নাও
        if '-' in price_str:
            price_str = price_str.split('-')[0].strip()

        # European format (131 911,26) → 131911.26
        # শেষ separator কোনটা?
        if ',' in price_str and '.' in price_str:
            # "1,234.56" → US format
            if price_str.rfind('.') > price_str.rfind(','):
                price_str = price_str.replace(',', '')
            # "1.234,56" → EU format
            else:
                price_str = price_str.replace('.', '').replace(',', '.')
        elif ',' in price_str:
            # "131 911,26" → EU decimal
            price_str = price_str.replace(' ', '').replace(',', '.')
        else:
            price_str = price_str.replace(' ', '')

        try:
            return float(price_str)
        except (ValueError, TypeError):
            return 0.0

    # ─────────────────────────────────────────────────────────────────────────
    # Data Extraction
    # ─────────────────────────────────────────────────────────────────────────

    def extract_product_data(self, item):
        """
        eBay Rapid API response কে standard DB format এ convert করে।

        Response fields:
        - title: product title
        - price.current.from / price.current.to: price range
        - price.previousPrice: original price
        - image: main image URL
        - url: product URL (eBay item URL — also used as external_id)
        - shippingMessage: shipping info
        - sellerInfo: seller details
        - location: item location
        - topRatedSeller: bool
        - customerReviews: {review, count, link}
        """

        # ── ID — URL থেকে item ID বের করো ────────────────────────────────────
        item_url   = item.get('url', '')
        item_id_match = re.search(r'/itm/(\d+)', item_url)
        external_id = item_id_match.group(1) if item_id_match else item_url[:100]

        # ── Price ────────────────────────────────────────────────────────────
        price_info   = item.get('price', {}) or {}
        current      = price_info.get('current', {}) or {}
        price_from   = self._parse_price(current.get('from', '0'))
        price_to     = self._parse_price(current.get('to', '0'))
        price        = price_from if price_from > 0 else price_to

        # ── Original Price ───────────────────────────────────────────────────
        original_price = None
        prev_price_raw = price_info.get('previousPrice') or price_info.get('trendingPrice')
        if prev_price_raw:
            prev = self._parse_price(str(prev_price_raw))
            if prev > price:
                original_price = prev

        # ── Discount ─────────────────────────────────────────────────────────
        discount_percentage = None
        if original_price and price and original_price > price:
            discount_percentage = round(((original_price - price) / original_price) * 100, 2)

        # ── Condition ────────────────────────────────────────────────────────
        sub_titles  = item.get('subTitles', []) or []
        condition_raw = ' '.join(sub_titles).lower()
        if 'new' in condition_raw or 'brand new' in condition_raw:
            condition = 'NEW'
        elif 'refurb' in condition_raw or 'renewed' in condition_raw or 'felújított' in condition_raw:
            condition = 'REFURBISHED'
        elif 'used' in condition_raw or 'pre-owned' in condition_raw:
            condition = 'USED'
        elif 'open box' in condition_raw:
            condition = 'OPEN_BOX'
        else:
            condition = 'USED'  # eBay default assumption

        # ── Shipping ─────────────────────────────────────────────────────────
        shipping_msg  = str(item.get('shippingMessage', '') or '')
        free_shipping = 'free' in shipping_msg.lower() or 'ingyenes' in shipping_msg.lower()
        shipping_cost = 0 if free_shipping else self._parse_price(shipping_msg)

        # ── Seller ───────────────────────────────────────────────────────────
        seller_info_raw = item.get('sellerInfo', '') or ''
        # Format: "bidallies 99% pozitív (365,6K)"
        seller_parts   = str(seller_info_raw).split()
        seller_name    = seller_parts[0] if seller_parts else 'eBay Seller'
        seller_rating  = None
        rating_match   = re.search(r'(\d+(?:\.\d+)?)%', seller_info_raw)
        if rating_match:
            seller_rating = float(rating_match.group(1))

        # ── Reviews ──────────────────────────────────────────────────────────
        reviews        = item.get('customerReviews', {}) or {}
        review_count   = int(reviews.get('count', 0) or 0)

        # ── Bids ─────────────────────────────────────────────────────────────
        bids_count = int(item.get('bidsCount', 0) or 0)

        # ── Title clean ──────────────────────────────────────────────────────
        title = item.get('title', 'eBay Product')
        # "Új ablakban vagy lapon nyílik meg" junk text বাদ দাও
        title = re.sub(r'Új ablakban.*', '', title).strip()
        title = re.sub(r'Opens in a new.*', '', title, flags=re.IGNORECASE).strip()

        return {
            'external_id':    external_id,
            'title':          title or 'eBay Product',
            'description':    ' | '.join(sub_titles) if sub_titles else '',
            'external_url':   item_url,

            'price':               price,
            'currency':            'USD',
            'original_price':      original_price,
            'discount_percentage': discount_percentage,

            'condition':  condition,
            'quantity':   1,
            'main_image': item.get('image', ''),
            'additional_images': [],
            'brand':         '',
            'model_number':  external_id,
            'category_path': '',

            'gtin': None,
            'asin': None,

            'is_available': True,

            'seller_username':       seller_name,
            'seller_rating':         seller_rating,
            'seller_feedback_count': review_count or bids_count,

            'item_location':      item.get('location', ''),
            'ships_from_country': '',

            'returns_accepted':   True,
            'return_period_days': 30,

            'shipping_info': {
                'cost':           shipping_cost,
                'currency':       'USD',
                'free_shipping':  free_shipping,
                'estimated_days': 7,
            },

            'specifications': {
                'Store':        'eBay',
                'Item ID':      external_id,
                'Seller':       seller_name,
                'Seller Rating': f"{seller_rating}%" if seller_rating else 'N/A',
                'Reviews':      str(review_count),
                'Bids':         str(bids_count),
                'Condition':    condition,
                'Top Rated':    str(item.get('topRatedSeller', False)),
            },
        }