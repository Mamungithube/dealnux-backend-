from django.db.models import Q
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated

from ..models import Coupon, Order, ProductReview, SellerProduct
from ..serializers import (
    CouponSerializer,
    CouponValidateSerializer,
    OrderCreateSerializer,
    OrderSerializer,
)
from ..services import (
    confirm_order_by_buyer,
    create_store_order,
    open_order_dispute,
    process_order_refund,
    resolve_order_dispute,
    update_order_tracking,
)
from .seller_views import is_approved_seller
from config.pagination import CustomPagination
from config.responses import error_response, success_response


class OrderViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination

    def get_serializer_class(self):
        if self.action == 'create':
            return OrderCreateSerializer
        return OrderSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Order.objects.select_related('buyer', 'seller', 'seller__user', 'seller_product').all().order_by('-created_at')

        return Order.objects.filter(
            Q(buyer=user) | Q(seller__user=user)
        ).select_related('buyer', 'seller', 'seller__user', 'seller_product').distinct().order_by('-created_at')

    def create(self, request, *args, **kwargs):
        """Places a marketplace order and holds funds in escrow"""
        serializer = self.get_serializer(
            data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        order = create_store_order(serializer, request.user)

        return success_response(
            OrderSerializer(order).data,
            message="Order placed and funds held in escrow.",
            code=201
        )

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)

        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter.upper())

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(qs, many=True)
        return success_response(serializer.data, message="Orders fetched")

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return success_response(serializer.data, message="Order details fetched")

    @action(detail=False, methods=['get'], url_path='seller-orders')
    def seller_orders(self, request):
        if not hasattr(request.user, 'seller_profile'):
            return error_response("You are not a registered seller.", code=403)

        seller = request.user.seller_profile

        queryset = Order.objects.filter(seller=seller).select_related(
            'buyer', 'seller_product').order_by('-created_at')

        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter.upper())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return success_response(serializer.data, message="Seller shop orders fetched")

    @action(detail=True, methods=['post'], url_path='update-status')
    def update_status(self, request, pk=None):
        order = self.get_object()

        if not request.user.is_staff and order.seller.user != request.user:
            return error_response("Unauthorized.", code=403)

        order.status = 'ACCEPTED'
        order.save(update_fields=['status', 'updated_at'])

        return success_response(
            {"order_number": order.order_number, "status": order.status},
            message="Order accepted by seller."
        )

    @action(detail=True, methods=['post', 'put', 'patch'], url_path='add-tracking')
    def add_tracking(self, request, pk=None):
        order = self.get_object()

        if order.seller.user != request.user and not request.user.is_staff:
            return error_response("You are not the seller of this order.", code=403)

        tracking_no = request.data.get('tracking_number')
        courier = request.data.get('courier_name')

        if not tracking_no:
            return error_response("Tracking number is required.", code=400)

        order = update_order_tracking(order, tracking_no, courier)
        return success_response(OrderSerializer(order).data, message="Order marked as Shipped.")

    @action(detail=False, methods=['get'], url_path='my-orders')
    def my_orders(self, request):
        user = request.user

        total_orders = Order.objects.filter(buyer=user).count()
        delivered_count = Order.objects.filter(
            buyer=user, status='DELIVERED').count()

        pending_action = Order.objects.filter(
            buyer=user,
            status='DELIVERED',
            is_accepted_by_buyer=False
        ).count()

        qs = Order.objects.filter(buyer=user).select_related(
            'seller', 'seller_product').order_by('-created_at')

        status_filter = request.query_params.get('status')
        if status_filter and status_filter.upper() != 'ALL':
            qs = qs.filter(status=status_filter.upper())

        review_count = ProductReview.objects.filter(user=user).count()

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)

            paginated_response = self.get_paginated_response(serializer.data)
            paginated_response.data['data']['summary'] = {
                "lifetime_savings": float(user.total_lifetime_savings),
                "total_orders": total_orders,
                "delivered_text": f"{delivered_count} delivered",
                "pending_action_count": pending_action,
                "review_count": review_count,
                "plan_name": "Pro",
                "plan_status": "Active"
            }
            return paginated_response

        serializer = self.get_serializer(qs, many=True)
        summary = {
            "lifetime_savings": float(user.total_lifetime_savings),
            "total_orders": total_orders,
            "pending_action_count": pending_action,
            "review_count": review_count,
        }
        return success_response({"summary": summary, "orders": serializer.data})

    @action(detail=True, methods=['post'], url_path='accept-order')
    def accept_order(self, request, pk=None):
        """Called by buyer once product received. Confirms order and releases funds."""
        order = self.get_object()

        if order.buyer != request.user:
            return error_response("Not authorized.", code=403)

        if order.status != 'SHIPPED':
            return error_response("You can only confirm after the order is SHIPPED.", code=400)

        confirm_order_by_buyer(order)
        return success_response(None, message="Order Confirmed! Funds released to seller.")

    @action(detail=True, methods=['post'], url_path='process-refund', permission_classes=[IsAdminUser])
    def process_refund(self, request, pk=None):
        order = self.get_object()
        fault = request.data.get('fault_party')

        if fault not in ['SELLER', 'BUYER']:
            return error_response("Invalid fault_party. Must be SELLER or BUYER.", code=400)

        refund_amount = process_order_refund(order, fault)
        return success_response({"refund_amount": float(refund_amount)}, message=f"Refund processed. Fault: {fault}")

    @action(detail=True, methods=['post'], url_path='open-dispute')
    def open_dispute(self, request, pk=None):
        order = self.get_object()

        if order.buyer != request.user:
            return error_response("Not authorized", code=403)

        if order.status not in ['SHIPPED', 'DELIVERED']:
            return error_response("Dispute can only be opened after shipping.", code=400)

        if hasattr(order, 'dispute'):
            return error_response("A dispute is already open for this order.", code=400)

        open_order_dispute(
            order=order,
            reason=request.data.get('reason'),
            description=request.data.get('description'),
            evidence_image=request.FILES.get('evidence_image')
        )

        return success_response(None, message="Dispute opened. Admin will review it soon.")

    @action(detail=True, methods=['post'], url_path='resolve-dispute', permission_classes=[IsAdminUser])
    def resolve_dispute(self, request, pk=None):
        order = self.get_object()
        if order.status != 'DISPUTED':
            return error_response("This order is not in dispute.", code=400)

        decision = request.data.get('decision')
        fault = request.data.get('fault_party')

        refund_amount = resolve_order_dispute(order, decision, fault)

        if decision == 'REJECT':
            return success_response(None, message="Dispute rejected. Order set back to Shipped.")

        return success_response(
            {"refund_amount": float(refund_amount)},
            message=f"Dispute resolved. Refund of ${refund_amount} processed for {fault} fault."
        )


class CouponViewSet(viewsets.ModelViewSet):
    serializer_class = CouponSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Coupon.objects.select_related('seller').all()
        if is_approved_seller(user):
            return Coupon.objects.filter(seller=user.seller_profile)
        return Coupon.objects.none()

    def perform_create(self, serializer):
        if not is_approved_seller(self.request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only approved sellers can create coupons.")
        serializer.save(seller=self.request.user.seller_profile)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return success_response(serializer.data, message="Coupon created.", code=201)

    @action(detail=False, methods=['post'], url_path='validate', permission_classes=[IsAuthenticated])
    def validate_coupon(self, request):
        serializer = CouponValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        v_data = serializer.validated_data
        code = v_data['code']
        total_discount = v_data['total_discount']
        total_original = v_data['total_original']
        final_amount = total_original - total_discount
        seller_shop = v_data.get('seller_shop', '')
        discount_type = v_data.get('discount_type', '')
        discount_value = float(v_data.get('discount_value', 0))

        items_data = v_data.get('items', [])
        last_product_title = f"Multiple Items ({len(items_data)})"
        if len(items_data) == 1:
            p_id = items_data[0].get('seller_product') or items_data[0].get('product')
            try:
                sp = SellerProduct.objects.get(id=p_id)
                last_product_title = sp.title
            except Exception:
                pass

        return success_response({
            "code":              code,
            "seller_shop":       seller_shop,
            "product_title":     last_product_title,
            "discount_type":     discount_type,
            "discount_value":    discount_value,
            "discount_applied":  float(total_discount),
            "original_item_total": float(total_original),
            "final_item_total":    float(final_amount),
        }, message="Coupon applied successfully!")
