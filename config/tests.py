from django.test import TestCase, Client
from django.urls import reverse
from rest_framework import status


class HealthCheckEndpointTests(TestCase):
    """Test suite for System Health Check Endpoints."""

    def setUp(self):
        self.client = Client()

    def test_lightweight_health_check(self):
        """Test lightweight /health/ ping returns HTTP 200 OK and healthy status."""
        response = self.client.get('/health/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data.get('status'), 'healthy')
        self.assertIn('timestamp', data)
        self.assertIn('services', data)
        self.assertEqual(data['services'].get('api'), 'ok')

    def test_full_health_check(self):
        """Test /health/?full=true returns detailed infrastructure status."""
        response = self.client.get('/health/?full=true')
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE])
        data = response.json()
        self.assertIn('status', data)
        self.assertIn('services', data)
        # Verify database check key exists in deep health check
        self.assertIn('database', data['services'])
