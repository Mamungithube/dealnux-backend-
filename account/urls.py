from .views import UserAPIView, RegisterApiView ,  LoginAPIView, ResendOTPApiView, VerifyOTPApiView, ForgotPasswordAPIView, ChangePasswordViewSet, DeleteAccountView
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    # user list 
    path('user_all/', UserAPIView.as_view({'get': 'list'}), name='user-list'), 
    path('user/<int:pk>/', UserAPIView.as_view({'get': 'list'}), name='user-detail'),

    # authentication part urls
    path('register/', RegisterApiView.as_view(), name='user-register'),
    path('login/', LoginAPIView.as_view(), name='login'),
    path('resend_otp/', ResendOTPApiView.as_view(), name='resend-otp'),
    path('verify_otp/', VerifyOTPApiView.as_view(), name='verify-otp'),
    path('forget-pass/', ForgotPasswordAPIView.as_view(), name='forget-password'),
    path('change-pass/', ChangePasswordViewSet.as_view({'post': 'create'}), name='password-change'),
    path('delete-account/', DeleteAccountView.as_view(), name='delete-account'),
]