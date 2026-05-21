from django.urls import path
from .views import (
    CheckSessionStatusView,
    CreateCheckoutSessionView,
    CreateSubscriptionCheckoutView,
    RequestPayoutView,
    StripeWebhookView,
    SellerStripeConnectView,
    SellerStripeStatusView,
    PaymentHistoryView,
    SellerPayoutHistoryView,
    CheckoutSessionStatusView,
    SellerStripeLoginLinkView,
    SubscriptionPlanListView,
    UserSubscriptionStatusView, 
    ProductClickTrackerView,
    ManageSubscriptionView,
)

app_name = 'payment'

urlpatterns = [
    path('checkout/session-status/', CheckoutSessionStatusView.as_view()),
    path('checkout/', CreateCheckoutSessionView.as_view(), name='checkout'),
    path('history/', PaymentHistoryView.as_view(), name='payment-history'),
    path('webhook/stripe/', StripeWebhookView.as_view(), name='stripe-webhook'),

    path('seller/connect/',       SellerStripeConnectView.as_view(),  name='seller-connect'),
    path('seller/connect/status/',SellerStripeStatusView.as_view(),   name='seller-connect-status'),
    path('seller/payouts/',       SellerPayoutHistoryView.as_view(),  name='seller-payouts'),
    path('session-status/', CheckSessionStatusView.as_view(), name='session-status'),
    path('seller/withdraw/', RequestPayoutView.as_view(), name='seller-withdraw'),
    path('seller/stripe-dashboard/', SellerStripeLoginLinkView.as_view(), name='seller-stripe-dashboard'),

        # --- Subscription module ---
    path('plans/', SubscriptionPlanListView.as_view(), name='plan-list'), # প্ল্যান লিস্ট দেখাবে
    path('subscribe/', CreateSubscriptionCheckoutView.as_view(), name='subscribe'), # প্ল্যান কেনা
    path('subscription/status/', UserSubscriptionStatusView.as_view(), name='sub-status'), 
    path('subscription/manage/', ManageSubscriptionView.as_view(), name='manage-subscription'),

    path('click-tracker/<int:listing_id>/', ProductClickTrackerView.as_view(), name='click-tracker'),
]
