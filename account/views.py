from django.shortcuts import render
from rest_framework.permissions import IsAdminUser
from rest_framework import viewsets
from .serializers import UserSerializer
from .models import User
from rest_framework.response import Response
from rest_framework import status
from .serializers import RegisterSerializer
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny


# Create your views here.

class UserApiView(viewsets.ModelViewSet):
    http_method_names = ['get', 'post', 'put', 'delete']
    permission_classes = [IsAdminUser]
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
    

"""--------------------Register View---------------------"""


class RegisterApiview(APIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        # Validate input
        if not request.data:
            return Response(
                {"success": False, "message": "Request body cannot be empty."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.serializer_class(data=request.data)
        
        # Check serializer validity
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "message": "Validation failed. Please check your input.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Attempt to save user and send OTP
        try:
            user = serializer.save()
            return Response(
                {
                    "success": True,
                    "message": "Registration successful! An OTP verification code has been sent to your email. Please check your inbox.",
                    "data": {
                        "user_id": user.id,
                        "email": user.email,
                        "message": "Please verify your email with the OTP to activate your account.",
                    },
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            # Handle duplicate email or other model errors
            error_message = str(e)
            if "email" in error_message.lower() or "unique" in error_message.lower():
                return Response(
                    {
                        "success": False,
                        "message": "An account with this email already exists. Please log in or use a different email.",
                        "errors": {"email": ["Email already registered."]},
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            
            # Generic server error for unexpected exceptions
            return Response(
                {
                    "success": False,
                    "message": "An error occurred during registration. Please try again later.",
                    "errors": {"detail": [str(e)]},
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )