from django.contrib import admin

from .models import Notification, NotificationPreference, DeviceToken


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('user__email', 'title', 'body')
    readonly_fields = ('created_at',)


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'shopping_price_alerts', 'orders', 'promotions', 'account_security', 'ai_recommendations')
    search_fields = ('user__email',)


@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'device_type', 'fcm_token', 'created_at')
    search_fields = ('user__email', 'fcm_token')
