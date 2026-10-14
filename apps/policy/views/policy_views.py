from rest_framework.views import APIView
from rest_framework import permissions, status
from rest_framework.permissions import IsAdminUser

from policy.models import (
    Privacy_Policy, Cookie_Policy, Terms_Of_Service,
    EMI_Payment_Policy, Warranty_Policy, Exchange_Policy,
    Delivery_Policy, PreOrder_Policy, Refund_Policy, Return_Policy,
    Seller_Policy, Buyer_Protection_Policy, Prohibited_Products_Policy,
    Intellectual_Property_Policy, Community_Guidelines, About_Us
)
from policy.serializers import (
    PrivacyPolicySerializer, CookiePolicySerializer,
    TermsOfServiceSerializer,
    EMIPaymentPolicySerializer, WarrantyPolicySerializer,
    ExchangePolicySerializer, DeliveryPolicySerializer,
    PreOrderPolicySerializer, RefundPolicySerializer,
    ReturnPolicySerializer, AboutUsSerializer,
    SellerPolicySerializer, BuyerProtectionPolicySerializer,
    ProhibitedProductsPolicySerializer, IntellectualPropertyPolicySerializer,
    CommunityGuidelinesSerializer
)
from .base import api_response, PolicyGetBaseView


# -------------------------- Privacy Policy View (Public Read, Admin Write) --------------------------
class PrivacyPolicyView(APIView):
    def get_permissions(self):
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


# -------------------------- Cookie Policy View (Public Read, Admin Write) --------------------------
class CookiePolicyView(APIView):
    def get_permissions(self):
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


# -------------------------- Terms of Service View (Public Read, Admin Write) --------------------------
class TermsOfServiceView(APIView):
    def get_permissions(self):
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


# -------------------------- Public GET-Only Policy Views --------------------------
class EMIPaymentPolicyView(PolicyGetBaseView):
    model = EMI_Payment_Policy
    serializer_class = EMIPaymentPolicySerializer
    policy_name = "EMI & Payment Policy"


class WarrantyPolicyView(PolicyGetBaseView):
    model = Warranty_Policy
    serializer_class = WarrantyPolicySerializer
    policy_name = "Warranty Policy"


class ExchangePolicyView(PolicyGetBaseView):
    model = Exchange_Policy
    serializer_class = ExchangePolicySerializer
    policy_name = "Exchange Policy"


class DeliveryPolicyView(PolicyGetBaseView):
    model = Delivery_Policy
    serializer_class = DeliveryPolicySerializer
    policy_name = "Delivery Policy"


class PreOrderPolicyView(PolicyGetBaseView):
    model = PreOrder_Policy
    serializer_class = PreOrderPolicySerializer
    policy_name = "Pre-Order Policy"


class RefundPolicyView(PolicyGetBaseView):
    model = Refund_Policy
    serializer_class = RefundPolicySerializer
    policy_name = "Refund Policy"


class ReturnPolicyView(PolicyGetBaseView):
    model = Return_Policy
    serializer_class = ReturnPolicySerializer
    policy_name = "Return Policy"


class SellerPolicyView(PolicyGetBaseView):
    model = Seller_Policy
    serializer_class = SellerPolicySerializer
    policy_name = "Seller Policy"


class BuyerProtectionPolicyView(PolicyGetBaseView):
    model = Buyer_Protection_Policy
    serializer_class = BuyerProtectionPolicySerializer
    policy_name = "Buyer Protection Policy"


class ProhibitedProductsPolicyView(PolicyGetBaseView):
    model = Prohibited_Products_Policy
    serializer_class = ProhibitedProductsPolicySerializer
    policy_name = "Prohibited Products Policy"


class IntellectualPropertyPolicyView(PolicyGetBaseView):
    model = Intellectual_Property_Policy
    serializer_class = IntellectualPropertyPolicySerializer
    policy_name = "Intellectual Property Policy"


class CommunityGuidelinesView(PolicyGetBaseView):
    model = Community_Guidelines
    serializer_class = CommunityGuidelinesSerializer
    policy_name = "Community Guidelines"


class AboutUsView(PolicyGetBaseView):
    model = About_Us
    serializer_class = AboutUsSerializer
    policy_name = "About Us"
