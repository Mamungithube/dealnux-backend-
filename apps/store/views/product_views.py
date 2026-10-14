import math
from django.db.models import Avg, Count, Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated

from ..models import ProductReview, SellerProduct
from ..serializers import (
    AdminSellerProductSerializer,
    SellerProductImageSerializer,
    SellerProductPublicSerializer,
    SellerProductReviewSerializer,
    SellerProductSerializer,
)
from .seller_views import is_approved_seller
from config.pagination import CustomPagination
from config.responses import error_response, success_response


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
                'seller', 'seller__user', 'category', 'linked_product'
            ).prefetch_related('images').all()
            status_filter = self.request.query_params.get('status')
            if status_filter:
                qs = qs.filter(status=status_filter.upper())
            return qs.order_by('?')

        if user.is_authenticated and is_approved_seller(user):
            if self.action in ['update', 'partial_update', 'destroy', 'my_products']:
                return SellerProduct.objects.select_related(
                    'seller', 'seller__user', 'category', 'linked_product'
                ).prefetch_related('images').filter(seller=user.seller_profile, is_active=True).order_by('-created_at')

        qs = SellerProduct.objects.filter(
            status='APPROVED', is_active=True
        ).select_related('seller', 'seller__user', 'category', 'linked_product').prefetch_related('images')

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
            raise PermissionDenied(
                "You must be an approved seller to add products.")
        serializer.save(seller=self.request.user.seller_profile)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return success_response(serializer.data, message="Product added successfully.", code=201)

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
        self.perform_destroy(instance)
        return success_response({}, message="Product deleted.")
    
    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=['is_active'])

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

        qs = SellerProduct.objects.filter(seller=request.user.seller_profile, is_active=True)
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

        stats = qs.aggregate(avg_rating=Avg('rating'), total=Count('id'))

        serializer = self.get_serializer(qs, many=True)
        return success_response({
            "average_rating": round(stats['avg_rating'] or 0, 1),
            "total_reviews":  stats['total'],
            "reviews":        serializer.data
        }, message="Reviews fetched.")
