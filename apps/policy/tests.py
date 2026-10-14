from django.test import TestCase, override_settings
from django.urls import reverse
from django.core import mail
from rest_framework.test import APIClient
from rest_framework import status
from policy.models import ContactMessage


class ContactMessageTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse('contact-send')

    @override_settings(ADMIN_EMAIL='admin@dealnux.com', DEFAULT_FROM_EMAIL='noreply@dealnux.shop')
    def test_contact_form_submission_and_email_flow(self):
        data = {
            "full_name": "Jane Doe",
            "email": "janedoe@example.com",
            "subject": "Order Tracking Inquiry",
            "message": "Hello, I would like to inquire about my order status."
        }

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("ticket_id", response.data)
        ticket_id = response.data["ticket_id"]
        self.assertTrue(ticket_id.startswith("DNX-"))

        # Verify DB entry
        contact_msg = ContactMessage.objects.get(ticket_id=ticket_id)
        self.assertEqual(contact_msg.full_name, "Jane Doe")
        self.assertEqual(contact_msg.email, "janedoe@example.com")
        self.assertEqual(contact_msg.subject, "Order Tracking Inquiry")
        self.assertEqual(contact_msg.message, "Hello, I would like to inquire about my order status.")

        # Verify 2 emails sent
        self.assertEqual(len(mail.outbox), 2)

        # 1. Admin email
        admin_email = mail.outbox[0]
        self.assertEqual(admin_email.to, ["admin@dealnux.com"])
        self.assertEqual(admin_email.reply_to, ["janedoe@example.com"])
        self.assertEqual(admin_email.subject, f"[{ticket_id}] New Contact: Order Tracking Inquiry")
        self.assertIn("New contact message received!", admin_email.body)
        self.assertIn(f"Ticket ID   : {ticket_id}", admin_email.body)
        self.assertIn("Name        : Jane Doe", admin_email.body)
        self.assertIn("Email       : janedoe@example.com", admin_email.body)
        self.assertIn("Subject     : Order Tracking Inquiry", admin_email.body)
        self.assertIn("Hello, I would like to inquire about my order status.", admin_email.body)

        # 2. User confirmation email
        user_email = mail.outbox[1]
        self.assertEqual(user_email.to, ["janedoe@example.com"])
        self.assertEqual(user_email.subject, f"[{ticket_id}] We’ve received your message | DealNux Support.")
        self.assertIn("Thank you for contacting DealNux.", user_email.body)
        self.assertIn(f"Ticket ID: {ticket_id}", user_email.body)
        self.assertIn("Subject: Order Tracking Inquiry", user_email.body)
        self.assertIn("Please keep your Ticket ID for reference if you need to follow up.", user_email.body)
        self.assertIn("Thank you for choosing DealNux.", user_email.body)
        self.assertIn("DealNux Admin", user_email.body)
        self.assertIn("SHOP SMARTER. SAVE BIGGER.", user_email.body)
        self.assertIn("www.dealnux.shop", user_email.body)
