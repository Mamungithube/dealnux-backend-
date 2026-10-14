from django.conf import settings
from django.db import models
from django.utils import timezone


class DeviceToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='fcm_tokens')
    fcm_token = models.TextField(unique=True)
    device_type = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.device_type or 'unknown'}"


class Notification(models.Model):
    CHANNEL_CHOICES = [
        ('SYSTEM', 'System'),
        ('ADMIN', 'Admin'),
    ]

    RECIPIENT_CHOICES = [
        ('USER', 'Single User'),
        ('ALL_USERS', 'All Users'),
        ('PREMIUM_USERS', 'Premium Users'),
        ('FREE_USERS', 'Free Users'),
        ('ALL_SELLERS', 'All Sellers'),
        ('SELECTED_USERS', 'Selected Users'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    body = models.TextField()
    notification_type = models.CharField(max_length=50)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='SYSTEM')
    recipient_type = models.CharField(max_length=30, choices=RECIPIENT_CHOICES, default='USER')
    image_url = models.URLField(blank=True, null=True)
    cta_text = models.CharField(max_length=100, blank=True)
    cta_link = models.CharField(max_length=500, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    is_sent = models.BooleanField(default=True)
    scheduled_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.title}"

    @property
    def is_scheduled(self):
        return self.scheduled_at and self.scheduled_at > timezone.now()


class NotificationPreference(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notification_preferences')
    shopping_price_alerts = models.BooleanField(default=True)
    orders = models.BooleanField(default=True)
    promotions = models.BooleanField(default=True)
    referral_rewards = models.BooleanField(default=True)
    account_security = models.BooleanField(default=True)
    ai_recommendations = models.BooleanField(default=True)
    price_increase_alerts = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user} preferences"

    @classmethod
    def get_for_user(cls, user):
        return cls.objects.get_or_create(user=user)[0]
