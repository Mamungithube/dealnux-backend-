import time
from datetime import timedelta
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken

from account.models import User, Profile
from account.serializers import (
    ProfileSerializer,
    ProfileUpdateSerializer,
    ProfileSetupSerializer,
)
from account.services import (
    send_otp_email,
    delete_user_account,
    complete_profile_setup,
    get_user_account_statuses,
)
from payment.models import SubscriptionPlan, UserSubscription


# ======================== Free Trial Logic (for payment/models.py) ========================
def start_free_trial(user):
    try:
        free_plan = SubscriptionPlan.objects.get(plan_type='FREE')
        trial_duration = free_plan.trial_days

        UserSubscription.objects.create(
            user=user,
            plan=free_plan,
            status='TRIAL',
            trial_ends_at=timezone.now() + timedelta(days=trial_duration),
            expires_at=timezone.now() + timedelta(days=trial_duration)
        )
    except SubscriptionPlan.DoesNotExist:
        pass


# -------------------------- Initial Profile Setup View (Post-Signup Onboarding) --------------------------
class ProfileSetupView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email')

        if not email:
            return Response({
                "success": False,
                "code": status.HTTP_400_BAD_REQUEST,
                "message": "Email is required.",
                "timestamp": int(time.time()),
                "data": {"email": ["This field is required."]}
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({
                "success": False,
                "code": status.HTTP_404_NOT_FOUND,
                "message": "User not found.",
                "timestamp": int(time.time()),
                "data": {"email": ["No user found with this email."]}
            }, status=status.HTTP_404_NOT_FOUND)

        if not user.is_active:
            return Response({
                "success": False,
                "code": status.HTTP_403_FORBIDDEN,
                "message": "Please verify your OTP first.",
                "timestamp": int(time.time()),
                "data": {}
            }, status=status.HTTP_403_FORBIDDEN)

        if user.profile_setup_completed:
            return Response({
                "success": False,
                "code": status.HTTP_400_BAD_REQUEST,
                "message": "Profile setup already completed. Please login to update your profile.",
                "timestamp": int(time.time()),
                "data": {}
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = ProfileSetupSerializer(data=request.data)

        if not serializer.is_valid():
            return Response({
                "success": False,
                "code": status.HTTP_400_BAD_REQUEST,
                "message": "Invalid input.",
                "timestamp": int(time.time()),
                "data": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            success, message, profile, errors = complete_profile_setup(user, serializer.validated_data)
            if not success:
                return Response({
                    "success": False,
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": message,
                    "timestamp": int(time.time()),
                    "data": errors or {}
                }, status=status.HTTP_400_BAD_REQUEST)

            profile_data = ProfileSerializer(profile).data
            refresh = RefreshToken.for_user(user)

            return Response({
                "success": True,
                "code": status.HTTP_201_CREATED,
                "message": message,
                "timestamp": int(time.time()),
                "data": {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                    "profile": profile_data
                }
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({
                "success": False,
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "Failed to setup profile.",
                "timestamp": int(time.time()),
                "data": {"detail": [str(e)]}
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# -------------------------- User Profile Details View (Retrieve Auth User Profile & Statuses) --------------------------
class ProfileDetailsView(generics.RetrieveAPIView):
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        profile, created = Profile.objects.get_or_create(
            user=self.request.user)
        return profile

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        account_statuses = get_user_account_statuses(request.user)

        return Response(
            {
                "success": True,
                "code": status.HTTP_200_OK,
                "message": "Profile retrieved successfully.",
                "timestamp": int(time.time()),
                "data": {
                    **serializer.data,
                    **account_statuses,
                }
            },
            status=status.HTTP_200_OK
        )


# -------------------------- User Profile Update View (Partial/Full Update) --------------------------
class ProfileUpdateView(generics.UpdateAPIView):
    serializer_class = ProfileUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        profile, created = Profile.objects.get_or_create(
            user=self.request.user)
        return profile

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data=request.data, partial=partial)

        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "Invalid input.",
                    "timestamp": int(time.time()),
                    "data": serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        self.perform_update(serializer)

        profile_serializer = ProfileSerializer(
            instance, context=self.get_serializer_context())
        return Response(
            {
                "success": True,
                "code": status.HTTP_200_OK,
                "message": "Profile updated successfully.",
                "timestamp": int(time.time()),
                "data": profile_serializer.data
            },
            status=status.HTTP_200_OK
        )


# -------------------------- Send Account Deletion OTP View (Authenticated User) --------------------------
class SendDeleteAccountOTPView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        try:
            send_otp_email(
                user,
                user.email,
                subject="Account Deletion Verification Code - DealNux"
            )
            return Response(
                {
                    "success": True,
                    "code": status.HTTP_200_OK,
                    "message": "Verification code has been sent to your email address.",
                    "timestamp": int(time.time()),
                    "data": {
                        "email": user.email
                    }
                },
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Failed to send verification code. Please try again later.",
                    "timestamp": int(time.time()),
                    "data": {"error": str(e)}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# -------------------------- Permanent Account Deletion View (Password/OTP Confirmed) --------------------------
class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def _perform_delete(self, request):
        data = request.data if hasattr(request, 'data') and request.data else {}
        success, message, errors, code = delete_user_account(request.user, data)
        return Response(
            {
                "success": success,
                "code": code,
                "message": message,
                "timestamp": int(time.time()),
                "data": errors if errors else {}
            },
            status=code
        )

    def delete(self, request, *args, **kwargs):
        return self._perform_delete(request)

    def post(self, request, *args, **kwargs):
        return self._perform_delete(request)
