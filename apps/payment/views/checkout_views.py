from decimal import Decimal

from django.db import transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
import stripe

from ..models import Payment
from ..services import create_product_checkout_session
from api_integration.models import ProductListing
from config.pagination import CustomPagination
from store.models import SellerProduct


class CreateCheckoutSessionView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        """
        Handles the creation of a checkout session for purchasing products.
        It calculates total amounts, applies user balance if requested, and creates a Stripe session.
        """
        items_data = request.data.get('items', [])
        use_balance = request.data.get('use_balance', False)
        shipping_address = request.data.get('shipping_address')

        root_coupon_code = (
            request.data.get('coupon_code')
            or request.data.get('couponCode')
            or request.data.get('coupon')
            or ''
        ).strip()

        if not items_data or not shipping_address:
            return Response({'error': 'Items and shipping address are required.'}, status=400)

        try:
            base_url = request.build_absolute_uri('/')
            result = create_product_checkout_session(
                user=request.user,
                items_data=items_data,
                shipping_address=shipping_address,
                use_balance=use_balance,
                root_coupon_code=root_coupon_code,
                base_url=base_url
            )
            if result.get('is_zero_payment'):
                return Response({
                    'success': True,
                    'message': 'Order placed successfully using your balance.',
                    'payment_id': result['payment_id'],
                    'breakdown': result['breakdown'],
                }, status=200)
            else:
                return Response({
                    'client_secret': result['clientSecret'],
                    'payment_intent_client_secret': result['payment_intent_client_secret'],
                    'payment_id': result['payment_id'],
                    'breakdown': result['breakdown'],
                })
        except SellerProduct.DoesNotExist:
            return Response({'error': 'One or more selected products were not found or not approved.'}, status=404)
        except Exception as e:
            return Response({'error': str(e)}, status=500)


class CheckoutSessionStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        payment_id = request.query_params.get('payment_id')

        if not payment_id:
            return Response({'error': 'payment_id is required.'}, status=400)

        try:
            payment = Payment.objects.get(id=payment_id, buyer=request.user)
        except Payment.DoesNotExist:
            return Response({'error': 'Payment not found.'}, status=404)

        return Response({
            'payment_status': payment.status,        # PAID / PENDING / FAILED
            'payment_id':     payment.id,
            'order_id':       payment.order.id if payment.order else None,
        })


class CheckSessionStatusView(APIView):
    """When the user returns to the return_url, Frontend will call it."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        session_id = request.query_params.get('session_id')

        if not session_id:
            return Response({"error": "session_id is required"}, status=400)

        try:
            session = stripe.checkout.Session.retrieve(session_id)

            customer_email = None
            if session.customer_details:
                customer_email = session.customer_details.get('email')
            elif session.customer_email:
                customer_email = session.customer_email

            return Response({
                "success": True,
                "status": session.status,
                "payment_status": session.payment_status,
                "customer_email": customer_email,
                "message": "Payment verified" if session.payment_status == 'paid' else "Payment process incomplete"
            }, status=200)

        except stripe.error.StripeError as e:
            return Response({"success": False, "error": str(e)}, status=400)
        except Exception:
            return Response({"success": False, "error": "An unexpected error occurred."}, status=500)


class PaymentHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        payments = Payment.objects.filter(buyer=request.user).select_related(
            'seller_product', 'order'
        )

        paginator = CustomPagination()
        paginated_qs = paginator.paginate_queryset(payments, request)

        data = []
        for p in paginated_qs:
            data.append({
                'id':              p.id,
                'product':         p.seller_product.title if p.seller_product else None,
                'quantity':        p.quantity,
                'final_amount':    float(p.final_amount) if p.final_amount is not None else None,
                'discount_amount': float(p.discount_amount) if p.discount_amount is not None else None,
                'currency':        p.currency,
                'status':          p.status,
                'order_id':        p.order.id if p.order else None,
                'order_status':    p.order.status if p.order else None,
                'created_at':      p.created_at,
            })

        return paginator.get_paginated_response(data)


class ProductClickTrackerView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, listing_id):
        try:
            listing = ProductListing.objects.select_related('platform').get(
                id=listing_id,
                is_available=True
            )
        except ProductListing.DoesNotExist:
            return Response({"error": "Listing not found."}, status=404)

        return Response({"redirect_url": listing.external_url})
