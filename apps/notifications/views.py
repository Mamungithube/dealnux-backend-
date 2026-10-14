import time

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import generics, status

from notifications.models import Notification, NotificationPreference
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DeviceToken
from .serializers import NotificationPreferenceSerializer, NotificationSerializer
from .services import (
    get_user_notifications_summary,
    mark_all_notifications_as_read,
    delete_all_user_notifications,
    broadcast_admin_notification,
)

User = get_user_model()


# -------------------------- Device Token Registration (Push Notifications) --------------------------
class DeviceTokenView(APIView):
    """Save a user device token for FCM push notifications."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = request.data.get('fcm_token')
        if not token:
            return Response({'error': 'fcm_token is required'}, status=400)

        DeviceToken.objects.get_or_create(user=request.user, fcm_token=token)
        return Response({'success': True, 'message': 'FCM token saved.'}, status=200)


# -------------------------- User Notification List & Unread Count View --------------------------
class NotificationListView(generics.ListAPIView):
    """Show notification history for the authenticated user."""
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def list(self, request):
        data = get_user_notifications_summary(request.user)

        return Response({
            'success': True,
            'code': 200,
            'message': 'Notifications fetched successfully.',
            'timestamp': int(time.time()),
            'data': data
        }, status=200)


# -------------------------- Mark All Notifications As Read View --------------------------
class MarkNotificationsReadView(APIView):
    """Mark all notifications as read for the authenticated user."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        mark_all_notifications_as_read(request.user)
        return Response({'success': True, 'message': 'Notifications marked as read.'})


# -------------------------- Delete All User Notifications View --------------------------
class DeleteAllNotificationsView(APIView):
    """Delete all notifications for the authenticated user."""
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        delete_all_user_notifications(request.user)
        return Response({'success': True, 'message': 'All notifications deleted successfully.'})


# -------------------------- Notification Preferences View (Get & Update) --------------------------
class NotificationPreferenceView(APIView):
    """Allow users to manage their notification preferences."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        prefs = NotificationPreference.get_for_user(request.user)
        serializer = NotificationPreferenceSerializer(prefs)
        return Response({'success': True, 'data': serializer.data})

    def patch(self, request):
        prefs = NotificationPreference.get_for_user(request.user)
        serializer = NotificationPreferenceSerializer(prefs, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'success': True, 'message': 'Preferences updated.', 'data': serializer.data})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# -------------------------- Admin Notification Broadcast View (Staff Only) --------------------------
class AdminNotificationBroadcastView(APIView):
    """Create a manual notification broadcast for admins."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.is_staff:
            return Response({'error': 'Only staff users can send admin notifications.'}, status=403)

        try:
            count = broadcast_admin_notification(request.data)
            return Response({'success': True, 'message': f'Admin notification broadcast queued for {count} users.'})
        except ValueError as ve:
            return Response({'error': str(ve)}, status=400)
        except LookupError as le:
            return Response({'error': str(le)}, status=404)
        except Exception as e:
            return Response({'error': str(e)}, status=500)

