from rest_framework import serializers
from .models import AdvertiserRequest, CustomAd, AdReview , AdDailyPerformance
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from django.core.files.images import get_image_dimensions

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
        
        # Remove the old check and enter the following one.
        pending = AdvertiserRequest.objects.filter(user=user, is_reviewed=False).exists()
        if pending:
            raise serializers.ValidationError("Your request is still under review.")
        
        # If rejected, delete the old request and create a new one.
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
    target_url = serializers.URLField(max_length=500)

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
    
    def validate_image(self, value):
        width, height = get_image_dimensions(value)
        
        if width < 1280 or height < 720:
            raise serializers.ValidationError(
                f"The image size is very small! It must be at least 1280x720 pixels. "
                f"The size of your image: {width}x{height}"
            )

        if value.size > 2 * 1024 * 1024:
            raise serializers.ValidationError("The image file size must be less than 2MB.")

        ext = value.name.split('.')[-1].lower()
        valid_extensions = ['jpg', 'jpeg', 'png', 'gif']
        if ext not in valid_extensions:
            raise serializers.ValidationError("Only JPG, PNG, or GIF files are allowed.")

        return value


class AdPublicSerializer(serializers.ModelSerializer):
    """Public facing serializer with performance chart data"""
    advertiser_name = serializers.CharField(source='advertiser.Fullname', read_only=True)
    ctr = serializers.FloatField(read_only=True)
    budget_remaining = serializers.FloatField(read_only=True)
    reviews = AdReviewSerializer(many=True, read_only=True)
    target_url = serializers.URLField(max_length=500)
    performance = serializers.SerializerMethodField() 

    class Meta:
        model = CustomAd
        fields = [
            'id', 'title', 'description', 'image', 'target_url',
            'target_section', 'total_budget', 'spent_amount', 
            'priority_weight', 'is_premium', 'clicks', 'impressions', 
            'ctr', 'start_date', 'end_date', 'is_approved', 'status',
            'cta_text', 'advertiser_name', 'budget_remaining',
            'created_at', 'updated_at', 'reviews', 'performance'
        ]

    def get_performance(self, obj):
        from datetime import timedelta
        start = obj.start_date.date()
        today = timezone.now().date()
        end = min(obj.end_date.date(), today)

        daily_data = AdDailyPerformance.objects.filter(
            ad=obj,
            date__gte=start,
            date__lte=today
        ).order_by('date')

        data_map = {d.date: d for d in daily_data}
        result = []
        current = start
        while current <= end:
            if current in data_map:
                result.append({
                    'date': current.strftime('%Y-%m-%d'),
                    'impressions': data_map[current].impressions,
                    'clicks': data_map[current].clicks,
                })
            else:
                result.append({
                    'date': current.strftime('%Y-%m-%d'),
                    'impressions': 0,
                    'clicks': 0,
                })
            current += timedelta(days=1)
        return result

class AdDailyPerformanceSerializer(serializers.ModelSerializer):
    day = serializers.SerializerMethodField()

    class Meta:
        model = AdDailyPerformance
        fields = ['day', 'impressions', 'clicks']

    def get_day(self, obj):
        # Mon, Tue, Wed... format
        return obj.date.strftime('%a')

