from .views import UserApiView, RegisterApiview
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('register/', RegisterApiview.as_view(), name='register' ,),
    path('users/', UserApiView.as_view({'get': 'list'}), name='users'),
]