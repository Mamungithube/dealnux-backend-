from rest_framework import serializers
from .models import PressCoverage


class PressCoverageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PressCoverage
        fields = [
            'id', 'source_name', 'source_logo', 'published_date',
            'excerpt', 'article_url', 'is_featured', 'created_at'
        ]