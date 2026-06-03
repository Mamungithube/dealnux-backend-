from django.urls import path
from .views import HomepageBannerAPIView, MainSliderBannerAPIView, SideBannerAPIView, homepage_view

app_name = 'banners'

urlpatterns = [
    # Template
    path('', homepage_view, name='homepage'),

    # API
    path('images/', HomepageBannerAPIView.as_view(), name='api-banners-all'),
    path('banners/main/', MainSliderBannerAPIView.as_view(), name='api-banners-main'),
    path('banners/side/', SideBannerAPIView.as_view(), name='api-banners-side'),
]