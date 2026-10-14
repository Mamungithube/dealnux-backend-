from django.db.models import Avg, Count
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Order, ProductReview, SellerProduct, SellerProfile, SellerRequest
from ..serializers import (
    AdminSellerRequestSerializer,
    OrderSerializer,
    SellerProfileSerializer,
    SellerRequestSerializer,
)
from ..services import (
    approve_seller_request,
    get_seller_dashboard_overview_data,
    get_seller_shipping_settings,
    reject_seller_request,
    update_seller_shipping_settings,
)
from config.responses import error_response, success_response


def is_approved_seller(user):
    """Check if user is an approved seller"""
    return hasattr(user, 'seller_profile') and user.seller_profile.is_active


class SellerRequestViewSet(viewsets.ModelViewSet):
    """
    User will apply in 11 steps.
    Admin can view all applications and approve/reject the application if he/she wants.
    """
    serializer_class = SellerRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return SellerRequest.objects.all().order_by('-created_at')
        return SellerRequest.objects.filter(user=user)

    def get_serializer_class(self):
        if self.request.user.is_staff:
            return AdminSellerRequestSerializer
        return SellerRequestSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        return Response({
            "success": True,
            "code": 201,
            "message": "Seller application submitted successfully! Please wait for admin review.",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def status(self, request):
        """User will see the current status and data of their application"""
        req = SellerRequest.objects.filter(user=request.user).first()
        if not req:
            return Response({
                "success": False,
                "code": 404,
                "message": "You haven't submitted any application yet.",
                "data": {}
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(req)
        return Response({
            "success": True,
            "code": 200,
            "message": "Application status fetched.",
            "data": serializer.data
        })

    # ── Admin Actions ──────────────────────────────────────────────────────

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def approve(self, request, pk=None):
        """Admin will approve the application and automatically create a seller profile"""
        seller_request = self.get_object()

        if seller_request.status == 'APPROVED':
            return Response({"message": "Already approved."}, status=400)

        approve_seller_request(seller_request)

        return Response({
            "success": True,
            "code": 200,
            "message": f"Seller '{seller_request.trade_name}' approved and profile activated.",
            "data": SellerRequestSerializer(seller_request).data
        })

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def reject(self, request, pk=None):
        """Admin will reject the application and provide a reason"""
        seller_request = self.get_object()
        note = request.data.get(
            'admin_note', 'Your application does not meet our requirements.')

        reject_seller_request(seller_request, note)

        return Response({
            "success": True,
            "code": 200,
            "message": "Seller application rejected.",
            "data": {"admin_note": note}
        })


class SellerProfileViewSet(viewsets.ModelViewSet):
    queryset = SellerProfile.objects.select_related('user').all()
    serializer_class = SellerProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return SellerProfile.objects.select_related('user').all()
        return SellerProfile.objects.select_related('user').filter(user=self.request.user)

    # --- Dashboard Overview Page ---
    @action(detail=False, methods=['get'], url_path='dashboard/overview')
    def dashboard_overview(self, request):
        seller = request.user.seller_profile
        data = get_seller_dashboard_overview_data(seller)
        return success_response(data)

    # --- Detailed Shipping Page (GET & PATCH) ---
    @action(detail=False, methods=['get', 'patch'], url_path='dashboard/shipping')
    def dashboard_shipping(self, request):
        try:
            seller = request.user.seller_profile
        except SellerProfile.DoesNotExist:
            return error_response("Seller profile not found.", code=404)

        if request.method == 'PATCH':
            update_seller_shipping_settings(seller, request.data)
            return success_response(None, message="Shipping settings updated successfully.")

        response_data = get_seller_shipping_settings(seller)
        return success_response(response_data, message="Detailed shipping settings fetched.")

    # --- Payouts/Wallet Page ---
    @action(detail=False, methods=['get'], url_path='dashboard/payouts')
    def dashboard_payouts(self, request):
        seller = request.user.seller_profile
        from payment.models import SellerPayout
        payouts = SellerPayout.objects.filter(seller=seller).order_by('-created_at')
        payout_history = []
        for p in payouts:
            payout_history.append({
                "id": p.id,
                "amount": float(p.seller_amount) if p.seller_amount is not None else 0.0,
                "gross_amount": float(p.gross_amount) if p.gross_amount is not None else 0.0,
                "status": p.status,
                "stripe_transfer_id": p.stripe_transfer_id or "",
                "created_at": p.created_at,
                "failure_reason": p.failure_reason or ""
            })

        data = {
            "available_balance": float(seller.available_balance),
            "pending_balance": float(seller.pending_balance),
            "total_withdrawn": float(seller.total_withdrawn),
            "total_earned": float(seller.total_earnings),
            "payout_history": payout_history
        }
        return success_response(data)

    @action(detail=False, methods=['get'], url_path='me')
    def me(self, request):
        """The seller will use this to view their profile data."""
        try:
            seller = request.user.seller_profile
            serializer = self.get_serializer(seller)
            return success_response(serializer.data, message="Your seller profile fetched")
        except AttributeError:
            return error_response("User has no seller profile.", code=404)
        except Exception as e:
            return error_response(str(e), code=500)


class SellerDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_approved_seller(request.user):
            return error_response("You are not an approved seller.", code=403)

        seller = request.user.seller_profile

        pending_products = SellerProduct.objects.filter(
            seller=seller, status='PENDING').count()
        approved_products = SellerProduct.objects.filter(
            seller=seller, status='APPROVED').count()

        recent_orders = Order.objects.filter(
            seller=seller).order_by('-created_at')[:5]

        review_stats = ProductReview.objects.filter(product__seller=seller).aggregate(
            average_rating=Avg('rating'),
            total_reviews=Count('id')
        )

        data = {
            "shop_name": seller.shop_name,
            "wallet": {
                "pending":    float(seller.pending_balance),
                "available":  float(seller.available_balance),
                "withdrawn":  float(seller.total_withdrawn),
                "total_earned": float(seller.total_earnings),
            },
            "total_products": SellerProduct.objects.filter(seller=seller).count(),
            "total_orders":   seller.total_orders,
            "total_reviews":  review_stats['total_reviews'],
            "average_rating": round(review_stats['average_rating'] or 0, 1),
            "product_stats": {
                "pending":  pending_products,
                "approved": approved_products,
            },
            "recent_orders": OrderSerializer(recent_orders, many=True).data,
        }

        return success_response(data, message="Seller dashboard fetched")
