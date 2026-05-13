from django.db import transaction
from django.utils import timezone
from rest_framework.views import APIView
import math
import time
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q, Sum
from stripe.climate import Product

from .models import (
    ProductReview, SellerRequest, SellerProfile,
    SellerProduct, Order, Coupon,
)
from .serializers import (
    SellerProductReviewSerializer, SellerRequestSerializer, AdminSellerRequestSerializer,
    SellerProfileSerializer,
    SellerProductSerializer, SellerProductPublicSerializer, AdminSellerProductSerializer,
    SellerProductImageSerializer,
    OrderSerializer, OrderCreateSerializer,
    CouponSerializer, CouponValidateSerializer,
)
logger = logging.getLogger(__name__)


class CustomPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        next_page_number = None
        if self.page.has_next():
            next_page_number = self.page.next_page_number()

        prev_page_number = None
        if self.page.has_previous():
            prev_page_number = self.page.previous_page_number()

        return Response({
            "success": True,
            "code": 200,
            "message": "Success",
            "timestamp": int(time.time()),
            "data": {
                "count": len(data),
                "results": data
            },
            "pagination": {
                "total_count": self.page.paginator.count,
                "total_pages": self.page.paginator.num_pages,
                "current_page": self.page.number,
                "page_size": self.get_page_size(self.request),
                "has_next": self.page.has_next(),
                "has_previous": self.page.has_previous(),
                "next_page": next_page_number,
                "prev_page": prev_page_number,
            }
        })
# ============================================================================
# Helpers
# ============================================================================


def success_response(data=None, message="Success", code=200):
    response = {
        "success": True,
        "code": code,
        "message": message,
        "timestamp": int(time.time()),
        "data": data or {},
    }
    if isinstance(data, dict) and 'pagination' in data:
        response['pagination'] = data.pop('pagination')
    return Response(response, status=code)


def error_response(message="Error", code=400, data=None):
    response = {
        "success": False,
        "code": code,
        "message": message,
        "timestamp": int(time.time()),
        "data": data or {},
    }
    return Response(response, status=code)


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


def is_approved_seller(user):
    """Check if user is an approved seller"""
    return hasattr(user, 'seller_profile') and user.seller_profile.is_active


# ============================================================================
# Seller Request ViewSet
# ============================================================================

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
            # Admin will be able to see all requests.
            return SellerRequest.objects.all().order_by('-created_at')
        # Normal users will only see their own requests.
        return SellerRequest.objects.filter(user=user)

    def get_serializer_class(self):
        if self.request.user.is_staff:
            return AdminSellerRequestSerializer
        return SellerRequestSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        # Original response format maintained
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

        with transaction.atomic():
            # 1. Request status update
            seller_request.status = 'APPROVED'
            seller_request.reviewed_at = timezone.now()
            seller_request.save()

            # 2. Create a seller profile (transfer all requested data to the profile)
            profile, created = SellerProfile.objects.get_or_create(
                user=seller_request.user,
                defaults={
                    'shop_name': seller_request.trade_name,
                    'shop_description': f"Primary Category: {seller_request.categories.first().name if seller_request.categories.exists() else 'N/A'}",
                    'phone_number': seller_request.contact_phone,
                    'legal_full_name': seller_request.contact_full_name,
                    'business_address': seller_request.experience_description,
                    'is_active': True
                }
            )

            # 3. Update Seller Flag in User Model
            user = seller_request.user
            user.ads_provided = True
            user.save(update_fields=['ads_provided'])

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

        seller_request.status = 'REJECTED'
        seller_request.admin_note = note
        seller_request.reviewed_at = timezone.now()
        seller_request.save()

        return Response({
            "success": True,
            "code": 200,
            "message": "Seller application rejected.",
            "data": {"admin_note": note}
        })

# ============================================================================
# Seller Profile ViewSet
# ============================================================================


class SellerProfileViewSet(viewsets.ModelViewSet):
    serializer_class = SellerProfileSerializer
    permission_classes = [IsAuthenticated]

    # --- Dashboard Overview Page ---
    @action(detail=False, methods=['get'], url_path='dashboard/overview')
    def dashboard_overview(self, request):
        seller = request.user.seller_profile
        today = timezone.now()

        this_month_earned = Order.objects.filter(
            seller=seller, status='ACCEPTED',
            created_at__month=today.month, created_at__year=today.year
        ).aggregate(total=Sum('item_total'))['total'] or 0

        total_units = SellerProduct.objects.filter(
            seller=seller, status='APPROVED'
        ).aggregate(total=Sum('quantity'))['total'] or 0

        data = {
            "shop_name": seller.shop_name,
            "stats": {
                "total_products": seller.total_products,
                "total_units_in_stock": total_units,
                "active_orders": Order.objects.filter(seller=seller, status__in=['PENDING', 'CONFIRMED', 'SHIPPED']).count(),
                "needs_action": Order.objects.filter(seller=seller, status='PENDING').count(),
                "this_month_earnings": float(this_month_earned),
                "total_earned": float(seller.total_earnings)
            }
        }
        return success_response(data)

    # --- Detailed Shipping Page (GET & PATCH) ---
    @action(detail=False, methods=['get', 'patch'], url_path='dashboard/shipping')
    def dashboard_shipping(self, request):
        seller = request.user.seller_profile

        if request.method == 'PATCH':
            # Local Pickup Update
            seller.local_pickup_active = request.data.get(
                'local_pickup_active', seller.local_pickup_active)
            seller.pickup_address_street = request.data.get(
                'pickup_address_street', seller.pickup_address_street)
            seller.pickup_address_city = request.data.get(
                'pickup_address_city', seller.pickup_address_city)
            seller.pickup_address_state = request.data.get(
                'pickup_address_state', seller.pickup_address_state)
            seller.pickup_address_zip = request.data.get(
                'pickup_address_zip', seller.pickup_address_zip)
            seller.pickup_hours_start = request.data.get(
                'pickup_hours_start', seller.pickup_hours_start)
            seller.pickup_hours_end = request.data.get(
                'pickup_hours_end', seller.pickup_hours_end)
            seller.pickup_available_days = request.data.get(
                'pickup_available_days', seller.pickup_available_days)

            # Local Delivery Update
            seller.local_delivery_active = request.data.get(
                'local_delivery_active', seller.local_delivery_active)
            seller.delivery_radius = request.data.get(
                'delivery_radius', seller.delivery_radius)
            seller.delivery_fee = request.data.get(
                'delivery_fee', seller.delivery_fee)
            seller.delivery_timeframe = request.data.get(
                'delivery_timeframe', seller.delivery_timeframe)

            # Standard Shipping Update
            seller.standard_shipping_active = request.data.get(
                'standard_shipping_active', seller.standard_shipping_active)
            seller.order_processing_time = request.data.get(
                'order_processing_time', seller.order_processing_time)
            seller.preferred_couriers = request.data.get(
                'preferred_couriers', seller.preferred_couriers)

            seller.save()
            return success_response(None, message="All shipping settings updated")

        # GET Response
        data = {
            "local_pickup": {
                "active": seller.local_pickup_active,
                "address": {
                    "street": seller.pickup_address_street,
                    "city": seller.pickup_address_city,
                    "state": seller.pickup_address_state,
                    "zip": seller.pickup_address_zip,
                },
                "hours": {
                    "start": seller.pickup_hours_start.strftime("%I:%M %p") if seller.pickup_hours_start else None,
                    "end": seller.pickup_hours_end.strftime("%I:%M %p") if seller.pickup_hours_end else None,
                },
                "available_days": seller.pickup_available_days
            },
            "local_delivery": {
                "active": seller.local_delivery_active,
                "radius": seller.delivery_radius,
                "fee": float(seller.delivery_fee),
                "timeframe": seller.delivery_timeframe
            },
            "standard_shipping": {
                "active": seller.standard_shipping_active,
                "processing_time": seller.order_processing_time,
                "preferred_couriers": seller.preferred_couriers
            }
        }
        return success_response(data)

    # --- Payouts/Wallet Page ---
    @action(detail=False, methods=['get'], url_path='dashboard/payouts')
    def dashboard_payouts(self, request):
        seller = request.user.seller_profile
        data = {
            "available_balance": float(seller.available_balance),
            "pending_balance": float(seller.pending_balance),
            "total_withdrawn": float(seller.total_withdrawn),
            "total_earned": float(seller.total_earnings),
            "payout_history": []  # This will be populated from the payment app later
        }
        return success_response(data)


# ============================================================================
# Seller Product ViewSet
# ============================================================================

class SellerProductViewSet(viewsets.ModelViewSet):
    """
    Seller manages their own products.
    Admin approves/rejects them.
    Public (AllowAny) - only shows APPROVED products.
    """
    pagination_class = CustomPagination

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'public_list']:
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.request.user.is_authenticated and self.request.user.is_staff:
            return AdminSellerProductSerializer
        if self.action in ['list', 'retrieve']:
            return SellerProductPublicSerializer
        return SellerProductSerializer

    def get_queryset(self):
        user = self.request.user

        # Admin:
        if user.is_authenticated and user.is_staff:
            qs = SellerProduct.objects.select_related(
                'seller', 'category').all()
            status_filter = self.request.query_params.get('status')
            if status_filter:
                qs = qs.filter(status=status_filter.upper())
            return qs.order_by('?')

        if user.is_authenticated and is_approved_seller(user):
            if self.action in ['update', 'partial_update', 'destroy', 'my_products']:

                return SellerProduct.objects.filter(seller=user.seller_profile).order_by('-created_at')

        qs = SellerProduct.objects.filter(
            status='APPROVED').select_related('seller', 'category')

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(title__icontains=search)
                | Q(description__icontains=search)
                | Q(brand__icontains=search)
            )

        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category__slug=category)

        return qs.order_by('?')

    def perform_create(self, serializer):
        if not is_approved_seller(self.request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(
                "You must be an approved seller to add products.")
        serializer.save(seller=self.request.user.seller_profile)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return success_response(serializer.data, message="Product submitted for review.", code=201)

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(qs, many=True)
        return success_response(serializer.data, message="Products fetched")

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return success_response(serializer.data, message="Product fetched")

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if not request.user.is_staff and instance.seller.user != request.user:
            return error_response("Permission denied.", code=403)
        # When editing an approved product, it returns to PENDING
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(
            instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        if not request.user.is_staff and obj.status == 'APPROVED':
            obj.status = 'PENDING'
            obj.save(update_fields=['status'])
        return success_response(self.get_serializer(obj).data, message="Product updated. Pending review.")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if not request.user.is_staff and instance.seller.user != request.user:
            return error_response("Permission denied.", code=403)
        instance.delete()
        return success_response({}, message="Product deleted.")

    # ── Seller: their own products ─────────────────────────────────────────

    @action(detail=False, methods=['get'])
    def my_products(self, request):
        if not is_approved_seller(request.user):
            return error_response("You are not an approved seller.", code=403)

        try:
            page = max(1, int(request.query_params.get('page', 1)))
            page_size = min(
                max(1, int(request.query_params.get('page_size', 10))), 50)
        except (ValueError, TypeError):
            page, page_size = 1, 10

        qs = SellerProduct.objects.filter(seller=request.user.seller_profile)
        total_count = qs.count()
        total_pages = math.ceil(total_count / page_size)

        start = (page - 1) * page_size
        end = start + page_size
        results = qs[start:end]

        serializer = SellerProductSerializer(
            results, many=True, context={'request': request})

        return success_response({
            'products': serializer.data,
            'pagination': {
                'total_count':  total_count,
                'total_pages':  total_pages,
                'current_page': page,
                'page_size':    page_size,
                'has_next':     page < total_pages,
                'has_previous': page > 1,
                'next_page':    page + 1 if page < total_pages else None,
                'prev_page':    page - 1 if page > 1 else None,
            },
        }, message="Your products fetched")

    # ── Admin: approve / reject ──────────────────────────────────────────

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def approve(self, request, pk=None):
        product = self.get_object()
        if product.status == 'APPROVED':
            return error_response("Already approved.", code=400)
        product.approve(admin_user=request.user)
        return success_response(
            AdminSellerProductSerializer(product).data,
            message="Product approved and listed."
        )

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def reject(self, request, pk=None):
        product = self.get_object()
        note = request.data.get('admin_note', '')
        product.reject(admin_user=request.user, note=note)
        return success_response(
            AdminSellerProductSerializer(product).data,
            message="Product rejected."
        )

    # ── Seller: image upload ────────────────────────────────────────────

    @action(detail=True, methods=['post'], url_path='upload-image')
    def upload_image(self, request, pk=None):
        product = self.get_object()
        if not request.user.is_staff and product.seller.user != request.user:
            return error_response("Permission denied.", code=403)

        serializer = SellerProductImageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(product=product)
        return success_response(serializer.data, message="Image uploaded.", code=201)

# ============================================================================
# Order ViewSet
# ============================================================================


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
            return Order.objects.all().order_by('-created_at')

        return Order.objects.filter(
            Q(buyer=user) | Q(seller__user=user)
        ).select_related('buyer', 'seller', 'seller_product').distinct()

    def create(self, request, *args, **kwargs):
        """The money will go to your pending balance (it's better to do it in the webhook, but you can put it here)"""
        serializer = self.get_serializer(
            data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            order = serializer.save()

            # The money will go to the seller's pending balance (it's better to do it in the webhook, but you can put it here)
            # Update the seller's pending balance
            seller_profile = order.seller
            # The item price + shipping fee will be added to the seller's pending wallet
            amount_for_seller = order.item_total + order.shipping_fee
            seller_profile.pending_balance += amount_for_seller
            seller_profile.save(update_fields=['pending_balance'])

        return success_response(
            OrderSerializer(order).data,
            message="Order placed and funds held in escrow.",
            code=201
        )

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)

        # Filter: by status (?status=SHIPPED)
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

    # ── Seller Action: Adding Tracking Number ──
    @action(detail=True, methods=['post'], url_path='add-tracking')
    def add_tracking(self, request, pk=None):
        order = self.get_object()

        # Only the seller or admin of the order can provide tracking.
        if order.seller.user != request.user and not request.user.is_staff:
            return error_response("You are not the seller of this order.", code=403)

        tracking_no = request.data.get('tracking_number')
        if not tracking_no:
            return error_response("Tracking number is required.", code=400)

        order.tracking_number = tracking_no
        order.status = 'SHIPPED'
        order.save(update_fields=['tracking_number', 'status'])

        return success_response(OrderSerializer(order).data, message="Order marked as shipped.")

    # ── Buyer Action: Received the product (The Payout Trigger) ──
    @action(detail=True, methods=['post'], url_path='accept-order')
    def accept_order(self, request, pk=None):
        """
        When the buyer clicks the "Accept" button:
        The money will be transferred from the 'Pending Balance' to the 'Available Balance'.
        """
        order = self.get_object()

        if order.buyer != request.user:
            return error_response("Only the buyer can accept this delivery.", code=403)

        if order.status == 'ACCEPTED':
            return error_response("Order is already accepted.", code=400)

        with transaction.atomic():
            # status update 
            order.status = 'ACCEPTED'
            order.is_accepted_by_buyer = True
            order.accepted_at = timezone.now()
            order.save()

            # wallet update
            seller_profile = order.seller
            amount_to_release = order.item_total + order.shipping_fee
            seller_profile.pending_balance -= amount_to_release
            seller_profile.available_balance += amount_to_release
            seller_profile.total_earnings += amount_to_release

            seller_profile.save()

        return success_response(None, message="Payment released to seller successfully!")

    # ── Admin Action: Process refund (Fault Logic) ──
    @action(detail=True, methods=['post'], url_path='process-refund', permission_classes=[IsAdminUser])
    def process_refund(self, request, pk=None):
        """
        Case 1: Seller fault -> Refund (Price + Shipping + Service Fee)
        Case 2: Buyer fault -> Refund (Price only, buyer pays shipping & fees)
        """
        order = self.get_object()
        fault = request.data.get('fault_party')  # 'SELLER' or 'BUYER'

        if fault not in ['SELLER', 'BUYER']:
            return error_response("Invalid fault_party. Must be SELLER or BUYER.", code=400)

        with transaction.atomic():
            order.status = 'REFUNDED'
            order.fault_party = fault

            # Deduct money from the seller's pending wallet (because the order failed)
            seller_profile = order.seller
            amount_to_deduct = order.item_total + order.shipping_fee
            seller_profile.pending_balance -= amount_to_deduct
            seller_profile.save()

            # Calculation of how much will be refunded to the buyer
            if fault == 'SELLER':
                refund_amount = order.total_price  # Full refund (price + shipping + fees)
            else:
                refund_amount = order.item_total  # Partial refund (price only)

            order.refund_amount = refund_amount
            order.save()

        return success_response({"refund_amount": float(refund_amount)}, message=f"Refund processed. Fault: {fault}")


# ============================================================================
# Product Review ViewSet
# ============================================================================


class ProductReviewViewSet(viewsets.ModelViewSet):
    serializer_class = SellerProductReviewSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_queryset(self):
        product_id = self.request.query_params.get('product_id')
        qs = ProductReview.objects.select_related('user', 'product')
        if product_id:
            qs = qs.filter(product_id=product_id)
        return qs

    def create(self, request, *args, **kwargs):
        product_id = request.data.get('product_id')
        if not product_id:
            return error_response("product_id is required", code=400)

        from store.models import SellerProduct
        product = SellerProduct.objects.filter(
            id=product_id, status='APPROVED').first()
        if not product:
            return error_response("Product not found", code=404)

        if ProductReview.objects.filter(product=product, user=request.user).exists():
            return error_response("You have already reviewed this product.", code=400)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user, product=product)
        return success_response(serializer.data, message="Review submitted successfully.", code=201)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.user != request.user:
            return error_response("Permission denied.", code=403)
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(
            instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response(serializer.data, message="Review updated.")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.user != request.user and not request.user.is_staff:
            return error_response("Permission denied.", code=403)
        instance.delete()
        return success_response({}, message="Review deleted.")

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())

        # Summary stats
        from django.db.models import Avg, Count
        stats = qs.aggregate(avg_rating=Avg('rating'), total=Count('id'))

        serializer = self.get_serializer(qs, many=True)
        return success_response({
            "average_rating": round(stats['avg_rating'] or 0, 1),
            "total_reviews":  stats['total'],
            "reviews":        serializer.data
        }, message="Reviews fetched.")


# ============================================================================
# Coupon ViewSet
# ============================================================================

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

    # ── Buyer: coupon validate ──────────────────────────────────────────

    @action(detail=False, methods=['post'], url_path='validate', permission_classes=[IsAuthenticated])
    def validate_coupon(self, request):
        serializer = CouponValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        coupon = serializer.validated_data['coupon']
        product = serializer.validated_data['product']
        item_total = serializer.validated_data['item_total']

        # discount calculation
        if coupon.discount_type == 'PERCENTAGE':
            discount = (item_total * coupon.discount_value) / 100
        else:
            discount = min(coupon.discount_value, item_total)

        final_amount = item_total - discount

        return success_response({
            "code":              coupon.code,
            "seller_shop":       product.seller.shop_name,
            "product_title":     product.title,
            "discount_type":     coupon.discount_type,
            "discount_value":    float(coupon.discount_value),
            "discount_applied":  float(discount),
            "original_item_total": float(item_total),
            "final_item_total":    float(final_amount),
        }, message="Coupon applied successfully!")


# ============================================================================
# Seller Dashboard
# ============================================================================


class SellerDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_approved_seller(request.user):
            return error_response("You are not an approved seller.", code=403)

        seller = request.user.seller_profile

        # product stats count
        pending_products = SellerProduct.objects.filter(
            seller=seller, status='PENDING').count()
        approved_products = SellerProduct.objects.filter(
            seller=seller, status='APPROVED').count()

        # Reset 5 Orders
        recent_orders = Order.objects.filter(
            seller=seller).order_by('-created_at')[:5]

        data = {
            "shop_name": seller.shop_name,
            "wallet": {
                "pending":    float(seller.pending_balance),
                "available":  float(seller.available_balance),
                "withdrawn":  float(seller.total_withdrawn),
                "total_earned": float(seller.total_earnings),
            },
            "total_products": seller.total_products,
            "total_orders":   seller.total_orders,
            "product_stats": {
                "pending":  pending_products,
                "approved": approved_products,
            },
            "recent_orders": OrderSerializer(recent_orders, many=True).data,
        }

        return success_response(data, message="Seller dashboard fetched")
