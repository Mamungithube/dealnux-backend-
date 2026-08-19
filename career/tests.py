from django.test import TestCase
from django.urls import reverse
from django.core import mail
from rest_framework.test import APIClient
from rest_framework import status
from career.models import CareerApplication


class CareerApplicationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.apply_url = reverse('career-apply')
        self.roles_url = reverse('career-roles')

    def test_get_career_roles_list(self):
        response = self.client.get(self.roles_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        roles = [r["value"] for r in response.data.get("roles", [])]
        expected_roles = [
            "Product Manager",
            "Data Analyst",
            "Digital Marketing Specialist",
            "Customer Support Specialist",
            "Sales Executive",
            "Other",
        ]
        for role in expected_roles:
            self.assertIn(role, roles)

    def test_submit_application_with_new_roles(self):
        test_roles = [
            "Product Manager",
            "Data Analyst",
            "Digital Marketing Specialist",
            "Customer Support Specialist",
            "Sales Executive",
            "Other",
        ]

        for idx, role in enumerate(test_roles, start=1):
            data = {
                "full_name": f"Applicant {idx}",
                "email": f"applicant{idx}@example.com",
                "phone": "+1234567890",
                "role": role,
                "experience": "5 years of experience in this domain.",
                "why_join": "Passionate about DealNux.",
            }
            response = self.client.post(self.apply_url, data, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, f"Failed for {role}: {response.data}")
            self.assertTrue(
                CareerApplication.objects.filter(email=f"applicant{idx}@example.com", role=role).exists()
            )

        # Check notification email dispatched
        self.assertEqual(len(mail.outbox), len(test_roles))
        self.assertIn("[DealNux] New Career Application", mail.outbox[0].subject)
