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
    CookieConsentView,
    AboutUsView,
    SellerPolicyView,
    BuyerProtectionPolicyView,
    ProhibitedProductsPolicyView,
    IntellectualPropertyPolicyView,
    CommunityGuidelinesView
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
    path('seller-policy/',                 SellerPolicyView.as_view(),               name='seller-policy'),
    path('buyer-protection-policy/',      BuyerProtectionPolicyView.as_view(),      name='buyer-protection-policy'),
    path('prohibited-products-policy/',   ProhibitedProductsPolicyView.as_view(),   name='prohibited-products-policy'),
    path('intellectual-property-policy/', IntellectualPropertyPolicyView.as_view(), name='intellectual-property-policy'),
    path('community-guidelines/',         CommunityGuidelinesView.as_view(),        name='community-guidelines'),
    path('about-us/',           AboutUsView.as_view(),          name='about-us'),

    path('cookie-consent/', CookieConsentView.as_view(), name='cookie-consent'),
]