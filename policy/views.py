import time
from rest_framework.views import APIView
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser

from policy.models import (
    Privacy_Policy, Cookie_Policy, Terms_Of_Service, Review,
    EMI_Payment_Policy, Warranty_Policy, Exchange_Policy,
    Delivery_Policy, PreOrder_Policy, Refund_Policy, Return_Policy
)
from policy.serializers import (
    PrivacyPolicySerializer, CookiePolicySerializer,
    TermsOfServiceSerializer, ReviewSerializer,
    EMIPaymentPolicySerializer, WarrantyPolicySerializer,
    ExchangePolicySerializer, DeliveryPolicySerializer,
    PreOrderPolicySerializer, RefundPolicySerializer,
    ReturnPolicySerializer
)

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
    # permission_classes = [IsAdminUser]  

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
    # permission_classes = [IsAdminUser]  

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
    # permission_classes = [IsAdminUser]  

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
    model            = None
    serializer_class = None
    policy_name      = "Policy"

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
    model            = EMI_Payment_Policy
    serializer_class = EMIPaymentPolicySerializer
    policy_name      = "EMI & Payment Policy"


# ==========================
# Warranty Policy View
# ==========================
class WarrantyPolicyView(PolicyGetBaseView):
    model            = Warranty_Policy
    serializer_class = WarrantyPolicySerializer
    policy_name      = "Warranty Policy"


# ==========================
# Exchange Policy View
# ==========================
class ExchangePolicyView(PolicyGetBaseView):
    model            = Exchange_Policy
    serializer_class = ExchangePolicySerializer
    policy_name      = "Exchange Policy"


# ==========================
# Delivery Policy View
# ==========================
class DeliveryPolicyView(PolicyGetBaseView):
    model            = Delivery_Policy
    serializer_class = DeliveryPolicySerializer
    policy_name      = "Delivery Policy"


# ==========================
# Pre-Order Policy View
# ==========================
class PreOrderPolicyView(PolicyGetBaseView):
    model            = PreOrder_Policy
    serializer_class = PreOrderPolicySerializer
    policy_name      = "Pre-Order Policy"


# ==========================
# Refund Policy View
# ==========================
class RefundPolicyView(PolicyGetBaseView):
    model            = Refund_Policy
    serializer_class = RefundPolicySerializer
    policy_name      = "Refund Policy"


# ==========================
# Return Policy View
# ==========================
class ReturnPolicyView(PolicyGetBaseView):
    model            = Return_Policy
    serializer_class = ReturnPolicySerializer
    policy_name      = "Return Policy"

class ReviewView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        reviews = Review.objects.all().order_by('-created_at')
        serializer = ReviewSerializer(reviews, many=True)
        return api_response(
            success=True,
            code=status.HTTP_200_OK,
            message="Reviews retrieved successfully.",
            data=serializer.data
        ) 
    
    def post(self, request):
        serializer = ReviewSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return api_response(
                success=True,
                code=status.HTTP_201_CREATED,
                message="Review created successfully.",
                data=serializer.data
            )

        return api_response(
            success=False,
            code=status.HTTP_400_BAD_REQUEST,
            message="Validation error.",
            data=serializer.errors
        )