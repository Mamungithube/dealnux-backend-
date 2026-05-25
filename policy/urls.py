from django.urls import path
from .views import (
    ContactMessageCreateView,
    ContactMessageListView,
    PrivacyPolicyView,
    CookiePolicyView,
    TermsOfServiceView,
    ReviewView,
    EMIPaymentPolicyView,
    WarrantyPolicyView,
    ExchangePolicyView,
    DeliveryPolicyView,
    PreOrderPolicyView,
    RefundPolicyView,
    ReturnPolicyView,
)

urlpatterns = [
    # Existing
    path('privacy-policy/',   PrivacyPolicyView.as_view(),  name='privacy-policy'),
    path('cookie-policy/',    CookiePolicyView.as_view(),   name='cookie-policy'),
    path('terms-of-service/', TermsOfServiceView.as_view(), name='terms-of-service'),
    path('review/',           ReviewView.as_view(),        name='review'),
    path('contact/send/', ContactMessageCreateView.as_view(), name='contact-send'),
    path('messages/', ContactMessageListView.as_view(), name='contact-messages'),

    # New GET-only policies
    path('emi-payment-policy/', EMIPaymentPolicyView.as_view(), name='emi-payment-policy'),
    path('warranty-policy/',    WarrantyPolicyView.as_view(),   name='warranty-policy'),
    path('exchange-policy/',    ExchangePolicyView.as_view(),   name='exchange-policy'),
    path('delivery-policy/',    DeliveryPolicyView.as_view(),   name='delivery-policy'),
    path('pre-order-policy/',   PreOrderPolicyView.as_view(),   name='pre-order-policy'),
    path('refund-policy/',      RefundPolicyView.as_view(),     name='refund-policy'),
    path('return-policy/',      ReturnPolicyView.as_view(),     name='return-policy'),
]