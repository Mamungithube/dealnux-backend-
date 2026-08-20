import os

source_path = r'c:\mamun file\Project File\dealnux-backend-\api_integration\views.py'
dest_dir = r'c:\mamun file\Project File\dealnux-backend-\api_integration\views'
os.makedirs(dest_dir, exist_ok=True)

with open(source_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Common header imports needed
common_imports = """from django.utils import timezone
from datetime import timedelta
import time
import logging
import math
import re
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

logger = logging.getLogger(__name__)
"""

# 1. category_views.py (lines 1592 to 1665)
cat_code = common_imports + "\n\n" + "".join(lines[1591:1664])
with open(os.path.join(dest_dir, 'category_views.py'), 'w', encoding='utf-8') as f:
    f.write(cat_code)

# 2. barcode_views.py (lines 2753 to 2969)
barcode_code = common_imports + "\n\n" + "".join(lines[2752:2969])
with open(os.path.join(dest_dir, 'barcode_views.py'), 'w', encoding='utf-8') as f:
    f.write(barcode_code)

# 3. user_views.py: CartViewSet (2074-2361), DashboardSavingsView (2363-2409), FavoriteViewSet (2544-2703), PriceAlertViewSet (2723-2747)
user_code = common_imports + "\n\n" + "".join(lines[2073:2409]) + "\n\n" + "".join(lines[2543:2703]) + "\n\n" + "".join(lines[2722:2747])
with open(os.path.join(dest_dir, 'user_views.py'), 'w', encoding='utf-8') as f:
    f.write(user_code)

# 4. comparison_views.py:
# match helpers (1149-1234), compare_prices_api (1240-1442), category_compare_prices (2412-2538)
comp_code = common_imports + "\n\n" + "".join(lines[1148:1442]) + "\n\n" + "".join(lines[2411:2538])
with open(os.path.join(dest_dir, 'comparison_views.py'), 'w', encoding='utf-8') as f:
    f.write(comp_code)

# 5. search_sync_views.py:
# helper functions (60-102), sync functions (296-570), search_and_sync / smart_search / paginate (1671-1894), bulk_sync / get_external_ids (1927-2068)
sync_imports = """
from api_integration.services.walmart_service import WalmartService
from api_integration.services.amazon_service import AmazonService
from api_integration.services.sephora_service import SephoraService
from api_integration.services.ebay_service import EbayRapidService
from api_integration.services.target_service import TargetService
from api_integration.services.wayfair_service import WayfairService
from api_integration.services.aliexpress_service import AliExpressService
from api_integration.services.bestbuy_service import BestBuyService
from api_integration.tasks import (
    sync_amazon_task, sync_ebay_task, sync_walmart_task,
    sync_all_platforms_task
)
"""
search_sync_code = common_imports + sync_imports + "\n\n" + "".join(lines[59:102]) + "\n\n" + "".join(lines[295:570]) + "\n\n" + "".join(lines[1670:1894]) + "\n\n" + "".join(lines[1926:2068])
with open(os.path.join(dest_dir, 'search_sync_views.py'), 'w', encoding='utf-8') as f:
    f.write(search_sync_code)

# 6. product_views.py:
# product_detail (106-264), StandardResultsSetPagination (576-580), ProductViewSet (587-1090), ProductListingViewSet (1557-1580), PlatformViewSet (1582-1590), product_price_history (1897-1924), amazon_promo_details (2707-2721)
product_code = common_imports + "\n\n" + "".join(lines[105:264]) + "\n\n" + "".join(lines[575:1090]) + "\n\n" + "".join(lines[1556:1590]) + "\n\n" + "".join(lines[1896:1924]) + "\n\n" + "".join(lines[2706:2721])
with open(os.path.join(dest_dir, 'product_views.py'), 'w', encoding='utf-8') as f:
    f.write(product_code)

# 7. __init__.py
init_code = """# api_integration/views package
from .product_views import (
    product_detail,
    StandardResultsSetPagination,
    ProductViewSet,
    ProductListingViewSet,
    PlatformViewSet,
    product_price_history,
    amazon_promo_details,
)
from .category_views import (
    CategoryViewSet,
    CategoryTreeView,
    CategoryParentListView,
    CategoryChildrenView,
)
from .comparison_views import (
    extract_storage,
    normalize_brand,
    extract_core_title,
    variant_check,
    storage_check,
    model_number_check,
    product_match_score,
    compare_prices_api,
    category_compare_prices,
)
from .search_sync_views import (
    clean_display_title,
    normalize_title,
    similarity_score,
    extract_keywords,
    token_similarity,
    _build_result_template,
    _generic_sync_loop,
    _normalize_and_sync_generic,
    sync_ebay_products,
    sync_amazon_products,
    sync_walmart_products,
    sync_sephora_products,
    sync_target_products,
    sync_wayfair_products,
    sync_aliexpress_products,
    sync_bestbuy_products,
    sync_all_platforms,
    search_and_sync,
    smart_search,
    paginate_results,
    get_pagination_meta,
    task_status,
    bulk_sync_products,
    get_external_ids,
)
from .user_views import (
    CartViewSet,
    DashboardSavingsView,
    FavoriteViewSet,
    PriceAlertViewSet,
)
from .barcode_views import (
    get_title_and_image_from_barcode_safely,
    get_title_from_barcode_safely,
    barcode_scanner_pipeline,
    decode_barcode_to_slug,
)
from dealnux.responses import success_response, error_response
"""
with open(os.path.join(dest_dir, '__init__.py'), 'w', encoding='utf-8') as f:
    f.write(init_code)

print('All 7 view files generated successfully!')
