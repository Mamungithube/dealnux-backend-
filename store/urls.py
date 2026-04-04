from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'seller-requests', views.SellerRequestViewSet,  basename='seller-request')
router.register(r'seller-profiles', views.SellerProfileViewSet,  basename='seller-profile')
router.register(r'seller-products', views.SellerProductViewSet,  basename='seller-product')
router.register(r'orders',          views.OrderViewSet,          basename='order')
router.register(r'coupons',         views.CouponViewSet,         basename='coupon')

app_name = 'store'

urlpatterns = [
    path('', include(router.urls)),
    path('seller/dashboard/', views.SellerDashboardView.as_view(), name='seller-dashboard'),
]