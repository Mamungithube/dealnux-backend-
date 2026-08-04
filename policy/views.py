from .serializers import ContactMessageSerializer
from .models import ContactMessage
from django.conf import settings
from django.core.mail import send_mail
from rest_framework import generics, permissions, status
import time
from rest_framework.views import APIView
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser

from policy.models import (
    Privacy_Policy, Cookie_Policy, Terms_Of_Service, Review,
    EMI_Payment_Policy, Warranty_Policy, Exchange_Policy,
    Delivery_Policy, PreOrder_Policy, Refund_Policy, Return_Policy, About_Us,
    Seller_Policy, Buyer_Protection_Policy, Prohibited_Products_Policy,
    Intellectual_Property_Policy, Community_Guidelines
)
from policy.serializers import (
    PrivacyPolicySerializer, CookiePolicySerializer,
    TermsOfServiceSerializer, ReviewSerializer,
    EMIPaymentPolicySerializer, WarrantyPolicySerializer,
    ExchangePolicySerializer, DeliveryPolicySerializer,
    PreOrderPolicySerializer, RefundPolicySerializer,
    ReturnPolicySerializer, AboutUsSerializer,
    SellerPolicySerializer, BuyerProtectionPolicySerializer,
    ProhibitedProductsPolicySerializer, IntellectualPropertyPolicySerializer,
    CommunityGuidelinesSerializer
)
from django.core.mail import EmailMessage
from django.utils import timezone
from rest_framework.permissions import AllowAny
# 🔹 Common API Response


def api_response(*, success: bool, code: int, message: str, data=None):
    return Response(
        {
            "success": success,
            "code": code,
            "message": message,
            "timestamp": int(time.time()),
            "data": data
        },
        status=code
    )


# ==========================
# Privacy Policy View
# ==========================
class PrivacyPolicyView(APIView):
    def get_permissions(self):
        # Allow anyone to read (GET); only admins can create/update/delete
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.AllowAny()]
        return [IsAdminUser()]

    def get(self, request):
        policy = Privacy_Policy.objects.first()
        if not policy:
            return api_response(
                success=False,
                code=status.HTTP_404_NOT_FOUND,
                message="Privacy policy not found.",
                data=None
            )

        serializer = PrivacyPolicySerializer(policy)
        return api_response(
            success=True,
            code=status.HTTP_200_OK,
            message="Privacy policy retrieved successfully.",
            data=serializer.data
        )

    def post(self, request):
        serializer = PrivacyPolicySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return api_response(
                success=True,
                code=status.HTTP_201_CREATED,
                message="Privacy policy created successfully.",
                data=serializer.data
            )

        return api_response(
            success=False,
            code=status.HTTP_400_BAD_REQUEST,
            message="Validation error.",
            data=serializer.errors
        )

    def put(self, request):
        policy = Privacy_Policy.objects.first()
        if not policy:
            return api_response(
                success=False,
                code=status.HTTP_404_NOT_FOUND,
                message="Privacy policy not found.",
                data=None
            )

        serializer = PrivacyPolicySerializer(policy, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return api_response(
                success=True,
                code=status.HTTP_200_OK,
                message="Privacy policy updated successfully.",
                data=serializer.data
            )

        return api_response(
            success=False,
            code=status.HTTP_400_BAD_REQUEST,
            message="Validation error.",
            data=serializer.errors
        )

    def delete(self, request):
        policy = Privacy_Policy.objects.first()
        if policy:
            policy.delete()

        return api_response(
            success=True,
            code=status.HTTP_204_NO_CONTENT,
            message="Privacy policy deleted successfully.",
            data=None
        )


# ==========================
# Cookie Policy View
# ==========================
class CookiePolicyView(APIView):
    def get_permissions(self):
        # Allow anyone to read (GET); only admins can create/update/delete
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.AllowAny()]
        return [IsAdminUser()]

    def get(self, request):
        policy = Cookie_Policy.objects.first()
        if not policy:
            return api_response(
                success=False,
                code=status.HTTP_404_NOT_FOUND,
                message="Cookie policy not found.",
                data=None
            )

        serializer = CookiePolicySerializer(policy)
        return api_response(
            success=True,
            code=status.HTTP_200_OK,
            message="Cookie policy retrieved successfully.",
            data=serializer.data
        )

    def post(self, request):
        serializer = CookiePolicySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return api_response(
                success=True,
                code=status.HTTP_201_CREATED,
                message="Cookie policy created successfully.",
                data=serializer.data
            )

        return api_response(
            success=False,
            code=status.HTTP_400_BAD_REQUEST,
            message="Validation error.",
            data=serializer.errors
        )

    def put(self, request):
        policy = Cookie_Policy.objects.first()
        if not policy:
            return api_response(
                success=False,
                code=status.HTTP_404_NOT_FOUND,
                message="Cookie policy not found.",
                data=None
            )

        serializer = CookiePolicySerializer(policy, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return api_response(
                success=True,
                code=status.HTTP_200_OK,
                message="Cookie policy updated successfully.",
                data=serializer.data
            )

        return api_response(
            success=False,
            code=status.HTTP_400_BAD_REQUEST,
            message="Validation error.",
            data=serializer.errors
        )

    def delete(self, request):
        policy = Cookie_Policy.objects.first()
        if policy:
            policy.delete()

        return api_response(
            success=True,
            code=status.HTTP_204_NO_CONTENT,
            message="Cookie policy deleted successfully.",
            data=None
        )


# ==========================
# Terms Of Service View
# ==========================
class TermsOfServiceView(APIView):
    def get_permissions(self):
        # Allow anyone to read (GET); only admins can create/update/delete
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.AllowAny()]
        return [IsAdminUser()]

    def get(self, request):
        policy = Terms_Of_Service.objects.first()
        if not policy:
            return api_response(
                success=False,
                code=status.HTTP_404_NOT_FOUND,
                message="Terms of service not found.",
                data=None
            )

        serializer = TermsOfServiceSerializer(policy)
        return api_response(
            success=True,
            code=status.HTTP_200_OK,
            message="Terms of service retrieved successfully.",
            data=serializer.data
        )

    def post(self, request):
        serializer = TermsOfServiceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return api_response(
                success=True,
                code=status.HTTP_201_CREATED,
                message="Terms of service created successfully.",
                data=serializer.data
            )

        return api_response(
            success=False,
            code=status.HTTP_400_BAD_REQUEST,
            message="Validation error.",
            data=serializer.errors
        )

    def put(self, request):
        policy = Terms_Of_Service.objects.first()
        if not policy:
            return api_response(
                success=False,
                code=status.HTTP_404_NOT_FOUND,
                message="Terms of service not found.",
                data=None
            )

        serializer = TermsOfServiceSerializer(policy, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return api_response(
                success=True,
                code=status.HTTP_200_OK,
                message="Terms of service updated successfully.",
                data=serializer.data
            )

        return api_response(
            success=False,
            code=status.HTTP_400_BAD_REQUEST,
            message="Validation error.",
            data=serializer.errors
        )

    def delete(self, request):
        policy = Terms_Of_Service.objects.first()
        if policy:
            policy.delete()

        return api_response(
            success=True,
            code=status.HTTP_204_NO_CONTENT,
            message="Terms of service deleted successfully.",
            data=None
        )


# ==========================
# Reusable GET-Only Base View
# ==========================
class PolicyGetBaseView(APIView):
    """
    Reusable base view for GET-only policy endpoints.
    Subclasses must define: model, serializer_class, policy_name
    """
    model = None
    serializer_class = None
    policy_name = "Policy"

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        policy = self.model.objects.first()
        if not policy:
            return api_response(
                success=False,
                code=status.HTTP_404_NOT_FOUND,
                message=f"{self.policy_name} not found.",
                data=None
            )
        serializer = self.serializer_class(policy)
        return api_response(
            success=True,
            code=status.HTTP_200_OK,
            message=f"{self.policy_name} retrieved successfully.",
            data=serializer.data
        )


# ==========================
# EMI & Payment Policy View
# ==========================
class EMIPaymentPolicyView(PolicyGetBaseView):
    model = EMI_Payment_Policy
    serializer_class = EMIPaymentPolicySerializer
    policy_name = "EMI & Payment Policy"


# ==========================
# Warranty Policy View
# ==========================
class WarrantyPolicyView(PolicyGetBaseView):
    model = Warranty_Policy
    serializer_class = WarrantyPolicySerializer
    policy_name = "Warranty Policy"


# ==========================
# Exchange Policy View
# ==========================
class ExchangePolicyView(PolicyGetBaseView):
    model = Exchange_Policy
    serializer_class = ExchangePolicySerializer
    policy_name = "Exchange Policy"


# ==========================
# Delivery Policy View
# ==========================
class DeliveryPolicyView(PolicyGetBaseView):
    model = Delivery_Policy
    serializer_class = DeliveryPolicySerializer
    policy_name = "Delivery Policy"


# ==========================
# Pre-Order Policy View
# ==========================
class PreOrderPolicyView(PolicyGetBaseView):
    model = PreOrder_Policy
    serializer_class = PreOrderPolicySerializer
    policy_name = "Pre-Order Policy"


# ==========================
# Refund Policy View
# ==========================
class RefundPolicyView(PolicyGetBaseView):
    model = Refund_Policy
    serializer_class = RefundPolicySerializer
    policy_name = "Refund Policy"


# ==========================
# Return Policy View
# ==========================
class ReturnPolicyView(PolicyGetBaseView):
    model = Return_Policy
    serializer_class = ReturnPolicySerializer
    policy_name = "Return Policy"


# ==========================
# Seller Policy View
# ==========================
class SellerPolicyView(PolicyGetBaseView):
    model = Seller_Policy
    serializer_class = SellerPolicySerializer
    policy_name = "Seller Policy"


# ==========================
# Buyer Protection Policy View
# ==========================
class BuyerProtectionPolicyView(PolicyGetBaseView):
    model = Buyer_Protection_Policy
    serializer_class = BuyerProtectionPolicySerializer
    policy_name = "Buyer Protection Policy"


# ==========================
# Prohibited Products Policy View
# ==========================
class ProhibitedProductsPolicyView(PolicyGetBaseView):
    model = Prohibited_Products_Policy
    serializer_class = ProhibitedProductsPolicySerializer
    policy_name = "Prohibited Products Policy"


# ==========================
# Intellectual Property Policy View
# ==========================
class IntellectualPropertyPolicyView(PolicyGetBaseView):
    model = Intellectual_Property_Policy
    serializer_class = IntellectualPropertyPolicySerializer
    policy_name = "Intellectual Property Policy"


# ==========================
# Community Guidelines View
# ==========================
class CommunityGuidelinesView(PolicyGetBaseView):
    model = Community_Guidelines
    serializer_class = CommunityGuidelinesSerializer
    policy_name = "Community Guidelines"


# ==========================
# About Us View
# ==========================
class AboutUsView(PolicyGetBaseView):
    model = About_Us
    serializer_class = AboutUsSerializer
    policy_name = "About Us"

from django.db import IntegrityError, transaction
import logging

logger = logging.getLogger(__name__)


class ReviewView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            reviews = Review.objects.all().order_by('-created_at')
            serializer = ReviewSerializer(reviews, many=True)
            return api_response(
                success=True,
                code=status.HTTP_200_OK,
                message="Reviews retrieved successfully.",
                data=serializer.data
            )
        except Exception as e:
            logger.error(f"Error fetching reviews: {str(e)}")
            return api_response(
                success=False,
                code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                message="Something went wrong while fetching reviews.",
                data=None
            )

    def post(self, request):
        try:
            existing_review = Review.objects.filter(user=request.user).first()

            if existing_review:
                serializer = ReviewSerializer(existing_review, data=request.data, partial=True)
                message = "Review updated successfully."
                success_code = status.HTTP_200_OK
            else:
                serializer = ReviewSerializer(data=request.data)
                message = "Review created successfully."
                success_code = status.HTTP_201_CREATED

            if not serializer.is_valid():
                return api_response(
                    success=False,
                    code=status.HTTP_400_BAD_REQUEST,
                    message="Validation error.",
                    data=serializer.errors
                )

            # race condition guard: দুইটা রিকোয়েস্ট একসাথে এলে DB constraint যাতে crash না করে
            with transaction.atomic():
                serializer.save(user=request.user)

            return api_response(
                success=True,
                code=success_code,
                message=message,
                data=serializer.data
            )

        except IntegrityError as e:
            logger.warning(f"Review IntegrityError for user {request.user.id}: {str(e)}")
            return api_response(
                success=False,
                code=status.HTTP_400_BAD_REQUEST,
                message="You have already submitted a review.",
                data=None
            )

        except Exception as e:
            logger.error(f"Unexpected error creating review for user {request.user.id}: {str(e)}")
            return api_response(
                success=False,
                code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                message="Something went wrong. Please try again later.",
                data=None
            )

class ContactMessageCreateView(generics.CreateAPIView):
    serializer_class = ContactMessageSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        contact = serializer.save()

        # Admin email
        try:
            admin_email = EmailMessage(
                subject=f"[{contact.ticket_id}] New Contact: {contact.subject}",
                body=f"""New contact message received!

Ticket  : {contact.ticket_id}
Name    : {contact.full_name}
Email   : {contact.email}
Subject : {contact.subject}

Message:
{contact.message}

Received At: {contact.created_at}""",
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[settings.ADMIN_EMAIL],
                reply_to=[contact.email],
            )
            admin_email.send(fail_silently=True)
        except Exception:
            pass

        # User confirmation email
        try:
            user_email = EmailMessage(
                subject=f"[{contact.ticket_id}] We received your message - Dealnux",
                body=f"""Hi {contact.full_name},

Thank you for contacting us! We have received your message.

Your Ticket ID : {contact.ticket_id}
Subject        : {contact.subject}

We'll get back to you within one business day.

Team Dealnux""",
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[contact.email],
            )
            user_email.send(fail_silently=True)
        except Exception:
            pass

        return Response(
            {
                "detail": "Message sent successfully. We'll reply within one business day.",
                "ticket_id": contact.ticket_id,
            },
            status=status.HTTP_201_CREATED
        )




class ContactMessageListView(generics.ListAPIView):
    serializer_class = ContactMessageSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = ContactMessage.objects.all()


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.utils import timezone
import time

class CookieConsentView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        preferences = request.data
        
        if request.user.is_authenticated:
            user = request.user
            user.cookie_preferences = preferences
            user.cookie_consent_date = timezone.now()
            user.save()
            return Response({
                "success": True, 
                "type": "authenticated", 
                "timestamp": int(time.time()),
                "data": preferences
            })

        else:
            return Response({
                "success": True, 
                "type": "guest",
                "timestamp": int(time.time()),
                "message": "Consent received. Frontend should store this in LocalStorage/Cookie."
            })