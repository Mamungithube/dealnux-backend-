from rest_framework import serializers

from .models import PressCoverage,PressInquiry


class PressCoverageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PressCoverage
        fields = [
            'id', 'source_name', 'source_logo', 'published_date',
            'excerpt', 'article_url', 'is_featured', 'created_at'
        ]


class PressInquirySerializer(serializers.ModelSerializer):
    class Meta:
        model = PressInquiry
        fields = ['full_name', 'email', 'subject', 'message', 'created_at']
        read_only_fields = ['created_at']