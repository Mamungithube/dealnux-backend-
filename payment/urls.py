from django.urls import path
from .views import (
    CreateCheckoutSessionView,
    StripeWebhookView,
    SellerStripeConnectView,
    SellerStripeStatusView,
    PaymentHistoryView,
    SellerPayoutHistoryView,
)

app_name = 'payment'

urlpatterns = [
    path('checkout/', CreateCheckoutSessionView.as_view(), name='checkout'),
    path('history/', PaymentHistoryView.as_view(), name='payment-history'),
    path('webhook/stripe/', StripeWebhookView.as_view(), name='stripe-webhook'),
    path('seller/connect/',       SellerStripeConnectView.as_view(),  name='seller-connect'),
    path('seller/connect/status/',SellerStripeStatusView.as_view(),   name='seller-connect-status'),
    path('seller/payouts/',       SellerPayoutHistoryView.as_view(),  name='seller-payouts'),
]
