from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.shortcuts import render
from .models import MainSliderBanner, SideBanner
from .serializers import MainSliderBannerSerializer, SideBannerSerializer, HomepageBannerSerializer


# ─── API Views (DRF) ──────────────────────────────────────────

class HomepageBannerAPIView(APIView):
    """GET /api/banners/ — all active banners (public endpoint)"""
    permission_classes = [AllowAny]

    def get(self, request):
        main_banners = MainSliderBanner.objects.filter(is_active=True).order_by('order')[:5]
        side_banners = SideBanner.objects.filter(is_active=True).order_by('position')

        data = {
            'main_banners': MainSliderBannerSerializer(main_banners, many=True, context={'request': request}).data,
            'side_banners': SideBannerSerializer(side_banners, many=True, context={'request': request}).data,
        }
        return Response(data, status=status.HTTP_200_OK)


class MainSliderBannerAPIView(APIView):
    """GET /api/banners/main/ — main slider banners only (public endpoint)"""
    permission_classes = [AllowAny]

    def get(self, request):
        banners = MainSliderBanner.objects.filter(is_active=True).order_by('order')[:5]
        serializer = MainSliderBannerSerializer(banners, many=True, context={'request': request})
        return Response(serializer.data)


class SideBannerAPIView(APIView):
    """GET /api/banners/side/ — side banners only (public endpoint)"""
    permission_classes = [AllowAny]

    def get(self, request):
        banners = SideBanner.objects.filter(is_active=True).order_by('position')
        serializer = SideBannerSerializer(banners, many=True, context={'request': request})
        return Response(serializer.data)


# ─── Template View ────────────────────────────────────────────

def homepage_view(request):
    """Homepage template view"""
    main_banners = MainSliderBanner.objects.filter(is_active=True).order_by('order')[:5]

    side_banners = {b.position: b for b in SideBanner.objects.filter(is_active=True)}

    return render(request, 'banners/homepage.html', {
        'main_banners': main_banners,
        'side_banner_1': side_banners.get(1),
        'side_banner_2': side_banners.get(2),
        'side_banner_3': side_banners.get(3),
        'side_banner_4': side_banners.get(4),
    })