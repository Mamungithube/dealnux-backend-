from django.urls import path
from .views import (
    ApplyForAdvertiserView,
    CheckAdvertiserStatusView,
    CreateAdView,
    AdListView,
    AdClickTrackerView,
    AdvertiserAdDashboardView,
    AdDetailView,
    UpdateAdView,
    DeleteAdView,


    # Admin Views
    AdminAdvertiserRequestListView,
    AdminApproveAdvertiserView,
    AdminRejectAdvertiserView,
    AdminAdListView,
    AdminApproveAdView,
    AdminRejectAdView,
    AdminPauseAdView,
    AdminDashboardStatsView,
    AdminBulkApproveAdsView,
    AdminBulkRejectAdsView,
)

app_name = 'ads'

urlpatterns = [
    # User -> Advertiser Application
    path('apply/', ApplyForAdvertiserView.as_view(), name='apply-advertiser'),
    path('status/', CheckAdvertiserStatusView.as_view(), name='advertiser-status'),
    
    # Ad Management (Advertiser)
    path('create/', CreateAdView.as_view(), name='create-ad'),
    
    path('dashboard/', AdvertiserAdDashboardView.as_view(), name='advertiser-dashboard'),
    path('update/<int:pk>/', UpdateAdView.as_view(), name='update-ad'),
    path('delete/<int:pk>/', DeleteAdView.as_view(), name='delete-ad'),
    
    # Public Ad APIs
    path('list/', AdListView.as_view(), name='ad-list'),
    path('detail/<int:pk>/', AdDetailView.as_view(), name='ad-detail'),
    path('click/<int:ad_id>/', AdClickTrackerView.as_view(), name='track-click'),

    path('admin/stats/', AdminDashboardStatsView.as_view(), name='admin-stats'),
    
    # Advertiser Request Management
    path('admin/requests/', AdminAdvertiserRequestListView.as_view(), name='admin-requests'),
    path('admin/requests/<int:pk>/approve/', AdminApproveAdvertiserView.as_view(), name='admin-approve-advertiser'),
    path('admin/requests/<int:pk>/reject/', AdminRejectAdvertiserView.as_view(), name='admin-reject-advertiser'),
    
    # Ad Management
    path('admin/ads/', AdminAdListView.as_view(), name='admin-ads'),
    path('admin/ads/<int:pk>/approve/', AdminApproveAdView.as_view(), name='admin-approve-ad'),
    path('admin/ads/<int:pk>/reject/', AdminRejectAdView.as_view(), name='admin-reject-ad'),
    path('admin/ads/<int:pk>/<str:action>/', AdminPauseAdView.as_view(), name='admin-pause-ad'),
    
    # Bulk Actions
    path('admin/ads/bulk-approve/', AdminBulkApproveAdsView.as_view(), name='admin-bulk-approve'),
    path('admin/ads/bulk-reject/', AdminBulkRejectAdsView.as_view(), name='admin-bulk-reject'),
]