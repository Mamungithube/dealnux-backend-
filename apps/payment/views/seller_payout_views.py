from decimal import Decimal

from custom_ads.utils import send_dealnux_email
from django.conf import settings
from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
import stripe

from ..models import SellerPayout
from ..services import process_seller_payout_request


class SellerStripeConnectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            seller = request.user.seller_profile
        except Exception:
            return Response({"success": False, "message": "You are not an approved seller."}, status=403)

        if not seller.stripe_account_id:
            account = stripe.Account.create(
                type='express',
                email=request.user.email,
                capabilities={'transfers': {'requested': True}},
                metadata={'seller_id': seller.id}
            )
            seller.stripe_account_id = account.id
            seller.save()

        account_link = stripe.AccountLink.create(
            account=seller.stripe_account_id,
            refresh_url=settings.STRIPE_CONNECT_REFRESH_URL,
            return_url=settings.STRIPE_CONNECT_RETURN_URL,
            type='account_onboarding',
        )

        return Response({
            "success": True,
            "code": 200,
            "message": "Onboarding link generated.",
            "data": {
                "onboarding_url": account_link.url,
                "stripe_account_id": seller.stripe_account_id
            }
        })


class RequestPayoutView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        seller = request.user.seller_profile
        amount = Decimal(str(request.data.get('amount', 0)))

        if amount < Decimal('10.00'):
            return Response({"success": False, "message": "Minimum payout is $10.00"}, status=400)

        try:
            payout = process_seller_payout_request(seller, amount)

            send_dealnux_email(
                "Payout Request Received - DealNux",
                request.user.email,
                "emails/payout_requested.html",
                {"seller": seller, "amount": float(amount)}
            )

            return Response({
                "success": True,
                "code": 200,
                "message": "Payout request processed successfully.",
                "data": {
                    "withdrawn_amount": float(amount),
                    "remaining_balance": float(seller.available_balance)
                }
            })
        except ValueError as ve:
            return Response({"success": False, "message": str(ve)}, status=400)
        except Exception as e:
            return Response({"success": False, "message": str(e)}, status=500)


class SellerStripeStatusView(APIView):
    """
    The seller's Stripe account status will be checked.
    GET /api/v1/store/seller/stripe-status/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            seller = request.user.seller_profile
        except AttributeError:
            return Response({"success": False, "message": "Seller profile not found."}, status=404)

        if not seller.stripe_account_id:
            return Response({
                "success": True,
                "data": {"connected": False, "verified": False}
            })

        try:
            account = stripe.Account.retrieve(seller.stripe_account_id)

            is_fully_verified = account.get(
                'charges_enabled', False) and account.get('payouts_enabled', False)

            if is_fully_verified and not seller.stripe_onboarding_completed:
                seller.stripe_onboarding_completed = True
                seller.save(update_fields=['stripe_onboarding_completed'])

            return Response({
                "success": True,
                "code": 200,
                "data": {
                    "connected": True,
                    "verified": is_fully_verified,
                    "stripe_account_id": seller.stripe_account_id,
                    "details_submitted": account.get('details_submitted', False)
                }
            })
        except Exception as e:
            return Response({"success": False, "message": f"Stripe Error: {str(e)}"}, status=400)


class SellerPayoutHistoryView(APIView):
    """
    Seller payout history
    GET /api/v1/store/seller/payouts/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            seller = request.user.seller_profile
        except Exception:
            return Response({'error': 'Not a seller.'}, status=403)

        payouts = SellerPayout.objects.filter(
            seller=seller).select_related('payment', 'order')
        data = []
        for p in payouts:
            data.append({
                'id':                 p.id,
                'order_id':           p.order.id if p.order else None,
                'gross_amount':       float(p.gross_amount) if p.gross_amount is not None else None,
                'platform_fee':       float(p.platform_fee_amount) if p.platform_fee_amount is not None else None,
                'seller_amount':      float(p.seller_amount) if p.seller_amount is not None else None,
                'currency':           p.payment.currency,
                'status':             p.status,
                'stripe_transfer_id': p.stripe_transfer_id,
                'failure_reason':     p.failure_reason,
                'created_at':         p.created_at,
            })
        return Response(data)


class SellerStripeLoginLinkView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            seller = request.user.seller_profile
        except AttributeError:
            return Response({
                "success": False,
                "message": "Seller profile not found."
            }, status=404)

        if not seller.stripe_account_id or not seller.stripe_onboarding_completed:
            return Response({
                "success": False,
                "message": "Please complete Stripe onboarding first before accessing the dashboard."
            }, status=400)

        try:
            login_link = stripe.Account.create_login_link(
                seller.stripe_account_id)

            return Response({
                "success": True,
                "code": 200,
                "message": "Login link generated successfully.",
                "data": {
                    "url": login_link.url
                }
            })
        except stripe.error.StripeError as e:
            return Response({
                "success": False,
                "message": f"Stripe Error: {str(e)}"
            }, status=400)
        except Exception:
            return Response({
                "success": False,
                "message": "An unexpected error occurred."
            }, status=500)
