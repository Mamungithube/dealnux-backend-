from api_integration.views import DeviceTokenView, NotificationListView

from .views import (
    UserAPIView,
    RegisterApiView,
    LoginAPIView,
    ResendOTPApiView,
    VerifyOTPApiView,
    ForgotPasswordAPIView,
    ChangePasswordViewSet,
    ProfileDetailsView,
    ProfileUpdateView,
    DeleteAccountView,
    ProfileSetupView
)
from django.urls import path


urlpatterns = [
    # user list
    path('user_all/', UserAPIView.as_view({'get': 'list'}), name='user-list'),
    path('user/<int:pk>/',
         UserAPIView.as_view({'get': 'list'}), name='user-detail'),

    # authentication part urls
    path('register/', RegisterApiView.as_view(), name='user-register'),
    path('login/', LoginAPIView.as_view(), name='login'),
    path('resend_otp/', ResendOTPApiView.as_view(), name='resend-otp'),
    path('verify_otp/', VerifyOTPApiView.as_view(), name='verify-otp'),
    path('forget-pass/', ForgotPasswordAPIView.as_view(), name='forget-password'),
    path('change-pass/',
         ChangePasswordViewSet.as_view({'post': 'create'}), name='password-change'),
    path('delete-account/', DeleteAccountView.as_view(), name='delete-account'),

    # profile part urls
    path('profile/setup/', ProfileSetupView.as_view(), name='profile-setup'),
    path('profile/',
         ProfileDetailsView.as_view(), name='profile'),
    path('profile/update/',
         ProfileUpdateView.as_view(), name='profile-detail'),

     path('profile/delete/', DeleteAccountView.as_view(), name='delete-account'),

     path('device-token/', DeviceTokenView.as_view(), name='device-token'),
     path('notifications/', NotificationListView.as_view(), name='notifications'),

]
