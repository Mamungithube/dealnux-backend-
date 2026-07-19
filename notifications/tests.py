from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from django.urls import reverse

from .models import Notification, NotificationPreference
from .views import create_notification


class NotificationFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email='notify@example.com', password='testpass123')

    def test_create_notification_respects_preference(self):
        pref = NotificationPreference.get_for_user(self.user)
        pref.shopping_price_alerts = False
        pref.save()

        created = create_notification(
            self.user,
            'Price drop',
            'A product dropped in price.',
            'PRICE_DROP',
            channel='SYSTEM',
        )

        self.assertIsNone(created)

    def test_create_notification_allows_enabled_preference(self):
        pref = NotificationPreference.get_for_user(self.user)
        pref.shopping_price_alerts = True
        pref.save()

        created = create_notification(
            self.user,
            'Price drop',
            'A product dropped in price.',
            'PRICE_DROP',
            channel='SYSTEM',
        )

        self.assertIsNotNone(created)


class DeleteAllNotificationsAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email='notify@example.com', password='testpass123')
        self.other_user = get_user_model().objects.create_user(email='other@example.com', password='testpass123')
        self.url = reverse('notifications-delete-all')
        
        # Create some notifications for user
        Notification.objects.create(user=self.user, title='Test 1', body='Body 1', notification_type='TEST')
        Notification.objects.create(user=self.user, title='Test 2', body='Body 2', notification_type='TEST')
        
        # Create one notification for other user
        Notification.objects.create(user=self.other_user, title='Other 1', body='Body O', notification_type='TEST')

    def test_delete_all_notifications_unauthenticated(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 401)
        # Verify no notifications were deleted
        self.assertEqual(Notification.objects.count(), 3)

    def test_delete_all_notifications_authenticated(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['message'], 'All notifications deleted successfully.')
        
        # Verify user's notifications are deleted
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 0)
        # Verify other user's notifications are NOT deleted
        self.assertEqual(Notification.objects.filter(user=self.other_user).count(), 1)

