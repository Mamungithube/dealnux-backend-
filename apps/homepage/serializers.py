from rest_framework import serializers
from .models import MainSliderBanner, SideBanner


class MainSliderBannerSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = MainSliderBanner
        fields = ['id', 'title', 'image', 'image_url', 'order', 'is_active']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return obj.image.url if obj.image else None


class SideBannerSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    position_display = serializers.CharField(source='get_position_display', read_only=True)

    class Meta:
        model = SideBanner
        fields = ['id', 'title', 'image', 'image_url', 'position', 'position_display', 'is_active']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return obj.image.url if obj.image else None


class HomepageBannerSerializer(serializers.Serializer):
    """Single endpoint — সব banner একসাথে"""
    main_banners = MainSliderBannerSerializer(many=True)
    side_banners = SideBannerSerializer(many=True)