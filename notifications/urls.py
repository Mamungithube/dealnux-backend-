from django.urls import path

from .views import AdminNotificationBroadcastView, DeviceTokenView, MarkNotificationsReadView, NotificationListView, NotificationPreferenceView, DeleteAllNotificationsView

urlpatterns = [
    path('device-token/', DeviceTokenView.as_view(), name='device-token'),
    path('notifications/', NotificationListView.as_view(), name='notifications'),
    path('notifications/read-all/', MarkNotificationsReadView.as_view(), name='notifications-read-all'),
    path('notifications/delete-all/', DeleteAllNotificationsView.as_view(), name='notifications-delete-all'),
    path('preferences/', NotificationPreferenceView.as_view(), name='notification-preferences'),
    path('admin-broadcast/', AdminNotificationBroadcastView.as_view(), name='admin-notification-broadcast'),
]
