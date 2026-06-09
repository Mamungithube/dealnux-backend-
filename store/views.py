from decimal import Decimal

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
from django.db.models import Q, Sum, Avg, Count
from stripe.climate import Product

from payment.views import _calculate_order_amounts
from payment.utils import process_referral_reward_for_user

from .models import (
    ProductReview, SellerRequest, SellerProfile,
    SellerProduct, Order, Coupon, Dispute
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
    queryset = SellerProfile.objects.all()
    serializer_class = SellerProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return SellerProfile.objects.all()
        return SellerProfile.objects.filter(user=self.request.user)

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

        review_stats = ProductReview.objects.filter(product__seller=seller).aggregate(
            average_rating=Avg('rating'),
            total_reviews=Count('id')
        )

        data = {
            "shop_name": seller.shop_name,
            "stats": {
                "total_products": seller.total_products,
                "total_units_in_stock": total_units,
                "active_orders": Order.objects.filter(seller=seller, status__in=['PENDING', 'CONFIRMED', 'SHIPPED']).count(),
                "needs_action": Order.objects.filter(seller=seller, status='PENDING').count(),
                "this_month_earnings": float(this_month_earned),
                "total_earned": float(seller.total_earnings),
                "total_reviews": review_stats['total_reviews'],
                "average_rating": round(review_stats['average_rating'] or 0, 1),
            }
        }
        return success_response(data)

    # --- Detailed Shipping Page (GET & PATCH) ---
    @action(detail=False, methods=['get', 'patch'], url_path='dashboard/shipping')
    def dashboard_shipping(self, request):
        try:
            seller = request.user.seller_profile
        except SellerProfile.DoesNotExist:
            return error_response("Seller profile not found.", code=404)

        # --- ১. Update Logic (PATCH) ---
        if request.method == 'PATCH':
            data = request.data

            # Local Pickup Section
            pickup_data = data.get('local_pickup', {})
            if pickup_data:
                seller.local_pickup_active = pickup_data.get(
                    'active', seller.local_pickup_active)
                seller.pickup_address_street = pickup_data.get(
                    'address_street', seller.pickup_address_street)
                seller.pickup_address_city = pickup_data.get(
                    'address_city', seller.pickup_address_city)
                seller.pickup_address_state = pickup_data.get(
                    'address_state', seller.pickup_address_state)
                seller.pickup_address_zip = pickup_data.get(
                    'address_zip', seller.pickup_address_zip)
                seller.pickup_hours_start = pickup_data.get(
                    'hours_start', seller.pickup_hours_start)
                seller.pickup_hours_end = pickup_data.get(
                    'hours_end', seller.pickup_hours_end)
                seller.pickup_available_days = pickup_data.get(
                    'available_days', seller.pickup_available_days)

            # Local Delivery Section
            delivery_data = data.get('local_delivery', {})
            if delivery_data:
                seller.local_delivery_active = delivery_data.get(
                    'active', seller.local_delivery_active)
                seller.delivery_radius = delivery_data.get(
                    'radius', seller.delivery_radius)
                seller.delivery_fee = delivery_data.get(
                    'fee', seller.delivery_fee)
                seller.delivery_timeframe = delivery_data.get(
                    'timeframe', seller.delivery_timeframe)

            # Standard Shipping Section
            standard_data = data.get('standard_shipping', {})
            if standard_data:
                seller.standard_shipping_active = standard_data.get(
                    'active', seller.standard_shipping_active)
                seller.order_processing_time = standard_data.get(
                    'processing_time', seller.order_processing_time)
                seller.preferred_couriers = standard_data.get(
                    'preferred_couriers', seller.preferred_couriers)

            seller.save()
            return success_response(None, message="Shipping settings updated successfully.")

        # --- ২. Response Data (GET) ---
        response_data = {
            "local_pickup": {
                "active": seller.local_pickup_active,
                "address_street": seller.pickup_address_street,
                "address_city": seller.pickup_address_city,
                "address_state": seller.pickup_address_state,
                "address_zip": seller.pickup_address_zip,
                "hours_start": seller.pickup_hours_start.strftime("%H:%M:%S") if seller.pickup_hours_start else None,
                "hours_end": seller.pickup_hours_end.strftime("%H:%M:%S") if seller.pickup_hours_end else None,
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
        return success_response(response_data, message="Detailed shipping settings fetched.")

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
        return success_response(self.get_serializer(obj).data, message="Product updated.")

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

            # Try to process referral reward for the buyer if they were referred.
            process_referral_reward_for_user(request.user)

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

    @action(detail=False, methods=['get'], url_path='seller-orders')
    def seller_orders(self, request):
        """
        URL: GET /api/v1/store/orders/seller-orders/
        """
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
        """
        সেলার এটি কল করবে অর্ডারটি গ্রহণ করার জন্য।
        এটি স্ট্যাটাসকে PENDING থেকে সরাসরি ACCEPTED করবে।
        """
        order = self.get_object()

        # সেলার চেক
        if not request.user.is_staff and order.seller.user != request.user:
            return error_response("Unauthorized.", code=403)

        # সেলারের জন্য স্ট্যাটাস ফিক্সড: ACCEPTED
        order.status = 'ACCEPTED' 
        order.save(update_fields=['status', 'updated_at'])

        return success_response(
            {"order_number": order.order_number, "status": order.status}, 
            message="Order accepted by seller."
        )

    # ── Seller Action: Adding Tracking Number ──
    @action(detail=True, methods=['post', 'put', 'patch'], url_path='add-tracking')
    def add_tracking(self, request, pk=None):
        order = self.get_object()

        if order.seller.user != request.user and not request.user.is_staff:
            return error_response("You are not the seller of this order.", code=403)

        tracking_no = request.data.get('tracking_number')
        courier = request.data.get('courier_name')

        if not tracking_no:
            return error_response("Tracking number is required.", code=400)

        order.tracking_number = tracking_no
        if courier:
            order.courier_name = courier

        order.status = 'SHIPPED'
        order.save()

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
        """
        বায়ার এটি কল করবে প্রোডাক্ট হাতে পাওয়ার পর।
        এটি স্ট্যাটাসকে SHIPPED থেকে সরাসরি CONFIRMED করবে।
        """
        order = self.get_object()

        # বায়ার চেক
        if order.buyer != request.user:
            return error_response("Not authorized.", code=403)

        # লজিক চেক: আগে শিপড হতে হবে, তারপর বায়ার কনফার্ম করতে পারবে
        if order.status != 'SHIPPED':
            return error_response("You can only confirm after the order is SHIPPED.", code=400)

        from payment.models import PayoutRecord 

        with transaction.atomic():
            # বায়ারের কাজ: স্ট্যাটাস এখন CONFIRMED হবে
            order.status = 'CONFIRMED'
            order.is_accepted_by_buyer = True
            order.accepted_at = timezone.now()
            order.save()

            # ওয়ালেট আপডেট লজিক
            seller_profile = order.seller
            amount = order.item_total + order.shipping_fee
            seller_profile.pending_balance -= amount
            seller_profile.available_balance += amount
            seller_profile.total_earnings += amount
            seller_profile.save()

            # ড্যাশবোর্ডের জন্য রেকর্ড তৈরি
            import random, string
            p_id = "PAY-" + "".join(random.choices(string.digits, k=4))
            PayoutRecord.objects.create(
                seller=seller_profile, payout_id=p_id,
                amount=amount, method="Stripe Transfer", status="Paid"
            )

            # স্ট্রাইপ ট্রান্সফার (যদি একাউন্ট কানেক্টেড থাকে)
            if seller_profile.stripe_account_id and seller_profile.stripe_onboarding_completed:
                try:
                    import stripe
                    stripe.Transfer.create(
                        amount=int(amount * 100),
                        currency=order.currency.lower(),
                        destination=seller_profile.stripe_account_id,
                        transfer_group=f"ORDER_{order.order_number}",
                    )
                except Exception as e:
                    logger.error(f"Stripe Error: {str(e)}")

        return success_response(None, message="Order Confirmed! Funds released to seller.")
        


    # ── Admin Action: Process refund (Fault Logic) ──

    @action(detail=True, methods=['post'], url_path='process-refund', permission_classes=[IsAdminUser])
    def process_refund(self, request, pk=None):
        """
        Case 1: Seller fault -> Refund (Price + Shipping + Service Fee)
        Case 2: Buyer fault -> Refund (Price only, buyer pays shipping & fees)
        """
        order = self.get_object()
        fault = request.data.get('fault_party')

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
                # Full refund (price + shipping + fees)
                refund_amount = order.total_price
            else:
                refund_amount = order.item_total  # Partial refund (price only)

            order.refund_amount = refund_amount
            order.save()

        return success_response({"refund_amount": float(refund_amount)}, message=f"Refund processed. Fault: {fault}")

    # ── Buyer Action: Open Dispute ──

    @action(detail=True, methods=['post'], url_path='open-dispute')
    def open_dispute(self, request, pk=None):
        order = self.get_object()

        if order.buyer != request.user:
            return error_response("Not authorized", code=403)

        if order.status not in ['SHIPPED', 'DELIVERED']:
            return error_response("Dispute can only be opened after shipping.", code=400)

        if hasattr(order, 'dispute'):
            return error_response("A dispute is already open for this order.", code=400)

        with transaction.atomic():
            order.status = 'DISPUTED'
            order.save()

            Dispute.objects.create(
                order=order,
                reason=request.data.get('reason'),
                description=request.data.get('description'),
                evidence_image=request.FILES.get(
                    'evidence_image')
            )

        return success_response(None, message="Dispute opened. Admin will review it soon.")

    # ── Admin Action: Resolve Dispute (Approve/Reject + Fault Logic) ──
    @action(detail=True, methods=['post'], url_path='resolve-dispute', permission_classes=[IsAdminUser])
    def resolve_dispute(self, request, pk=None):
        order = self.get_object()
        if order.status != 'DISPUTED':
            return error_response("This order is not in dispute.", code=400)

        decision = request.data.get('decision')
        fault = request.data.get('fault_party')

        with transaction.atomic():
            dispute = order.dispute

            if decision == 'REJECT':

                dispute.status = 'REJECTED'
                order.status = 'SHIPPED'
                dispute.save()
                order.save()
                return success_response(None, message="Dispute rejected. Order set back to Shipped.")

            dispute.status = 'RESOLVED'
            order.status = 'REFUNDED'
            order.fault_party = fault

            seller = order.seller
            amount_held = order.item_total + order.shipping_fee
            seller.pending_balance -= amount_held
            seller.save()

            if fault == 'SELLER':
                refund_amount = order.total_price
            else:
                refund_amount = order.item_total

            order.refund_amount = refund_amount
            order.save()
            dispute.save()

        return success_response(
            {"refund_amount": float(refund_amount)},
            message=f"Dispute resolved. Refund of ${refund_amount} processed for {fault} fault."
        )


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

        items_data = serializer.validated_data['items']
        code = serializer.validated_data['coupon_code'].upper().strip()

        total_discount = Decimal('0')
        total_original = Decimal('0')
        applied_seller_shop = ""
        last_product_title = ""
        discount_type = ""
        discount_value = 0

        for item in items_data:
            p_id = item.get('seller_product')
            qty = int(item.get('quantity', 1))

            try:
                product = SellerProduct.objects.get(id=p_id, status='APPROVED')
                res = _calculate_order_amounts(product, qty, code)

                total_discount += res['discount_amount']
                total_original += Decimal(str(product.price * qty))

                applied_seller_shop = product.seller.shop_name
                last_product_title = product.title if len(
                    items_data) == 1 else f"Multiple Items ({len(items_data)})"

                coupon = Coupon.objects.filter(
                    code=code, seller=product.seller).first()
                if coupon:
                    discount_type = coupon.discount_type
                    discount_value = float(coupon.discount_value)

            except (SellerProduct.DoesNotExist, Exception):
                continue

        final_amount = total_original - total_discount

        return success_response({
            "code":              code,
            "seller_shop":       applied_seller_shop,
            "product_title":     last_product_title,
            "discount_type":     discount_type,
            "discount_value":    discount_value,
            "discount_applied":  float(total_discount),
            "original_item_total": float(total_original),
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
            "total_products": seller.total_products,
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
