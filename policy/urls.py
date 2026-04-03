from django.urls import path
from .views import (
    PrivacyPolicyView,
    CookiePolicyView,
    TermsOfServiceView,
    ReviewView
)

urlpatterns =[
    path('privacy-policy/', PrivacyPolicyView.as_view(), name='privacy-policy'),
    path('cookie-policy/', CookiePolicyView.as_view(), name='cookie-policy'),
    path('terms-of-service/', TermsOfServiceView.as_view(), name='terms-of-service'),
    path('reviews/', ReviewView.as_view(), name='reviews'),

]