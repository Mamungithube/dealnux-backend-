from django.shortcuts import render
from rest_framework.permissions import IsAdminUser
from rest_framework import viewsets

from store.models import SellerRequest
from .serializers import (UserSerializer, RegisterSerializer, UserLoginSerializer, ChangePasswordSerializer, ResetPasswordSerializer,
                         LoginSerializer, ProfileSerializer, ProfileUpdateSerializer, ProfileSetupSerializer)
from .models import User, Profile
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth import login
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.mail import EmailMessage
from django.conf import settings
from django.template.loader import render_to_string
from rest_framework import generics, permissions
from django.db import transaction
import random
import json
import time
from custom_ads.models import AdvertiserRequest


def generate_otp():
    return str(random.randint(1000, 9999))


# Create your views here.

class UserAPIView(viewsets.ModelViewSet):
    http_method_names = ['get', 'post', 'put', 'delete']
    permission_classes = [IsAdminUser]
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


"""--------------------Register View---------------------"""


class RegisterApiView(APIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        if not request.data:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "Request body cannot be empty.",
                    "timestamp": int(time.time()),
                    "data": {}
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "user already exists.",
                    "timestamp": int(time.time()),
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = serializer.save()
            return Response(
                {
                    "success": True,
                    "code": status.HTTP_201_CREATED,
                    "message": "Registration successful! OTP sent to your email.",
                    "timestamp": int(time.time()),
                    "data": {
                        "user_id": user.id,
                        "email": user.email,
                    },
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Something went wrong on the server.",
                    "timestamp": int(time.time()),
                    "data": {"detail": [str(e)]},
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


""" ----------------verify OTP API view------------------- """


class VerifyOTPApiView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        if not request.data:
            return Response({
                "success": False,
                "code": status.HTTP_400_BAD_REQUEST,
                "message": "Request body cannot be empty.",
                "timestamp": int(time.time()),
                "data": {}
            }, status=status.HTTP_400_BAD_REQUEST)

        email = request.data.get('email', '').strip()
        otp = request.data.get('otp', '').strip()

        if not email or not otp:
            return Response({
                "success": False,
                "code": status.HTTP_400_BAD_REQUEST,
                "message": "Email and OTP are required.",
                "timestamp": int(time.time()),
                "data": {}
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({
                "success": False,
                "code": status.HTTP_404_NOT_FOUND,
                "message": "No account found with this email address.",
                "timestamp": int(time.time()),
                "data": {}
            }, status=status.HTTP_404_NOT_FOUND)

        # if user.is_active:
        #     return Response({
        #         "success": False,
        #         "code": status.HTTP_400_BAD_REQUEST,
        #         "message": "This account is already activated.",
        #         "timestamp": int(time.time()),
        #         "data": {}
        #     }, status=status.HTTP_400_BAD_REQUEST)

        if not user.otp:
            return Response({
                "success": False,
                "code": status.HTTP_400_BAD_REQUEST,
                "message": "No OTP found. Please request a new OTP.",
                "timestamp": int(time.time()),
                "data": {}
            }, status=status.HTTP_400_BAD_REQUEST)

        if user.otp.strip().upper() != otp.upper():
            return Response({
                "success": False,
                "code": status.HTTP_400_BAD_REQUEST,
                "message": "The OTP you entered is incorrect.",
                "timestamp": int(time.time()),
                "data": {}
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            user.is_active = True
            user.otp = None
            user.save()

            return Response({
                "success": True,
                "code": status.HTTP_200_OK,
                "message": "Account verification successfully.",
                "timestamp": int(time.time()),
                "data": {
                    "user_id": user.id,
                    "email": user.email,
                    "is_active": user.is_active,
                    "profile_setup_completed": user.profile_setup_completed
                }
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                "success": False,
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "Failed to activate account.",
                "timestamp": int(time.time()),
                "data": {"detail": [str(e)]}
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


""" ----------------Resend OTP API view------------------- """


class ResendOTPApiView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        email = request.data.get('email')

        if not email:
            return Response({
                "success": False,
                "code": status.HTTP_400_BAD_REQUEST,
                "message": "Email is required.",
                "timestamp": int(time.time()),
                "data": {}
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({
                "success": False,
                "code": status.HTTP_404_NOT_FOUND,
                "message": "No account found with this email address.",
                "timestamp": int(time.time()),
                "data": {}
            }, status=status.HTTP_404_NOT_FOUND)

        otp_code = generate_otp()
        user.otp = otp_code
        user.save()

        html_content = render_to_string(
            'send_code.html', {'otp': otp_code, 'user': user})

        try:
            msg = EmailMessage(
                subject='Your New OTP Code',
                body=html_content,
                from_email=settings.EMAIL_HOST_USER,
                to=[email],
            )
            msg.content_subtype = "html"
            msg.send()

            return Response({
                "success": True,
                "code": status.HTTP_200_OK,
                "message": "OTP has been resent to your email.",
                "timestamp": int(time.time()),
                "data": {}
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                "success": False,
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "Failed to send email.",
                "timestamp": int(time.time()),
                "data": {"detail": [str(e)]}
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


""" ----------------Forgot Password view------------------- """


class ForgotPasswordAPIView(APIView):
    serializer_class = ResetPasswordSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.serializer_class(data=request.data)

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

        email = serializer.validated_data['email']
        password = serializer.validated_data['password']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_404_NOT_FOUND,
                    "message": "Email not registered. Please sign up.",
                    "timestamp": int(time.time()),
                    "data": {"email": ["User not found."]}
                },
                status=status.HTTP_404_NOT_FOUND
            )

        user.set_password(password)
        user.save()

        return Response(
            {
                "success": True,
                "code": status.HTTP_200_OK,
                "message": "Password has been reset successfully.",
                "timestamp": int(time.time()),
                "data": {}
            },
            status=status.HTTP_200_OK
        )


""" -------------------Change Password view----------------------- """

class ChangePasswordViewSet(viewsets.GenericViewSet):
    serializer_class = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_401_UNAUTHORIZED,
                    "message": "Authentication required.",
                    "timestamp": int(time.time()),
                    "data": {}
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = self.get_serializer(
            data=request.data, context={"request": request})

        try:
            serializer.is_valid(raise_exception=True)
        except Exception as exc:
            errors = serializer.errors
            error_messages = []
            for field, messages in errors.items():
                error_messages.extend(messages)
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": ", ".join(error_messages),
                    "timestamp": int(time.time()),
                    # "data": {}
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        old_password = serializer.validated_data.get("old_password")
        new_password = serializer.validated_data.get("new_password")

        if not user.check_password(old_password):
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "The provided current password is incorrect.",
                    "timestamp": int(time.time()),
                    # "data": {}
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from django.contrib.auth import password_validation
            password_validation.validate_password(new_password, user)
        except Exception as exc:
            error_messages = exc.messages if hasattr(exc, 'messages') else [str(exc)]
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": ", ".join(error_messages),
                    "timestamp": int(time.time()),
                    # "data": {}
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user.set_password(new_password)
            user.save()
        except Exception as exc:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Failed to update password. Please try again later.",
                    "timestamp": int(time.time()),
                    # "data": {}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "success": True,
                "code": status.HTTP_200_OK,
                "message": "Password changed successfully.",
                "timestamp": int(time.time()),
                # "data": {}
            },
            status=status.HTTP_200_OK,
        )


""" ----------------Login view------------------- """


class LoginAPIView(APIView):
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.serializer_class(data=request.data)

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

        email = serializer.validated_data['email']
        password = serializer.validated_data['password']

        # ইউজার খুঁজুন
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "Email and password do not match.",
                    "timestamp": int(time.time()),
                    "data": {}
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Password verify করুন (manual authentication)
        if not user.check_password(password):
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "Email and password do not match.",
                    "timestamp": int(time.time()),
                    "data": {}
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Account activate করা নাই
        if not user.is_active:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_401_UNAUTHORIZED,
                    "message": "Account not activated. Please verify OTP first!",
                    "timestamp": int(time.time()),
                    "data": {
                        "email": user.email
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Profile setup complete করা নাই
        if not user.profile_setup_completed:
            refresh = RefreshToken.for_user(user)

            return Response(
                {
                    "success": False,
                    "code": status.HTTP_402_PAYMENT_REQUIRED,
                    "message": "Profile setup not completed. Please complete your profile first!",
                    "timestamp": int(time.time()),
                    "data": {
                        "requires_profile_setup": True,
                        "user_id": user.id,
                        "email": user.email,
                        "access": str(refresh.access_token),
                        "refresh": str(refresh)
                    }
                },
                status=status.HTTP_402_PAYMENT_REQUIRED
            )

        # সফল Login - manually set backend
        user.backend = 'django.contrib.auth.backends.ModelBackend'
        login(request, user)

        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "success": True,
                "code": status.HTTP_200_OK,
                "message": "Login successful.",
                "timestamp": int(time.time()),
                "data": {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "name": user.name,
                        "is_staff": user.is_staff,
                        "profile_setup_completed": user.profile_setup_completed
                    }
                }
            },
            status=status.HTTP_200_OK
        )


"""========================= deleted account/views.py code========================="""


class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, *args, **kwargs):
        user = request.user
        user.delete()
        return Response(
            {
                "success": True,
                "code": status.HTTP_200_OK,
                "message": "Account deleted successfully.",
                "timestamp": int(time.time()),
                "data": {}
            },
            status=status.HTTP_200_OK
        )


"""========================= Profile Setup View ========================="""


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

        # ✅ Check if the OTP has been verified.
        if not user.is_active:
            return Response({
                "success": False,
                "code": status.HTTP_403_FORBIDDEN,
                "message": "Please verify your OTP first.",
                "timestamp": int(time.time()),
                "data": {}
            }, status=status.HTTP_403_FORBIDDEN)

        # ✅ Check if the profile setup has already been done.
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
            with transaction.atomic():
                # Create or update profile
                profile, created = Profile.objects.get_or_create(user=user)

                address = serializer.validated_data.get('address')
                interests = serializer.validated_data.get('interests')
                profile_picture = serializer.validated_data.get(
                    'profile_picture')
                referred_by_code = serializer.validated_data.get(
                    'referred_by_code')

                if address:
                    profile.address = address

                if interests:
                    profile.interests = json.dumps(interests)

                if profile_picture:
                    profile.profile_picture = profile_picture

                profile.save()

                # ✅ Referral Bonus Process (Only Once)
                print(
                    f"[DEBUG] referred_by_code from request: {referred_by_code}")
                print(
                    f"[DEBUG] user.has_claimed_referral: {user.has_claimed_referral}")

                if referred_by_code and not user.has_claimed_referral:
                    # Trim referral code
                    referred_by_code = referred_by_code.strip()
                    print(
                        f"[DEBUG] Trimmed referral code: '{referred_by_code}'")

                    if not referred_by_code:
                        print("[DEBUG] Referral code is empty after trim")
                        return Response({
                            "success": False,
                            "code": status.HTTP_400_BAD_REQUEST,
                            "message": "Referral code cannot be empty.",
                            "timestamp": int(time.time()),
                            "data": {"referred_by_code": ["Invalid referral code."]}
                        }, status=status.HTTP_400_BAD_REQUEST)

                    try:
                        # Find the person whose code is being used
                        referrer = User.objects.get(
                            referral_code=referred_by_code)
                        print(
                            f"[DEBUG] Referrer found: {referrer.email} (ID: {referrer.id})")

                        # You cannot use your own code.
                        if referrer == user:
                            print(f"[DEBUG] User trying to use own code")
                            return Response({
                                "success": False,
                                "code": status.HTTP_400_BAD_REQUEST,
                                "message": "You cannot use your own referral code.",
                                "timestamp": int(time.time()),
                                "data": {"referred_by_code": ["Invalid referral code."]}
                            }, status=status.HTTP_400_BAD_REQUEST)

                        # ✅ Bonus day (in atomic transaction)
                        print(f"[DEBUG] Adding bonus to referrer and new user")
                        print(
                            f"[DEBUG] Referrer old balance: {referrer.balance}")
                        print(f"[DEBUG] New user old balance: {user.balance}")

                        referrer.balance += 10
                        referrer.save()

                        user.balance += 10
                        user.referred_by = referrer
                        user.has_claimed_referral = True

                        print(
                            f"[DEBUG] Referrer new balance: {referrer.balance}")
                        print(f"[DEBUG] New user new balance: {user.balance}")
                        print(f"[DEBUG] Referral bonus applied successfully!")

                    except User.DoesNotExist:
                        print(f"[DEBUG] Referral code not found in database")
                        return Response({
                            "success": False,
                            "code": status.HTTP_400_BAD_REQUEST,
                            "message": "Invalid referral code.",
                            "timestamp": int(time.time()),
                            "data": {"referred_by_code": ["Referral code not found."]}
                        }, status=status.HTTP_400_BAD_REQUEST)

                # ✅ Mark Profile setup complete.
                user.profile_setup_completed = True
                user.save()

                profile_data = ProfileSerializer(profile).data

                return Response({
                    "success": True,
                    "code": status.HTTP_201_CREATED,
                    "message": "Profile setup completed successfully. You can now login.",
                    "timestamp": int(time.time()),
                    "data": profile_data
                }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({
                "success": False,
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "Failed to setup profile.",
                "timestamp": int(time.time()),
                "data": {"detail": [str(e)]}
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


"""------------------------Profile Detail View-----------------------------------"""

class ProfileDetailsView(generics.RetrieveAPIView):
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        profile, created = Profile.objects.get_or_create(user=self.request.user)
        return profile

    def get_advertiser_status(self, user):
        if user.ads_provided:
            return {"status": "approved"}
        
        try:
            req = AdvertiserRequest.objects.get(user=user)
            return {
                "status": "pending" if not req.is_reviewed else "rejected",
                "applied_at": req.applied_at,
                "rejection_reason": req.rejection_reason
            }
        except AdvertiserRequest.DoesNotExist:
            return {"status": "not_applied"}

    def get_seller_status(self, user):
        try:
            req = SellerRequest.objects.get(user=user)
            data = {
                "status": req.status.lower(),
                "applied_at": req.created_at,
                "shop_name": req.shop_name,
            }
            if req.status == 'REJECTED':
                data["admin_note"] = req.admin_note
            return data
        except SellerRequest.DoesNotExist:
            return {"status": "not_applied"}

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        
        return Response(
            {
                "success": True,
                "code": status.HTTP_200_OK,
                "message": "Profile retrieved successfully.",
                "timestamp": int(time.time()),
                "data": {
                    **serializer.data,
                    "advertiser_status": self.get_advertiser_status(request.user),
                    "seller_status": self.get_seller_status(request.user),
                }
            },
            status=status.HTTP_200_OK
        )
""" ------------------------Profile UpdateView view--------------------------- """


class ProfileUpdateView(generics.UpdateAPIView):
    serializer_class = ProfileUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        # Get or create profile for the current user
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

        # Return full profile data after update
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
