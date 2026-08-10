from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient
from account.models import User
from payment.models import SubscriptionPlan, UserSubscription


class AppleIAPTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='testapple@example.com',
            password='testpassword123'
        )
        self.client.force_authenticate(user=self.user)

        self.monthly_plan = SubscriptionPlan.objects.create(
            name='Dealnux PRO',
            plan_type='PRO_MONTHLY',
            price=9.99,
            apple_product_id='com.dealnux.app.premium.monthly',
            is_active=True
        )

    def test_apple_verify_receipt_success(self):
        response = self.client.post('/api/v1/payment/apple/verify/', {
            'product_id': 'com.dealnux.app.premium.monthly',
            'transaction_id': '2000000123456789'
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.get('success'))
        self.assertTrue(response.data.get('is_active'))

        sub = UserSubscription.objects.get(user=self.user)
        self.assertEqual(sub.status, 'ACTIVE')
        self.assertEqual(sub.payment_gateway, 'APPLE')
        self.assertEqual(sub.apple_latest_transaction_id, '2000000123456789')

    def test_apple_server_notifications(self):
        # Create active subscription first
        sub = UserSubscription.objects.create(
            user=self.user,
            plan=self.monthly_plan,
            status='ACTIVE',
            payment_gateway='APPLE',
            apple_original_transaction_id='2000000123456789',
            expires_at=timezone.now() + timedelta(days=30)
        )

        unauth_client = APIClient()
        response = unauth_client.post('/api/v1/payment/apple/notifications/', {
            'signedPayload': 'dummy_payload'
        }, format='json')

        self.assertEqual(response.status_code, 200)

