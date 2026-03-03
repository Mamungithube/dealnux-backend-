from rest_framework import serializers
from .models import AdvertiserRequest, CustomAd, AdReview
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError as DjangoValidationError


class AdReviewSerializer(serializers.ModelSerializer):
    reviewer_email = serializers.EmailField(source='reviewer.email', read_only=True)
    
    class Meta:
        model = AdReview
        fields = ['id', 'status', 'feedback', 'reviewed_at', 'reviewer_email']
        read_only_fields = ['reviewed_at']



class AdvertiserRequestSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    
    class Meta:
        model = AdvertiserRequest
        fields = [
            'id', 'user_email', 'business_name', 
            'business_details', 'website', 'applied_at', 
            'is_reviewed', 'reviewed_at', 'rejection_reason'
        ]
        read_only_fields = ['is_reviewed', 'reviewed_at', 'rejection_reason']

    def create(self, validated_data):
        user = self.context['request'].user
        
        # পুরনো check সরিয়ে নিচেরটা দিন
        pending = AdvertiserRequest.objects.filter(user=user, is_reviewed=False).exists()
        if pending:
            raise serializers.ValidationError("Your request is still under review.")
        
        # Rejected হলে পুরনো request delete করে নতুন তৈরি করুন
        AdvertiserRequest.objects.filter(user=user, is_reviewed=True).delete()
        
        return AdvertiserRequest.objects.create(user=user, **validated_data)

    def validate_website(self, value):
        """Validate URL format"""
        if value:
            validator = URLValidator()
            try:
                validator(value)
            except DjangoValidationError:
                raise serializers.ValidationError("Enter a valid URL")
        return value


class AdSerializer(serializers.ModelSerializer):
    advertiser_name = serializers.CharField(source='advertiser.Fullname', read_only=True)
    ctr = serializers.FloatField(read_only=True)
    budget_remaining = serializers.FloatField(read_only=True)
    reviews = AdReviewSerializer(many=True, read_only=True)

    class Meta:
        model = CustomAd
        fields = [
            'id', 'title', 'description', 'image', 'target_url',
            'target_section',
            'total_budget', 'spent_amount', 'priority_weight',
            'is_premium', 'clicks', 'impressions', 'ctr',
            'start_date', 'end_date', 'is_approved', 'status',
            'cta_text', 'advertiser_name', 'budget_remaining',
            'created_at', 'updated_at', 'reviews'
        ]
        read_only_fields = [
            'spent_amount', 'clicks', 'impressions',
            'is_approved', 'status',
            'created_at', 'updated_at', 'reviews'
        ]

    def validate(self, data):
        """Cross-field validation"""
        if data.get('end_date') and data.get('start_date'):
            if data['end_date'] <= data['start_date']:
                raise serializers.ValidationError(
                    "End date must be after start date"
                )
        
        if data.get('priority_weight', 0) > 100:
            raise serializers.ValidationError(
                "Priority weight cannot exceed 100"
            )
        
        if data.get('total_budget', 0) <= 0:
            raise serializers.ValidationError(
                "Budget must be greater than 0"
            )
        
        return data

    def validate_target_url(self, value):
        """Validate target URL"""
        validator = URLValidator()
        try:
            validator(value)
        except DjangoValidationError:
            raise serializers.ValidationError("Enter a valid URL")
        return value


class AdPublicSerializer(serializers.ModelSerializer):
    """Public facing serializer - minimal data exposure"""
    class Meta:
        model = CustomAd
        fields = "__all__"



# serializers.py - AdReview serializer

