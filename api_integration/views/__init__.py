# api_integration/views package
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
