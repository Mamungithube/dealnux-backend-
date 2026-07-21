from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from api_integration.models import Category
from store.models import SellerRequest

User = get_user_model()


class SellerRequestAPITestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='seller@example.com',
            password='Password123!'
        )
        self.category = Category.objects.create(
            name='Electronics',
            slug='electronics'
        )
        self.client.force_authenticate(user=self.user)
        self.url = '/api/v1/store/seller-requests/'

    def test_create_seller_request_with_agree_return_policy(self):
        data = {
            "trade_name": "Tech Store",
            "legal_business_type": "Sole Proprietorship",
            "business_reg_number": "12345",
            "contact_full_name": "John Doe",
            "job_title": "Owner",
            "contact_email": "john@example.com",
            "contact_phone": "+1234567890",
            "category_names": ["Electronics"],
            "estimated_sku_count": "100",
            "min_price": "10.00",
            "max_price": "500.00",
            "owns_inventory": True,
            "agree_return_policy": True,
            "agreed_to_compliance": True,
            "agreed_to_prohibited_items": True,
            "agreed_to_seller_agreement": True,
            "agreed_to_terms": True,
            "agreed_to_privacy": True,
            "digital_signature": "John Doe"
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        
        resp_data = response.data['data']
        self.assertIn('agree_return_policy', resp_data)
        self.assertTrue(resp_data['agree_return_policy'])
        self.assertNotIn('return_policy_description', resp_data)
        self.assertNotIn('return_policy_document', resp_data)

        # Verify database object
        seller_req = SellerRequest.objects.get(user=self.user)
        self.assertTrue(seller_req.agree_return_policy)

    def test_seller_request_status_endpoint(self):
        SellerRequest.objects.create(
            user=self.user,
            trade_name="Tech Store",
            agree_return_policy=True,
            agreed_to_seller_agreement=True,
            agreed_to_terms=True,
            agreed_to_privacy=True
        )
        status_url = '/api/v1/store/seller-requests/status/'
        response = self.client.get(status_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        resp_data = response.data['data']
        self.assertIn('agree_return_policy', resp_data)
        self.assertTrue(resp_data['agree_return_policy'])

