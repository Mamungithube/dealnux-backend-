from django.shortcuts import render
from rest_framework.permissions import IsAdminUser
from rest_framework import viewsets
from .serializers import UserSerializer, RegisterSerializer, UserLoginSerializer, ChangePasswordSerializer, ResetPasswordSerializer, LoginSerializer , ProfileSerializer , ProfileUpdateSerializer
from .models import User,Profile
from rest_framework.response import Response
from rest_framework import status
from .serializers import RegisterSerializer
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny,IsAuthenticated
from django.contrib.auth import authenticate, login
from rest_framework_simplejwt.tokens import RefreshToken
from django.shortcuts import get_object_or_404   
from django.core.mail import EmailMessage
from django.conf import settings
from django.template.loader import render_to_string
from rest_framework import generics, permissions
import time

import random

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
        # ১. ইনপুট খালি কি না চেক
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

        # ২. ভ্যালিডেশন (এখানেই ইমেইল এক্সিস্ট কি না চেক হয়ে যাবে)
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            # যদি ইমেইল আগে থেকেই থাকে, ডিজেঙ্গো অটোমেটিক errors এর মধ্যে সেটা বলে দিবে
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

        # ৩. ইউজার সেভ করা
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
            # যদি সেভ করার পর অন্য কোনো টেকনিক্যাল এরর হয় (ডাটাবেজ কানেকশন ইত্যাদি)
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
    """OTP verification endpoint.
    
    Expects `email` and `otp` in the request body.
    Activates user account after successful OTP verification.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        # Validate request body is not empty
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

        # Extract and validate email
        email = request.data.get('email', '').strip()
        if not email:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "Email is required.",
                    "timestamp": int(time.time()),
                    "data": {"email": ["Email field cannot be empty."]},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Extract and validate OTP
        otp = request.data.get('otp', '').strip()
        if not otp:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "OTP is required.",
                    "timestamp": int(time.time()),
                    "data": {"otp": ["OTP field cannot be empty."]},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if user exists
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_404_NOT_FOUND,
                    "message": "No account found with this email address.",
                    "timestamp": int(time.time()),
                    "data": {"email": ["User not registered."]},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if user is already active
        if user.is_active:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "This account is already activated.",
                    "timestamp": int(time.time()),
                    "data": {"detail": ["Account already verified."]},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if profile exists
        try:
            profile = user.profile
        except Profile.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "User profile not found. Please contact support.",
                    "timestamp": int(time.time()),
                    "data": {"detail": ["Profile does not exist."]},
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Check if OTP exists in profile
        if not profile.otp:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "No OTP found for this account. Please request a new OTP.",
                    "timestamp": int(time.time()),
                    "data": {"otp": ["OTP has expired or not set."]},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify OTP (case-insensitive for safety)
        if profile.otp.strip().upper() != otp.upper():
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "The OTP you entered is incorrect.",
                    "timestamp": int(time.time()),
                    "data": {"otp": ["Invalid OTP. Please try again."]},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # OTP is valid — activate the user account
        try:
            user.is_active = True
            user.save(update_fields=['is_active'])
            
            profile.otp = None
            profile.save(update_fields=['otp'])

            return Response(
                {
                    "success": True,
                    "code": status.HTTP_200_OK,
                    "message": "Account activated successfully. You can now log in.",
                    "timestamp": int(time.time()),
                    "data": {
                        "user_id": user.id,
                        "email": user.email,
                        "is_active": user.is_active,
                    },
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Failed to activate account. Please try again later.",
                    "timestamp": int(time.time()),
                    "data": {"detail": [str(e)]},
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


""" ----------------Resend OTP API view------------------- """


class ResendOTPApiView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        email = request.data.get('email')
        
        if not email:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "Email is required.",
                    "timestamp": int(time.time()),
                    "data": {"email": ["Email field cannot be empty."]}
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_404_NOT_FOUND,
                    "message": "No account found with this email address.",
                    "timestamp": int(time.time()),
                    "data": {"email": ["User not registered."]}
                },
                status=status.HTTP_404_NOT_FOUND
            )

        otp_code = generate_otp()
        user.profile.otp = otp_code
        user.profile.save()

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

            return Response(
                {
                    "success": True,
                    "code": status.HTTP_200_OK,
                    "message": "OTP has been resent to your email. Please check your email inbox.",
                    "timestamp": int(time.time()),
                    "data": {}
                },
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Failed to send email.",
                    "timestamp": int(time.time()),
                    "data": {"detail": [str(e)]}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


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

        serializer = self.get_serializer(data=request.data, context={"request": request})

        try:
            serializer.is_valid(raise_exception=True)
        except Exception as exc:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "Invalid input.",
                    "timestamp": int(time.time()),
                    "data": serializer.errors
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
                    "data": {"old_password": ["Incorrect password. Please try again."]}
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate the new password against Django validators
        try:
            from django.contrib.auth import password_validation
            password_validation.validate_password(new_password, user)
        except Exception as exc:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "New password did not meet requirements.",
                    "timestamp": int(time.time()),
                    "data": {"new_password": exc.messages if hasattr(exc, 'messages') else [str(exc)]}
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Everything OK — change the password
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
                    "data": {"detail": [str(exc)]}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "success": True,
                "code": status.HTTP_200_OK,
                "message": "Password changed successfully.",
                "timestamp": int(time.time()),
                "data": {}
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

        user = authenticate(email=email, password=password)

        if user:
            if not user.is_active:
                return Response(
                    {
                        "success": False,
                        "code": status.HTTP_403_FORBIDDEN,
                        "message": "Account not activated. Verify OTP first!",
                        "timestamp": int(time.time()),
                        "data": {}
                    },
                    status=status.HTTP_403_FORBIDDEN
                )

            login(request, user)

            # Generate JWT tokens
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
                            "is_staff": user.is_staff
                        }
                    }
                },
                status=status.HTTP_200_OK
            )

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


class BaseResponseMixin:
    def success_response(self, message, data=None, status_code=status.HTTP_200_OK):
        response = {
            "success": True,
            "code": status_code,
            "message": message,
            "timestamp": int(time.time()),
            "data": data if data is not None else {}
        }
        return Response(response, status=status_code)

    def error_response(self, message, data=None, status_code=status.HTTP_400_BAD_REQUEST):
        response = {
            "success": False,
            "code": status_code,
            "message": message,
            "timestamp": int(time.time()),
            "data": data if data is not None else {}
        }
        return Response(response, status=status_code)


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
    


"""------------------------Profile Detail View-----------------------------------"""

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
        return Response(
            {
                "success": True,
                "code": status.HTTP_200_OK,
                "message": "Profile retrieved successfully.",
                "timestamp": int(time.time()),
                "data": serializer.data
            },
            status=status.HTTP_200_OK
        )


""" ------------------------Profile UpdateView view--------------------------- """

class ProfileUpdateView(generics.UpdateAPIView):
    serializer_class = ProfileUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        # Get or create profile for the current user
        profile, created = Profile.objects.get_or_create(user=self.request.user)
        return profile  

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        
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
        profile_serializer = ProfileSerializer(instance, context=self.get_serializer_context())
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