from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'products', views.ProductViewSet, basename='product')
router.register(r'listings', views.ProductListingViewSet, basename='listing')
router.register(r'platforms', views.PlatformViewSet, basename='platform')
router.register(r'categories', views.CategoryViewSet, basename='category')

app_name = 'api_integration'

urlpatterns = [
    path('', views.api_root, name='api_root'),
    path('', include(router.urls)),
    
    # Existing endpoints
    path('search-and-sync/', views.search_and_sync, name='search_and_sync'),
    path('bulk-sync/', views.bulk_sync_products, name='bulk_sync'),
    
    # ✨ নতুন 2টা endpoint add করুন
    path('sync-from-search/', views.sync_from_search_results, name='sync_from_search'),
    path('get-external-ids/', views.get_external_ids, name='get_external_ids'),

    # ClickBank Endpoints
    # path('clickbank/search-and-sync/', views.search_and_sync_clickbank, name='clickbank_search_sync'),
    # path('clickbank/categories/', views.get_clickbank_categories, name='clickbank_categories'),
    # path('clickbank/products/<str:product_id>/', views.clickbank_product_details, name='clickbank_product_details'),
]