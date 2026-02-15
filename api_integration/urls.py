from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# REST API Router
router = DefaultRouter()
router.register(r'products', views.ProductViewSet, basename='product')
router.register(r'listings', views.ProductListingViewSet, basename='listing')
router.register(r'platforms', views.PlatformViewSet, basename='platform')
router.register(r'categories', views.CategoryViewSet, basename='category')

app_name = 'api_integration'

urlpatterns = [
    # API Root
    path('', views.api_root, name='api_root'),
    
    # REST API ViewSets
    path('', include(router.urls)),
    
    # Custom API Endpoints
    path('api/search-and-sync/', views.search_and_sync, name='search_and_sync'),
    path('api/bulk-sync/', views.bulk_sync_products, name='bulk_sync'),
]