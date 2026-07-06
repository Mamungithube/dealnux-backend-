from django.test import TestCase
from django.contrib.auth import get_user_model

from .models import NotificationPreference
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
