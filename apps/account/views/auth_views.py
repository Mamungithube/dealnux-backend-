import time
from rest_framework import status, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import login

from account.models import User
from account.serializers import (
    RegisterSerializer,
    LoginSerializer,
    ResetPasswordSerializer,
    ChangePasswordSerializer,
)
from account.services import (
    generate_otp_code,
    resend_user_otp,
    verify_user_otp,
    reset_user_password,
)


def generate_otp():
    return generate_otp_code()


# -------------------------- User Registration View (Public Signup & OTP Dispatch) --------------------------
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


# -------------------------- Account Activation OTP Verification View (Public) --------------------------
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

        success, msg, user = verify_user_otp(email, otp)
        if not success:
            code = status.HTTP_404_NOT_FOUND if "No account found" in msg else status.HTTP_400_BAD_REQUEST
            return Response({
                "success": False,
                "code": code,
                "message": msg,
                "timestamp": int(time.time()),
                "data": {}
            }, status=code)

        return Response({
            "success": True,
            "code": status.HTTP_200_OK,
            "message": "Account verification successful.",
            "timestamp": int(time.time()),
            "data": {
                "user_id": user.id,
                "email": user.email,
                "is_active": user.is_active,
                "profile_setup_completed": user.profile_setup_completed
            }
        }, status=status.HTTP_200_OK)


# -------------------------- Resend Registration OTP View (Public) --------------------------
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
            success, message = resend_user_otp(email)
            if not success:
                return Response({
                    "success": False,
                    "code": status.HTTP_404_NOT_FOUND,
                    "message": message,
                    "timestamp": int(time.time()),
                    "data": {}
                }, status=status.HTTP_404_NOT_FOUND)

            return Response({
                "success": True,
                "code": status.HTTP_200_OK,
                "message": message,
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


# -------------------------- User Login View (Credentials & JWT Token Generation) --------------------------
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


# -------------------------- Forgot Password & Reset View (Public) --------------------------
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

        success, message = reset_user_password(email, password)
        if not success:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_404_NOT_FOUND,
                    "message": message,
                    "timestamp": int(time.time()),
                    "data": {"email": ["User not found."]}
                },
                status=status.HTTP_404_NOT_FOUND
            )

        return Response(
            {
                "success": True,
                "code": status.HTTP_200_OK,
                "message": message,
                "timestamp": int(time.time()),
                "data": {}
            },
            status=status.HTTP_200_OK
        )


# -------------------------- Change Password ViewSet (Authenticated User) --------------------------
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
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from django.contrib.auth import password_validation
            password_validation.validate_password(new_password, user)
        except Exception as exc:
            error_messages = exc.messages if hasattr(
                exc, 'messages') else [str(exc)]
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": ", ".join(error_messages),
                    "timestamp": int(time.time()),
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
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "success": True,
                "code": status.HTTP_200_OK,
                "message": "Password changed successfully.",
                "timestamp": int(time.time()),
            },
            status=status.HTTP_200_OK,
        )
