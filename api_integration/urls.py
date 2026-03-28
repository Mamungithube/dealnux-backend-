from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'products', views.ProductViewSet, basename='product')
router.register(r'listings', views.ProductListingViewSet, basename='listing')
router.register(r'platforms', views.PlatformViewSet, basename='platform')
router.register(r'categories', views.CategoryViewSet, basename='category')
router.register(r'cart', views.CartViewSet, basename='cart')
router.register(r'favorites', views.FavoriteViewSet, basename='favorite')

app_name = 'api_integration'

urlpatterns = [
    path('categories/tree/', views.CategoryTreeView.as_view(), name='category-tree'),
    path('categories/parents/', views.CategoryParentListView.as_view(), name='category-parents'),
    path('categories/<slug:slug>/children/', views.CategoryChildrenView.as_view(), name='category-children'),
    path('products/<int:pk>/detail/', views.product_detail, name='product-detail'),
    path('', include(router.urls)),
    path('compare-prices/<slug:slug>/', views.compare_prices_api, name='compare-prices'),
    path('search-and-sync/', views.search_and_sync, name='search_and_sync'),
    path('bulk-sync/', views.bulk_sync_products, name='bulk_sync'),
    # path('sync-from-search/', views.sync_from_search_results, name='sync_from_search'),
    path('get-external-ids/', views.get_external_ids, name='get_external_ids'),
    path('smart-search/', views.smart_search, name='smart_search'),
    path('task-status/<str:task_id>/', views.task_status, name='task_status'),
    path('products/<slug:slug>/price-history/', views.product_price_history, name='product_price_history'),
    path('dashboard/', views.DashboardSavingsView.as_view(), name='dashboard-savings'),
    path('products/category/<slug:slug>/compare_prices/', views.category_compare_prices, name='category-compare-prices'),
]