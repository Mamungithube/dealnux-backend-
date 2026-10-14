from rest_framework import serializers

from .models import Notification, NotificationPreference


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            'id', 'title', 'body', 'notification_type', 'channel', 'recipient_type',
            'image_url', 'cta_text', 'cta_link', 'is_read', 'is_sent', 'scheduled_at', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = [
            'shopping_price_alerts', 'orders', 'promotions', 'referral_rewards',
            'account_security', 'ai_recommendations', 'price_increase_alerts'
        ]
