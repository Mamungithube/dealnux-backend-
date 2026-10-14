import logging
import re
from django.db import transaction
from django.utils.text import slugify

from .matching_utils import (
    _clean_brand,
    _find_matching_product,
    is_valid_usd_price,
    _normalize_rating,
)
from .category_resolver import (
    _get_category_cache,
    _resolve_category,
)

logger = logging.getLogger(__name__)


def save_generic_product_to_db(product_data, platform, query=None, category_slug=None, all_categories=None):
    """Universal save helper. Will check price, image and URL before saving to database."""
    from ..models import (
        Product, ProductListing, Category,
        PriceHistory, ProductImage, ProductSpecification,
    )

    title = product_data.get('title', '').strip()
    price_val = float(product_data.get('price', 0) or 0)
    image_url = product_data.get('main_image', '').strip()
    external_url = product_data.get('external_url', '').strip()
    external_id = product_data.get('external_id')

    if not title or title == 'Unknown Product':
        logger.warning(f"Skipped: Missing Title")
        return None, None, False

    if price_val <= 0:
        logger.warning(
            f"Skipped: Invalid Price ({price_val}) for {title[:30]}")
        return None, None, False

    if not image_url or len(image_url) < 10:
        logger.warning(f"Skipped: Missing Image for {title[:30]}")
        return None, None, False

    if not external_url or not external_id:
        logger.warning(f"Skipped: Missing URL/External ID for {title[:30]}")
        return None, None, False

    raw_currency = product_data.get('currency')
    if not raw_currency and product_data.get('_price_raw'):
        match = re.search(r'[A-Z]{3}', product_data['_price_raw'].upper())
        if match:
            raw_currency = match.group()
    product_data['currency'] = raw_currency if raw_currency else 'USD'

    if not is_valid_usd_price(product_data.get('_price_raw', ''), price_val):
        return None, None, False

    brand = _clean_brand((product_data.get('brand') or ''), title)
    gtin = (product_data.get('gtin') or '').strip() or None
    asin = (product_data.get('asin') or '').strip() or None

    if all_categories is None:
        all_categories = list(Category.objects.all())

    if category_slug:
        category = next(
            (c for c in all_categories if c.slug == category_slug), None)
    else:
        category = _resolve_category(
            product_data.get('category_path'), title, _get_category_cache()
        )

    # ── Extract rating & review from product_data ─────────────────────────
    incoming_rating = _normalize_rating(product_data.get('seller_rating'))
    incoming_reviews = 0
    try:
        incoming_reviews = int(product_data.get('seller_feedback_count') or 0)
    except (ValueError, TypeError):
        incoming_reviews = 0

    with transaction.atomic():

        product = _find_matching_product(title, brand, gtin, asin)

        if product:
            created = False
            updated_fields = []
            if gtin and not product.gtin:
                product.gtin = gtin
                updated_fields.append('gtin')
            if asin and not product.asin:
                product.asin = asin
                updated_fields.append('asin')
            if brand and not product.brand:
                product.brand = brand
                updated_fields.append('brand')
            if not product.category and category:
                product.category = category
                updated_fields.append('category')
            # ── Update rating only if we have better data ─────────────
            if incoming_rating > 0 and (not product.rating or product.rating == 0):
                product.rating = incoming_rating
                updated_fields.append('rating')
            if incoming_reviews > 0 and product.review_count == 0:
                product.review_count = incoming_reviews
                updated_fields.append('review_count')
            # ─────────────────────────────────────────────────────────
            if updated_fields:
                product.save(update_fields=updated_fields)
        else:
            created = True
            base_slug = slugify(title)[:490]
            slug = (
                f"{base_slug}-{str(external_id)[:8]}"
                if Product.objects.filter(slug=base_slug).exists()
                else base_slug
            )
            product = Product.objects.create(
                title=title,
                slug=slug,
                brand=brand,
                model_number=product_data.get('model_number') or external_id,
                main_image=product_data.get('main_image', ''),
                category=category,
                gtin=gtin,
                asin=asin,
                rating=incoming_rating,
                review_count=incoming_reviews,
            )

        was_available = True
        was_coupon = False
        was_price = None
        try:
            old_listing = ProductListing.objects.only('is_available', 'has_coupon', 'price').get(
                platform=platform,
                external_id=external_id
            )
            was_available = old_listing.is_available
            was_coupon = old_listing.has_coupon
            was_price = old_listing.price
        except ProductListing.DoesNotExist:
            was_available = False

        shipping = product_data.get('shipping_info', {})
        listing, listing_created = ProductListing.objects.update_or_create(
            platform=platform,
            external_id=external_id,
            defaults={
                'product':           product,
                'external_url':      product_data.get('external_url', ''),
                'price':             price_val,
                'currency':          product_data.get('currency', 'USD'),
                'original_price':    product_data.get('original_price'),
                'discount_percentage': product_data.get('discount_percentage'),
                'condition':         product_data.get('condition', 'NEW'),
                'quantity':          int(product_data.get('quantity') or 1),
                'seller_username':   product_data.get('seller_username', 'Merchant'),
                'seller_rating':     product_data.get('seller_rating'),
                'seller_feedback_count': product_data.get('seller_feedback_count', 0),
                'item_location':     product_data.get('item_location', ''),
                'ships_from_country': product_data.get('ships_from_country', ''),
                'shipping_cost':     shipping.get('cost', 0),
                'shipping_currency': shipping.get('currency', 'USD'),
                'free_shipping':     bool(shipping.get('free_shipping', False)),
                'estimated_delivery_days': shipping.get('estimated_days'),
                'returns_accepted':  product_data.get('returns_accepted', False),
                'return_period_days': product_data.get('return_period_days'),
                'is_available':      bool(product_data.get('is_available', True)),
                'has_coupon':     product_data.get('has_coupon', False),
                'coupon_text':    product_data.get('coupon_text', ''),
                'deal_badge':     product_data.get('deal_badge', ''),
                'is_best_seller': product_data.get('is_best_seller', False),
            }
        )

        try:
            from notifications.utils import (
                send_back_in_stock_notification,
                send_flash_sale_notification,
                create_notification,
                send_price_drop_notification,
            )
            from ..models import Favorite
            
            product_link = f"/product/{product.slug}" if product.slug else f"/product/{product.id}"
            is_now_available = bool(product_data.get('is_available', True))
            has_now_coupon = bool(product_data.get('has_coupon', False)) or bool(product_data.get('coupon_text', ''))
            
            if not was_available and is_now_available:
                favorites = Favorite.objects.filter(product=product).select_related('user')
                for fav in favorites:
                    send_back_in_stock_notification(
                        fav.user,
                        product.title,
                        product_link
                    )
            
            has_discount = product_data.get('discount_percentage') or (
                product_data.get('original_price') and price_val < float(product_data['original_price'])
            )
            if has_discount:
                favorites = Favorite.objects.filter(product=product).select_related('user')
                for fav in favorites:
                    create_notification(
                        user=fav.user,
                        title="Wishlist Item on Sale! 🏷️",
                        body=f"Your favorite item '{product.title}' is now on sale for ${price_val}!",
                        notification_type="WISHLIST_SALE",
                        channel="SYSTEM",
                        cta_text="View Product",
                        cta_link=product_link
                    )
            
            if not was_coupon and has_now_coupon:
                favorites = Favorite.objects.filter(product=product).select_related('user')
                for fav in favorites:
                    send_flash_sale_notification(
                        fav.user,
                        title="Special Coupon Available! 🎟️",
                        body=f"A coupon is now available for '{product.title}': {product_data.get('coupon_text') or 'Discount applied'}",
                        product_url=product_link
                    )
            
            if platform.code.startswith('local-seller-') and is_now_available:
                cheapest_online = ProductListing.objects.filter(
                    product=product,
                    is_available=True
                ).exclude(platform__code__startswith='local-seller-').order_by('price').first()
                
                if cheapest_online and price_val < cheapest_online.price:
                    favorites = Favorite.objects.filter(product=product).select_related('user')
                    for fav in favorites:
                        create_notification(
                            user=fav.user,
                            title="Better Local Deal Found! 📍",
                            body=f"A local seller has listed '{product.title}' for ${price_val}, which is cheaper than online stores!",
                            notification_type="LOCAL_DEAL",
                            channel="SYSTEM",
                            cta_text="View Product",
                            cta_link=product_link
                        )
            
            # General Price Drop alert for Wishlist/Favorite users
            if was_price and price_val < was_price:
                favorites = Favorite.objects.filter(product=product).select_related('user')
                for fav in favorites:
                    send_price_drop_notification(
                        fav.user,
                        product.title,
                        product_link
                    )

            # New lowest price found check
            try:
                lowest_history = PriceHistory.objects.filter(listing__product=product).order_by('price').first()
                if lowest_history and price_val < lowest_history.price:
                    favorites = Favorite.objects.filter(product=product).select_related('user')
                    for fav in favorites:
                        create_notification(
                            user=fav.user,
                            title="New Lowest Price Found! 💎",
                            body=f"Fantastic news! '{product.title}' has hit a new lowest price of ${price_val} on {platform.name}!",
                            notification_type="PRICE_DROP",
                            channel="SYSTEM",
                            cta_text="View Product",
                            cta_link=product_link
                        )
            except Exception as eh:
                logger.error(f"Error checking new lowest price: {eh}")

        except Exception as e:
            logger.error(f"Error sending automatic notifications: {str(e)}")

        if listing_created:
            PriceHistory.objects.create(
                listing=listing, price=listing.price, currency=listing.currency
            )

        additional_images = product_data.get('additional_images', [])
        if additional_images and created:
            for order, img_url in enumerate(additional_images[:10]):
                if img_url:
                    ProductImage.objects.get_or_create(
                        product=product,
                        image_url=img_url,
                        defaults={'order': order}
                    )

        specs = product_data.get('specifications', {})
        if specs:
            for name, value in specs.items():
                ProductSpecification.objects.update_or_create(
                    product=product,
                    name=name,
                    defaults={'value': str(value)}
                )

    try:
        from notifications.utils import send_price_drop_notification, send_target_price_reached_notification
        from ..models import PriceAlert

        active_alerts = PriceAlert.objects.filter(
            product=product,
            is_active=True,
            target_price__gte=price_val
        ).select_related('user')

        for alert in active_alerts:
            title = "Price Drop Alert! 📉"
            body = f"Good news! {product.title} is now ${price_val} on {platform.name}. Buy it before the price goes up!"
            send_price_drop_notification(alert.user, product.title, f"/product/{product.id}")
 
            if alert.target_price and float(alert.target_price) >= float(price_val):
                send_target_price_reached_notification(alert.user, product.title, f"/product/{product.id}")

    except Exception as e:
        logger.error(
            f"Error processing price alerts for product {product.id}: {str(e)}")

    return product, listing, created
