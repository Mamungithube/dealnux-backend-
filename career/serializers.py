from rest_framework import serializers
from .models import CareerApplication


class CareerApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = CareerApplication
        fields = [
            'id', 'full_name', 'email', 'phone', 'role',
            'experience', 'why_join', 'resume',
            'portfolio_url', 'linkedin_url', 'applied_at'
        ]
        read_only_fields = ['applied_at']