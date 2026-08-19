from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from account.models import User


class DeleteAccountViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_email = "testuser@example.com"
        self.user_password = "Password123!"
        self.user = User.objects.create_user(
            email=self.user_email,
            password=self.user_password,
            name="Test User",
            is_active=True
        )
        self.url = reverse('delete-account')

    def test_delete_account_unauthenticated(self):
        response = self.client.delete(self.url, {'email': self.user_email, 'password': self.user_password}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_delete_account_missing_fields(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.delete(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data['data'])
        self.assertIn('password', response.data['data'])
        self.assertTrue(User.objects.filter(id=self.user.id).exists())

    def test_delete_account_mismatched_email(self):
        self.client.force_authenticate(user=self.user)
        payload = {'email': 'other@example.com', 'password': self.user_password}
        response = self.client.delete(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['message'], "Email address does not match your account.")
        self.assertTrue(User.objects.filter(id=self.user.id).exists())

    def test_delete_account_invalid_password(self):
        self.client.force_authenticate(user=self.user)
        payload = {'email': self.user_email, 'password': 'WrongPassword'}
        response = self.client.delete(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data.get('success'))
        self.assertTrue(User.objects.filter(id=self.user.id).exists())

    def test_delete_account_success_via_delete_method(self):
        self.client.force_authenticate(user=self.user)
        payload = {'email': self.user_email, 'password': self.user_password}
        response = self.client.delete(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('success'))
        self.assertFalse(User.objects.filter(id=self.user.id).exists())

    def test_delete_account_success_via_post_method(self):
        self.client.force_authenticate(user=self.user)
        payload = {'email': self.user_email, 'password': self.user_password}
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('success'))
        self.assertFalse(User.objects.filter(id=self.user.id).exists())


class ReferralRewardTests(TestCase):
    def setUp(self):
        from account.models import SiteSettings
        from payment.models import SubscriptionPlan, UserSubscription
        from store.models import Order
        from django.utils import timezone

        # Ensure SiteSettings with $10 referral reward
        self.site_settings = SiteSettings.get()
        self.site_settings.referral_reward_amount = 10.00
        self.site_settings.save()

        # Create referrer user
        self.referrer = User.objects.create_user(
            email="referrer@example.com",
            password="Password123!",
            name="Referrer User",
            referral_code="REF12345",
            balance=0,
            is_active=True
        )

        # Create referred friend user
        self.friend = User.objects.create_user(
            email="friend@example.com",
            password="Password123!",
            name="Friend User",
            referred_by=self.referrer,
            has_claimed_referral=True,
            balance=0,
            is_active=True
        )

        # Active subscriptions for both
        self.plan = SubscriptionPlan.objects.create(
            name="Dealnux PRO",
            plan_type="PRO_MONTHLY",
            price=9.99
        )
        self.referrer_sub = UserSubscription.objects.create(
            user=self.referrer,
            plan=self.plan,
            status='ACTIVE',
            expires_at=timezone.now() + timezone.timedelta(days=30)
        )
        self.friend_sub = UserSubscription.objects.create(
            user=self.friend,
            plan=self.plan,
            status='ACTIVE',
            expires_at=timezone.now() + timezone.timedelta(days=30)
        )

        # Order placed by friend
        self.order = Order.objects.create(
            buyer=self.friend,
            unit_price=25.00,
            total_price=25.00,
            shipping_address="123 Test St"
        )

    def test_referral_reward_awarded_only_to_referrer(self):
        from payment.utils import process_referral_reward_for_user
        from django.core import mail
        from notifications.models import Notification

        # Process referral reward
        result = process_referral_reward_for_user(self.friend)
        self.assertTrue(result)

        # Refresh from database
        self.referrer.refresh_from_db()
        self.friend.refresh_from_db()

        # 1. Referrer earned the reward ($10)
        self.assertEqual(float(self.referrer.balance), 10.00)

        # 2. Friend earned 0 points / $0 balance
        self.assertEqual(float(self.friend.balance), 0.00)

        # 3. Friend is marked as reward awarded (to prevent re-awarding)
        self.assertTrue(self.friend.has_referral_reward_awarded)

        # 4. Notifications: Only REFERRAL_REWARD sent to referrer, none to friend
        referrer_notifs = Notification.objects.filter(user=self.referrer, notification_type='REFERRAL_REWARD')
        friend_notifs = Notification.objects.filter(user=self.friend, notification_type='REFERRAL_REWARD')
        self.assertEqual(referrer_notifs.count(), 1)
        self.assertEqual(friend_notifs.count(), 0)

        # 5. Emails: Referral reward email only sent to referrer
        referral_emails = [m for m in mail.outbox if "referral reward" in m.subject.lower()]
        self.assertEqual(len(referral_emails), 1)
        self.assertEqual(referral_emails[0].to, ["referrer@example.com"])
        self.assertIn("You've earned a referral reward!", referral_emails[0].subject)

        # 6. Secondary attempt should not re-award
        second_result = process_referral_reward_for_user(self.friend)
        self.assertFalse(second_result)
        self.referrer.refresh_from_db()
        self.assertEqual(float(self.referrer.balance), 10.00)



