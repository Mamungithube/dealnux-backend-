import requests
import re
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class TargetService:
    """
    Target.com Shopping API via RapidAPI
    Host: target-com-shopping-api.p.rapidapi.com
    Response: data['data']['search']['products'] — list of product dicts
    """

    def __init__(self):
        self.api_key  = settings.RAPIDAPI_KEY
        self.host     = 'target-com-shopping-api.p.rapidapi.com'
        self.headers  = {
            'x-rapidapi-key':  self.api_key,
            'x-rapidapi-host': self.host,
            'Content-Type':    'application/json',
        }
        self.store_id = '1122'  # Default Target store ID

    # ─────────────────────────────────────────────────────────────────────────
    # Search
    # ─────────────────────────────────────────────────────────────────────────

    def search_products(self, query, limit=10, offset=0):
        """
        keyword দিয়ে Target products search করো।
        Response: data['data']['search']['products']
        """
        url    = f"https://{self.host}/product_search"
        params = {
            'store_id': self.store_id,
            'keyword':  query,
            'count':    str(min(limit, 24)),
            'offset':   str(offset),
        }

        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=20
            )
            logger.debug(f"Target search '{query}': {response.status_code}")

            if response.status_code == 200:
                data     = response.json()
                products = (
                    data.get('data', {})
                        .get('search', {})
                        .get('products', [])
                )
                logger.info(f"Target search '{query}': {len(products)} results")
                return products[:limit]

            logger.error(f"Target search error {response.status_code}: {response.text[:300]}")
            return []

        except Exception as e:
            logger.error(f"Target search exception: {e}")
            return []

    # ─────────────────────────────────────────────────────────────────────────
    # Product Details
    # ─────────────────────────────────────────────────────────────────────────

    def get_product_details(self, tcin):
        """
        tcin দিয়ে Target product details আনো।
        """
        url    = f"https://{self.host}/product_details"
        params = {
            'tcin':     tcin,
            'store_id': self.store_id,
        }

        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=20
            )
            if response.status_code == 200:
                data = response.json()
                return data.get('data', {}) or None
            logger.error(f"Target details error {response.status_code}: {tcin}")
            return None

        except Exception as e:
            logger.error(f"Target details exception ({tcin}): {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # Data Extraction
    # ─────────────────────────────────────────────────────────────────────────

    def extract_product_data(self, item):
        """
        Target API response কে standard DB format এ convert করে।

        Response structure:
        - item.tcin: product ID
        - item.parent.item.product_description.title: title
        - item.parent.item.primary_brand.name: brand
        - item.parent.item.enrichment.images.primary_image_url: image
        - item.parent.item.enrichment.buy_url: product URL
        - item.price.current_retail: price
        - item.price.reg_retail: original price
        - item.parent.ratings_and_reviews: reviews
        """

        parent       = item.get('parent', {}) or {}
        parent_item  = parent.get('item', {}) or {}
        enrichment   = parent_item.get('enrichment', {}) or {}
        desc         = parent_item.get('product_description', {}) or {}
        brand_info   = parent_item.get('primary_brand', {}) or {}
        images_info  = enrichment.get('images', {}) or {}
        rar          = parent.get('ratings_and_reviews', {}) or {}

        # ── ID ───────────────────────────────────────────────────────────────
        external_id = str(item.get('tcin') or parent.get('tcin') or '')

        # ── Title ────────────────────────────────────────────────────────────
        title = (
            desc.get('title')
            or item.get('item', {}).get('product_description', {}).get('title')
            or 'Target Product'
        )

        # ── Price ────────────────────────────────────────────────────────────
        price_info = item.get('price', {}) or {}
        price_raw  = (
            price_info.get('current_retail')
            or price_info.get('reg_retail')
            or 0
        )
        try:
            price = float(price_raw)
        except (ValueError, TypeError):
            price = 0.0

        # ── Original Price ───────────────────────────────────────────────────
        original_price = None
        reg_retail     = price_info.get('reg_retail')
        if reg_retail:
            try:
                reg = float(reg_retail)
                if reg > price:
                    original_price = reg
            except (ValueError, TypeError):
                pass

        # ── Discount ─────────────────────────────────────────────────────────
        discount_percentage = None
        if original_price and price and original_price > price:
            discount_percentage = round(
                ((original_price - price) / original_price) * 100, 2
            )

        # ── Brand ────────────────────────────────────────────────────────────
        brand = brand_info.get('name', '')

        # ── Images ───────────────────────────────────────────────────────────
        main_image = images_info.get('primary_image_url', '')
        alt_images = images_info.get('alternate_image_urls', []) or []

        # ── URL ──────────────────────────────────────────────────────────────
        buy_url      = enrichment.get('buy_url', '')
        external_url = (
            f"https://www.target.com{buy_url}"
            if buy_url and not buy_url.startswith('http')
            else buy_url
        )
        if not external_url and external_id:
            external_url = f"https://www.target.com/p/-/A-{external_id}"

        # ── Rating & Reviews ─────────────────────────────────────────────────
        rating_stats  = rar.get('statistics', {}) or {}
        rating_val    = rating_stats.get('rating', {}).get('primary', 0) or 0
        review_count  = rating_stats.get('review_count', 0) or 0
        try:
            seller_rating = float(rating_val) * 20  # 5-star → 0-100
        except (ValueError, TypeError):
            seller_rating = None
        try:
            review_count = int(review_count)
        except (ValueError, TypeError):
            review_count = 0

        # ── Category ─────────────────────────────────────────────────────────
        category_info = item.get('category', {}) or {}
        category_id   = category_info.get('category_id', '')
        merch_class   = parent_item.get('merchandise_classification', {}) or {}
        category_path = merch_class.get('class_description', '') or 'General Merchandise'

        # ── Description ──────────────────────────────────────────────────────
        bullets     = desc.get('bullet_descriptions', []) or []
        description = ' '.join(
            re.sub(r'<[^>]+>', '', b) for b in bullets[:5]
        ) if bullets else ''

        # ── Promotions ───────────────────────────────────────────────────────
        promotions    = item.get('promotions', []) or []
        promo_text    = promotions[0].get('promotion_message', '') if promotions else ''

        # ── Fulfillment ──────────────────────────────────────────────────────
        fulfillment   = item.get('fulfillment', {}) or {}
        is_available  = True  # Target products are generally available

        return {
            'external_id':    external_id,
            'title':          title,
            'description':    description,
            'external_url':   external_url,

            'price':               price,
            'currency':            'USD',
            'original_price':      original_price,
            'discount_percentage': discount_percentage,

            'condition':  'NEW',
            'quantity':   1,
            'main_image': main_image,
            'additional_images': alt_images[:9],
            'brand':         brand,
            'model_number':  external_id,
            'category_path': category_path,

            'gtin': None,
            'asin': None,

            'is_available': is_available,

            'seller_username':       'Target',
            'seller_rating':         seller_rating,
            'seller_feedback_count': review_count,

            'item_location':      'United States',
            'ships_from_country': 'US',

            'returns_accepted':   True,
            'return_period_days': 90,  # Target এর 90-day return policy

            'shipping_info': {
                'cost':           0,
                'currency':       'USD',
                'free_shipping':  price >= 35,  # Target free shipping on $35+
                'estimated_days': 5,
            },

            'specifications': {
                'Store':       'Target',
                'TCIN':        external_id,
                'Brand':       brand or 'N/A',
                'Rating':      str(rating_val) if rating_val else 'N/A',
                'Reviews':     str(review_count),
                'Category ID': category_id,
                'Promotion':   promo_text or 'N/A',
            },
        }