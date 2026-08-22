from django.test import TestCase
from rest_framework.test import APIClient
from account.models import User
from api_integration.models import Category, Platform, Product, ProductListing
from notifications.models import Notification
from notifications.tasks import send_daily_ai_recommendations


class ProductAndRecommendationTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user, _ = User.objects.get_or_create(
            email='testuser@dealnux.shop',
            defaults={
                'name': 'Test User',
                'is_active': True
            }
        )
        self.category, _ = Category.objects.get_or_create(slug='electronics', defaults={'name': 'Electronics'})
        self.platform, _ = Platform.objects.get_or_create(code='amazon', defaults={'name': 'Amazon'})

        self.product, _ = Product.objects.get_or_create(
            slug='apple-iphone-15-pro-max-256gb',
            defaults={
                'title': 'Apple iPhone 15 Pro Max 256GB',
                'category': self.category,
                'brand': 'Apple',
                'is_active': True
            }
        )

        self.listing, _ = ProductListing.objects.get_or_create(
            platform=self.platform,
            external_id='amazon-iphone-15-123',
            defaults={
                'product': self.product,
                'price': 1099.99,
                'original_price': 1199.99,
                'discount_percentage': 8.33,
                'is_available': True
            }
        )

    def test_product_detail_lookup_by_numeric_id(self):
        """Test looking up a product by numeric ID /api/v1/fetch-products/products/<id>/ (Fix for client bug)."""
        response = self.client.get(f"/api/v1/fetch-products/products/{self.product.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], self.product.id)
        self.assertEqual(response.data['title'], 'Apple iPhone 15 Pro Max 256GB')
        self.assertEqual(response.data['price'], 1099.99)

    def test_product_detail_lookup_by_slug(self):
        """Test looking up a product by slug /api/v1/fetch-products/products/<slug>/."""
        response = self.client.get(f"/api/v1/fetch-products/products/{self.product.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], self.product.id)
        self.assertEqual(response.data['slug'], 'apple-iphone-15-pro-max-256gb')

    def test_send_daily_ai_recommendations_and_cta_link(self):
        """Test that AI recommendation creates notification and CTA link loads product without 404."""
        result = send_daily_ai_recommendations()
        self.assertIn("Sent to 1 users", result)

        notification = Notification.objects.filter(
            user=self.user,
            notification_type='AI_RECOMMENDATION'
        ).first()

        self.assertIsNotNone(notification)
        self.assertTrue(notification.cta_link.startswith("/product/"))

        # Extract param from /product/<param>
        param = notification.cta_link.replace('/product/', '').strip('/')
        # Verify the backend API call resolves successfully
        api_res = self.client.get(f"/api/v1/fetch-products/products/{param}/")
        self.assertEqual(api_res.status_code, 200)
        self.assertEqual(api_res.data['id'], self.product.id)
