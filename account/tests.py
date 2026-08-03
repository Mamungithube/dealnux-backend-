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


