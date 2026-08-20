from django.utils import timezone
from datetime import timedelta
import time
import logging
import math
import re
import requests
from decimal import Decimal
from difflib import SequenceMatcher

from django.db import transaction
from django.db.models import Q, F, Min, Count, Sum, Avg, Value, Case, When, FloatField
from django.db.models.functions import TruncDate
from django.core.cache import cache
from django.contrib.postgres.search import TrigramSimilarity

from rest_framework import viewsets, generics, permissions as drf_permissions
from rest_framework.views import APIView
from rest_framework.decorators import api_view, action, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import ValidationError

from rapidfuzz import fuzz

from api_integration.product_matcher import calculate_match_score, get_product_fingerprint
from api_integration.models import (
    Product, ProductListing, Platform, Category,
    CartItem, SavingsActivity, Favorite, PriceAlert
)
from api_integration.serializers import (
    ProductSerializer, ProductDetailSerializer,
    ProductListingSerializer, PlatformSerializer,
    CategorySerializer, PriceHistorySerializer,
    CartItemSerializer, FavoriteSerializer,
    CategoryTreeSerializer, CategoryChildSerializer, PriceAlertSerializer
)
from notifications.models import Notification
from notifications.serializers import NotificationSerializer
from store.serializers import SellerProductSerializer
from api_integration.db_helpers import save_generic_product_to_db

from dealnux.responses import success_response, error_response
from .comparison_views import compare_prices_api

logger = logging.getLogger(__name__)



def get_title_and_image_from_barcode_safely(barcode):
    """Fetches product title & image from free & open global barcode databases"""
    # 1. UPCItemDB
    try:
        r = requests.get(f"https://api.upcitemdb.com/prod/trial/lookup?upc={barcode}", timeout=4)
        if r.status_code == 200:
            data = r.json()
            if 'items' in data and len(data['items']) > 0:
                item = data['items'][0]
                title = item.get('title')
                imgs = item.get('images', [])
                img = imgs[0] if (imgs and isinstance(imgs, list)) else None
                if title:
                    return title, img
    except Exception:
        pass

    # 2. Open Food Facts
    try:
        r = requests.get(f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json", timeout=4)
        if r.status_code == 200:
            data = r.json()
            if data.get('status') == 1:
                p = data.get('product', {})
                title = p.get('product_name')
                img = p.get('image_url') or p.get('image_front_url')
                if title:
                    return title, img
    except Exception:
        pass

    # 3. Open Beauty Facts
    try:
        r = requests.get(f"https://world.openbeautyfacts.org/api/v0/product/{barcode}.json", timeout=4)
        if r.status_code == 200:
            data = r.json()
            if data.get('status') == 1:
                p = data.get('product', {})
                title = p.get('product_name')
                img = p.get('image_url') or p.get('image_front_url')
                if title:
                    return title, img
    except Exception:
        pass

    # 4. Open Products Facts
    try:
        r = requests.get(f"https://world.openproductsfacts.org/api/v0/product/{barcode}.json", timeout=4)
        if r.status_code == 200:
            data = r.json()
            if data.get('status') == 1:
                p = data.get('product', {})
                title = p.get('product_name')
                img = p.get('image_url') or p.get('image_front_url')
                if title:
                    return title, img
    except Exception:
        pass

    # 5. Google Books API (ISBN)
    try:
        r = requests.get(f"https://www.googleapis.com/books/v1/volumes?q=isbn={barcode}", timeout=4)
        if r.status_code == 200:
            data = r.json()
            if 'items' in data and len(data['items']) > 0:
                v = data['items'][0].get('volumeInfo', {})
                title = v.get('title')
                img_links = v.get('imageLinks', {})
                img = img_links.get('thumbnail') or img_links.get('smallThumbnail')
                if title:
                    return title, img
    except Exception:
        pass

    # 6. Open Library API (ISBN)
    try:
        r = requests.get(f"https://openlibrary.org/api/books?bibkeys=ISBN:{barcode}&format=json&jscmd=data", timeout=4)
        if r.status_code == 200:
            data = r.json()
            key = f"ISBN:{barcode}"
            if key in data:
                b = data[key]
                title = b.get('title')
                covers = b.get('cover', {})
                img = covers.get('large') or covers.get('medium') or covers.get('small')
                if title:
                    return title, img
    except Exception:
        pass

    # 7. Fallback to eBay Search API
    try:
        from .services.ebay_service import EbayRapidService
        ebay = EbayRapidService()
        items = ebay.search_products(barcode, limit=1)
        if items and len(items) > 0:
            item = items[0]
            title = item.get('title')
            img = item.get('image') or item.get('main_image')
            if title:
                return title, img
    except Exception:
        pass

    return None, None


def get_title_from_barcode_safely(barcode):
    title, _ = get_title_and_image_from_barcode_safely(barcode)
    return title




@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def barcode_scanner_pipeline(request):
    """
    1. Receives barcode (via GET query string or POST JSON/body).
    2. Converts to product name using external lookup.
    3. Finds or Creates a product in DB to get a slug.
    4. Internally redirects to the existing 'compare_prices_api' logic.
    """
    subscription = getattr(request.user, 'subscription', None)
    if not subscription or not subscription.is_active:
        return error_response("Please subscribe to a plan to use barcode scanner.", code=403)

    barcode = (
        request.query_params.get('code') or 
        request.query_params.get('barcode') or 
        (request.data.get('code') if isinstance(request.data, dict) else None) or 
        (request.data.get('barcode') if isinstance(request.data, dict) else None) or 
        ''
    ).strip()

    if not barcode:
        return error_response("Barcode is required", code=400)

    product = Product.objects.filter(Q(gtin=barcode) | Q(asin=barcode)).first()
    if not product:
        title_found, image_found = get_title_and_image_from_barcode_safely(barcode)
        
        if title_found:
            from django.utils.text import slugify
            import uuid
            
            base_slug = slugify(title_found)[:490]
            final_slug = base_slug if not Product.objects.filter(slug=base_slug).exists() else f"{base_slug}-{uuid.uuid4().hex[:5]}"

            product = Product.objects.create(
                title=title_found,
                slug=final_slug,
                gtin=barcode,
                main_image=image_found or '',
                is_active=True
            )
        else:
            return error_response("Could not identify this barcode. Try manual search.", code=404)
    else:
        if not product.main_image:
            _, image_found = get_title_and_image_from_barcode_safely(barcode)
            if image_found:
                product.main_image = image_found
                product.save(update_fields=['main_image'])

    return compare_prices_api(request._request, slug=product.slug)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def decode_barcode_to_slug(request):
    """
    Takes a barcode, finds the product title, creates a temporary product,
    and then calls the compare_prices_api to get all deals.
    """
    subscription = getattr(request.user, 'subscription', None)
    if not subscription or not subscription.is_active:
        return error_response("Please subscribe to a plan to use barcode scanner.", code=403)

    barcode = (
        request.query_params.get('code') or 
        request.query_params.get('barcode') or 
        (request.data.get('code') if isinstance(request.data, dict) else None) or 
        (request.data.get('barcode') if isinstance(request.data, dict) else None) or 
        ''
    ).strip()

    if not barcode:
        return error_response("Query parameter 'code' or 'barcode' is required.", code=400)

    product = Product.objects.filter(Q(gtin=barcode) | Q(asin=barcode)).first()

    if not product:
        title_found, image_found = get_title_and_image_from_barcode_safely(barcode)
        if not title_found:
            return error_response(f"Could not find a product title for barcode '{barcode}'.", code=404)

        from django.utils.text import slugify
        import uuid
        base_slug = slugify(title_found)[:490]
        final_slug = base_slug if not Product.objects.filter(slug=base_slug).exists() else f"{base_slug}-{uuid.uuid4().hex[:5]}"
        
        product = Product.objects.create(
            title=title_found,
            slug=final_slug,
            gtin=barcode,
            main_image=image_found or '',
            is_active=True
        )
    else:
        if not product.main_image:
            _, image_found = get_title_and_image_from_barcode_safely(barcode)
            if image_found:
                product.main_image = image_found
                product.save(update_fields=['main_image'])

    return compare_prices_api(request._request, slug=product.slug)