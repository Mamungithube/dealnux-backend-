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
from .utils import create_notification

User = get_user_model()


class DeviceTokenView(APIView):
    """Save a user device token for FCM push notifications."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = request.data.get('fcm_token')
        if not token:
            return Response({'error': 'fcm_token is required'}, status=400)

        DeviceToken.objects.get_or_create(user=request.user, fcm_token=token)
        return Response({'success': True, 'message': 'FCM token saved.'}, status=200)


class NotificationListView(generics.ListAPIView):
    """Show notification history for the authenticated user."""
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def list(self, request):
        notifications = Notification.objects.filter(user=request.user).order_by('-created_at')[:20]
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()

        return Response({
            'success': True,
            'code': 200,
            'message': 'Notifications fetched successfully.',
            'timestamp': int(time.time()),
            'data': {
                'unread_count': unread_count,
                'notifications': [
                    {
                        'id': n.id,
                        'title': n.title,
                        'body': n.body,
                        'channel': n.channel,
                        'recipient_type': n.recipient_type,
                        'image_url': n.image_url,
                        'cta_text': n.cta_text,
                        'cta_link': n.cta_link,
                        'is_read': n.is_read,
                        'created_at': n.created_at,
                    } for n in notifications
                ]
            }
        }, status=200)


class MarkNotificationsReadView(APIView):
    """Mark all notifications as read for the authenticated user."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'success': True, 'message': 'Notifications marked as read.'})


class DeleteAllNotificationsView(APIView):
    """Delete all notifications for the authenticated user."""
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        Notification.objects.filter(user=request.user).delete()
        return Response({'success': True, 'message': 'All notifications deleted successfully.'})



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


class AdminNotificationBroadcastView(APIView):
    """Create a manual notification broadcast for admins."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.is_staff:
            return Response({'error': 'Only staff users can send admin notifications.'}, status=403)

        title = request.data.get('title')
        body = request.data.get('body')
        recipient_type = request.data.get('recipient_type', 'ALL_USERS')
        notification_type = request.data.get('notification_type', 'ADMIN_MESSAGE')
        image_url = request.data.get('image_url', '')
        cta_text = request.data.get('cta_text', '')
        cta_link = request.data.get('cta_link', '')
        scheduled_at = request.data.get('scheduled_at')

        if not title or not body:
            return Response({'error': 'title and body are required.'}, status=400)

        user_queryset = User.objects.filter(is_active=True)
        if recipient_type == 'PREMIUM_USERS':
            user_queryset = user_queryset.filter(subscription__is_active=True)
        elif recipient_type == 'FREE_USERS':
            user_queryset = user_queryset.filter(subscription__isnull=True)
        elif recipient_type == 'ALL_SELLERS':
            user_queryset = user_queryset.filter(seller_profile__is_active=True)
        elif recipient_type == 'SELECTED_USERS':
            selected_ids = request.data.get('user_ids', [])
            if not selected_ids:
                return Response({'error': 'user_ids are required for SELECTED_USERS.'}, status=400)
            user_queryset = user_queryset.filter(id__in=selected_ids)

        users = list(user_queryset.distinct())
        if not users:
            return Response({'error': 'No matching users found.'}, status=404)

        for user in users:
            create_notification(
                user=user,
                title=title,
                body=body,
                notification_type=notification_type,
                channel='ADMIN',
                recipient_type=recipient_type,
                image_url=image_url or None,
                cta_text=cta_text,
                cta_link=cta_link,
                scheduled_at=scheduled_at and timezone.datetime.fromisoformat(scheduled_at.replace('Z', '+00:00')) or None,
                is_sent=True,
            )

        return Response({'success': True, 'message': 'Admin notification broadcast queued.'})
