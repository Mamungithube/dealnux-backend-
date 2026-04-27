from rest_framework.views import APIView
import math
import time
import logging
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q
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
    User submits a request to become a seller.
    Admin approves/rejects it.
    """
    serializer_class = SellerRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return SellerRequest.objects.select_related('user', 'reviewed_by').all()
        # Normal user can only see their own
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
        return success_response(serializer.data, message="Seller request submitted successfully", code=201)

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        # Admin filter by status
        status_filter = request.query_params.get('status')
        if status_filter and request.user.is_staff:
            qs = qs.filter(status=status_filter.upper())
        serializer = self.get_serializer(qs, many=True)
        return success_response(serializer.data, message="Seller requests fetched")

    # ── Admin Actions ──────────────────────────────────────────────────────

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def approve(self, request, pk=None):
        seller_request = self.get_object()

        if seller_request.status == 'APPROVED':
            return error_response("Already approved.", code=400)

        with transaction.atomic():
            seller_request.approve(admin_user=request.user)

            seller_profile, created = SellerProfile.objects.get_or_create(
                user=seller_request.user,
                defaults={
                    'shop_name': seller_request.shop_name,
                    'phone_number': seller_request.phone_number,
                    'is_active': True
                }
            )

        return success_response(
            AdminSellerRequestSerializer(seller_request).data,
            message=f"{seller_request.user.email} approved and profile created successfully."
        )

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def reject(self, request, pk=None):
        seller_request = self.get_object()
        note = request.data.get('admin_note', '')

        if seller_request.status == 'REJECTED':
            return error_response("Already rejected.", code=400)

        seller_request.reject(admin_user=request.user, note=note)
        return success_response(
            AdminSellerRequestSerializer(seller_request).data,
            message="Seller request rejected."
        )


# ============================================================================
# Seller Profile ViewSet
# ============================================================================

class SellerProfileViewSet(viewsets.ModelViewSet):
    serializer_class = SellerProfileSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    def get_queryset(self):
        if self.request.user.is_staff:
            return SellerProfile.objects.select_related('user').all()
        return SellerProfile.objects.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        serializer = self.get_serializer(qs, many=True)
        return success_response(serializer.data, message="Seller profiles fetched")

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return success_response(serializer.data, message="Seller profile fetched")

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if not request.user.is_staff and instance.user != request.user:
            return error_response("Permission denied.", code=403)
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(
            instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response(serializer.data, message="Seller profile updated")

    @action(detail=False, methods=['get'])
    def me(self, request):
        """View your own seller profile"""
        try:
            profile = request.user.seller_profile
        except SellerProfile.DoesNotExist:
            return error_response("You are not an approved seller yet.", code=404)
        serializer = self.get_serializer(profile)
        return success_response(serializer.data, message="Your seller profile")


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

        serializer = SellerProductSerializer(results, many=True, context={'request': request})

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
    pagination_class = StandardPagination

    def get_serializer_class(self):
        if self.action == 'create':
            return OrderCreateSerializer
        return OrderSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Order.objects.select_related('buyer', 'seller', 'seller_product').all()
        # Buyer's own orders
        qs = Order.objects.filter(buyer=user)
        # Seller's shop orders
        if is_approved_seller(user):
            qs = qs | Order.objects.filter(seller=user.seller_profile)
        return qs.distinct()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return success_response(
            OrderSerializer(order).data,
            message="Order placed successfully.",
            code=201
        )

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = OrderSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        return success_response(OrderSerializer(qs, many=True).data, message="Orders fetched")

    # ── Seller: order status update ──────────────────────────────────────

    @action(detail=True, methods=['post'], url_path='update-status')
    def update_status(self, request, pk=None):
        order = self.get_object()
        new_status = request.data.get('status', '').upper()

        allowed_statuses = [s[0] for s in Order.STATUS_CHOICES]
        if new_status not in allowed_statuses:
            return error_response(f"Invalid status. Choose from: {allowed_statuses}", code=400)

        # Only seller or admin can change status
        if not request.user.is_staff:
            if not is_approved_seller(request.user) or order.seller.user != request.user:
                return error_response("Permission denied.", code=403)

        order.status = new_status
        if new_status == 'SHIPPED':
            order.tracking_number = request.data.get('tracking_number', '')
        order.save()
        return success_response(OrderSerializer(order).data, message=f"Order status updated to {new_status}")

    @action(detail=False, methods=['get'], url_path='my-orders')
    def my_orders(self, request):
        qs = Order.objects.filter(buyer=request.user)
        serializer = OrderSerializer(qs, many=True)
        return success_response(serializer.data, message="Your orders fetched")

    @action(detail=False, methods=['get'], url_path='seller-orders')
    def seller_orders(self, request):
        if not is_approved_seller(request.user):
            return error_response("You are not an approved seller.", code=403)
        qs = Order.objects.filter(seller=request.user.seller_profile)
        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter.upper())
        serializer = OrderSerializer(qs, many=True)
        return success_response(serializer.data, message="Shop orders fetched")


# ============================================================================
# Product Review ViewSet
# ============================================================================


class ProductReviewViewSet(viewsets.ModelViewSet):
    """
    GET    /api/v1/reviews/?product_id=
    POST   /api/v1/reviews/     
    PATCH  /api/v1/reviews/<id>/     
    DELETE /api/v1/reviews/<id>/  
    """
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

        # ✅ শুধু SellerProduct চেক করো
        from store.models import SellerProduct
        product = SellerProduct.objects.filter(id=product_id, status='APPROVED').first()
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
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
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
        # আমাদের নতুন সিরিয়ালাইজার ব্যবহার করছি
        serializer = CouponValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        coupon = serializer.validated_data['coupon']
        product = serializer.validated_data['product']
        item_total = serializer.validated_data['item_total']

        # ডিসকাউন্ট হিসাব
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
        pending = SellerProduct.objects.filter(
            seller=seller, status='PENDING').count()
        approved = SellerProduct.objects.filter(
            seller=seller, status='APPROVED').count()
        rejected = SellerProduct.objects.filter(
            seller=seller, status='REJECTED').count()

        recent_orders = Order.objects.filter(
            seller=seller).order_by('-created_at')[:5]

        data = {
            "shop_name":      seller.shop_name,
            "total_products": seller.total_products,
            "total_orders":   seller.total_orders,
            "total_earnings": float(seller.total_earnings),
            "product_stats": {
                "pending":  pending,
                "approved": approved,
                "rejected": rejected,
            },
            "recent_orders": OrderSerializer(recent_orders, many=True).data,
        }

        return success_response(data, message="Seller dashboard fetched")


