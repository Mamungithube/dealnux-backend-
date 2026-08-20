from django.utils import timezone
from datetime import timedelta
import time
import logging
import math
import re
from decimal import Decimal
from difflib import SequenceMatcher

from django.db import transaction
from django.db.models import Q, F, Min, Count, Sum, Avg, Value, Case, When, FloatField
from django.db.models.functions import TruncDate
from django.core.cache import cache
from django.contrib.postgres.search import TrigramSimilarity

from rest_framework import viewsets, generics, permissions as drf_permissions
from rest_framework.views import APIView
from rest_framework.decorators import api_view, action, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import ValidationError

from rapidfuzz import fuzz

from api_integration.product_matcher import calculate_match_score, get_product_fingerprint
from api_integration.models import (
    Product, ProductListing, Platform, Category,
    CartItem, SavingsActivity, Favorite, PriceAlert
)
from api_integration.serializers import (
    ProductSerializer, ProductDetailSerializer,
    ProductListingSerializer, PlatformSerializer,
    CategorySerializer, PriceHistorySerializer,
    CartItemSerializer, FavoriteSerializer,
    CategoryTreeSerializer, CategoryChildSerializer, PriceAlertSerializer
)
from notifications.models import Notification
from notifications.serializers import NotificationSerializer
from store.serializers import SellerProductSerializer
from api_integration.db_helpers import save_generic_product_to_db

from dealnux.responses import success_response, error_response

logger = logging.getLogger(__name__)


# -------------------------- User Cart Management ViewSet (Add, List, Checkout Options & Savings) --------------------------
class CartViewSet(viewsets.ModelViewSet):
    serializer_class = CartItemSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CartItem.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def _success(self, data, message="Success", code=200):
        return Response({
            "success":   True,
            "code":      code,
            "message":   message,
            "timestamp": int(time.time()),
            "data":      data,
        }, status=code)

    def _error(self, message="Error", code=400):
        return Response({
            "success":   False,
            "code":      code,
            "message":   message,
            "timestamp": int(time.time()),
            "data":      {},
        }, status=code)

    def create(self, request, *args, **kwargs):
        product_id = request.data.get('product_id')
        quantity = request.data.get('quantity', 1)

        if not product_id:
            return self._error("product_id is required", code=400)

        product = None

        # 1. SellerProduct দিয়ে খোঁজো
        try:
            from store.models import SellerProduct
            from api_integration.models import Product, Category
            from django.utils.text import slugify
            import uuid

            seller_product_obj = SellerProduct.objects.get(
                id=product_id, status='APPROVED')
            product = seller_product_obj.linked_product

            # linked_product নেই — নতুন Product বানিয়ে link করো
            if not product:
                # category match করো
                category = None
                if seller_product_obj.category:
                    category = seller_product_obj.category  # already a Category FK? check করো
                
                slug = slugify(seller_product_obj.title)[:490]
                # slug unique হতে হবে
                if Product.objects.filter(slug=slug).exists():
                    slug = f"{slug}-{str(uuid.uuid4())[:8]}"

                product = Product.objects.create(
                    title=seller_product_obj.title,
                    slug=slug,
                    description=seller_product_obj.description or '',
                    brand=seller_product_obj.brand or '',
                    main_image='',
                    category=category,
                    is_active=True,
                )

                seller_product_obj.linked_product = product
                seller_product_obj.save(update_fields=['linked_product'])

        except SellerProduct.DoesNotExist:
            pass

        # 2. fallback — Product table এ সরাসরি খোঁজো
        if not product:
            try:
                product = Product.objects.get(id=product_id)
            except Product.DoesNotExist:
                pass

        if not product:
            return self._error(f"Product not found with id '{product_id}'", code=404)

        if CartItem.objects.filter(user=request.user, product=product).exists():
            return self._error("This product is already in your cart", code=400)

        cart_item = CartItem.objects.create(
            user=request.user,
            product=product,
            quantity=quantity,
        )

        serializer = self.get_serializer(cart_item)
        return self._success(serializer.data, message="Item added to cart", code=201)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return self._success(serializer.data, message="Cart item fetched")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        grouped = {}
        total_items = 0
        total_price = 0.0

        for item in serializer.data:
            listing = item.get('listing')
            if not listing:
                continue

            platform = listing.get('platform_name', 'Unknown')

            entry = {
                "id":            item['id'],
                "product":       item['product'],
                "product_title": item['product_title'],
                "product_image": item['product_image'],
                "quantity":      item['quantity'],
                "listing":       listing,
            }

            if platform not in grouped:
                grouped[platform] = []

            grouped[platform].append(entry)

            total_items += item['quantity']
            total_price += listing.get('total_price', 0.0) * item['quantity']

        summary = {
            "total_platforms": len(grouped),
            "total_items":     total_items,
            "total_price":     round(total_price, 2),
            "currency":        "USD",
        }

        return self._success(
            {"summary": summary, "platforms": grouped},
            message="Cart items fetched"
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return self._success(serializer.data, message="Cart item updated")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return self._success({}, message="Item removed from cart")

    @action(detail=False, methods=['get'])
    def checkout_options(self, request):
        cart_items = self.get_queryset()

        # . Definite data collection
        optimized_data = {}  # {platform: [items]}
        single_store_data = {'BestBuy': []}

        total_opt_price = 0
        total_single_price = 0

        for item in cart_items:
            # Main Logic: Best cheap deal among all listings
            best_listing = ProductListing.objects.filter(
                product=item.product).order_by('price').first()

            item_total = float(best_listing.price) * item.quantity
            total_opt_price += item_total

            plat = best_listing.platform.name
            if plat not in optimized_data:
                optimized_data[plat] = []
            optimized_data[plat].append(
                {"title": item.product.title, "price": float(best_listing.price)})

        total_saved = 50.00

        return success_response({
            "options": {
                "single_store": {
                    "title": "Single Store",
                    "platform": "Best Buy",
                    "total_cost": 1500.00,
                    "shipments": 1
                },
                "optimized_split": {
                    "title": "Optimized Split",
                    "total_cost": total_opt_price,
                    "total_saved": total_saved,
                    "shipments": len(optimized_data),
                    "breakdown": optimized_data
                }
            },
            "savings_breakdown": {
                "original_total": 1500.00,
                "coupon_savings": 50.00,
                "price_match_comparison": total_saved,
                "final_price": total_opt_price
            }
        })

    @action(detail=False, methods=['post'])
    def complete_checkout(self, request):
        cart_items = self.get_queryset()
        if not cart_items.exists():
            raise ValidationError({"cart": "Your cart is empty."})

        original_total = 0
        optimized_total = 0
        activities_to_create = []

        for item in cart_items:
            qty = item.quantity
            product = item.product

            cheapest = ProductListing.objects.filter(
                product=product, is_available=True
            ).order_by('price').first()

            if not cheapest:
                continue

            current_price = cheapest.price * qty
            original_total += current_price
            opt_price = cheapest.price * qty
            optimized_total += opt_price

            item_saved = float(current_price - opt_price)
            if item_saved > 0:
                activities_to_create.append(SavingsActivity(
                    user=request.user,
                    title=product.title,
                    saved_amount=item_saved,
                ))

        total_saved = float(original_total - optimized_total)

        with transaction.atomic():
            user = request.user
            if total_saved > 0:
                current_savings = getattr(user, 'total_lifetime_savings', 0)
                user.total_lifetime_savings = float(
                    current_savings) + total_saved
                user.save()
                if activities_to_create:
                    SavingsActivity.objects.bulk_create(activities_to_create)
            cart_items.delete()

        recent = SavingsActivity.objects.filter(
            user=request.user).order_by('-created_at')[:5]
        data = {
            "total_paid":             float(optimized_total),
            "total_saved_this_order": total_saved,
            "lifetime_savings_now":   float(getattr(user, 'total_lifetime_savings', 0)),
            "recent_activity": [
                {"title": a.title, "saved_amount": float(
                    a.saved_amount), "date": a.time_ago}
                for a in recent
            ],
        }
        return self._success(data, message="Checkout completed successfully")

    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        user = request.user
        recent = SavingsActivity.objects.filter(
            user=user).order_by('-created_at')[:5]
        data = {
            "total_lifetime_savings": float(getattr(user, 'total_lifetime_savings', 0.0)),
            "recent_activity": [
                {"title": a.title, "saved_amount": float(
                    a.saved_amount), "date": a.time_ago}
                for a in recent
            ],
        }
        return self._success(data, message="Dashboard data fetched successfully")


# -------------------------- User Savings Analytics & 30-Day Dashboard Trend View --------------------------
class DashboardSavingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        recent = SavingsActivity.objects.filter(
            user=user
        ).order_by('-created_at')[:5]

        thirty_days_ago = timezone.now().date() - timedelta(days=30)

        trend_data = SavingsActivity.objects.filter(
            user=user,
            created_at__date__gte=thirty_days_ago
        ).annotate(
            day=TruncDate('created_at')
        ).values('day').annotate(
            total=Sum('saved_amount')
        ).order_by('day')

        trend_map = {item['day'].strftime(
            '%Y-%m-%d'): float(item['total']) for item in trend_data}

        graph_list = []
        for i in range(30, -1, -1): 
            date_str = (timezone.now().date() -
                        timedelta(days=i)).strftime('%Y-%m-%d')
            graph_list.append({
                "date": date_str,
                "amount": trend_map.get(date_str, 0.0)  
            })

        data = {
            "total_lifetime_savings": float(getattr(user, 'total_lifetime_savings', 0.0)),
            "savings_trend": graph_list,  
            "recent_activity": [
                {
                    "title": a.title,
                    "saved_amount": float(a.saved_amount),
                    "date": a.time_ago
                } for a in recent
            ],
        }

        return success_response(data, message="Dashboard data fetched successfully")


# -------------------------- User Product Favorites / Wishlist Management ViewSet --------------------------
class FavoriteViewSet(viewsets.ModelViewSet):
    serializer_class = FavoriteSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'delete']

    def get_queryset(self):
        return Favorite.objects.filter(
            user=self.request.user
        ).select_related('product')

    def _success(self, data, message="Success", code=200):
        return Response({
            "success":   True,
            "code":      code,
            "message":   message,
            "timestamp": int(time.time()),
            "data":      data,
        }, status=code)

    def _error(self, message="Error", code=400):
        return Response({
            "success":   False,
            "code":      code,
            "message":   message,
            "timestamp": int(time.time()),
            "data":      {},
        }, status=code)

    def create(self, request, *args, **kwargs):
        product_id = request.data.get('product_id')

        if not product_id:
            return self._error("product_id is required", code=400)

        product = None

        try:
            from store.models import SellerProduct
            seller_product = SellerProduct.objects.get(
                id=product_id, status='APPROVED')
            product = seller_product.linked_product
        except SellerProduct.DoesNotExist:
            pass

        if not product:
            product = Product.objects.filter(id=product_id).first()

        if not product:
            return self._error("Product not found", code=404)

        favorite, created = Favorite.objects.get_or_create(
            user=request.user, product=product
        )
        if not created:
            return self._error("Product already in favorites", code=400)

        serializer = self.get_serializer(favorite)
        return self._success(serializer.data, message="Added to favorites", code=201)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response({
            "success": True, "code": 200,
            "message": "Removed from favorites",
            "timestamp": int(time.time()),
            "data": {},
        }, status=200)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        favorite_ids = set(queryset.values_list('product_id', flat=True))

        serializer = FavoriteSerializer(
            queryset,
            many=True,
            context={
                **self.get_serializer_context(),
                'favorite_ids': favorite_ids,
            }
        )

        return Response({
            "success": True, "code": 200,
            "message": "Favorites fetched",
            "timestamp": int(time.time()),
            "data": {"count": queryset.count(), "favorites": serializer.data},
        }, status=200)

    @action(detail=False, methods=['delete'], url_path='remove')
    def remove(self, request):
        product_id = request.data.get('product_id')

        if not product_id:
            return self._error("product_id is required", code=400)

        favorite = Favorite.objects.filter(
            user=request.user, product_id=product_id
        ).first()

        if not favorite:
            return self._error("Favorite not found", code=404)

        favorite.delete()
        return self._success(
            {},
            message="Removed from favorites",
            code=200,
        )

    @action(detail=False, methods=['get'], url_path='check/(?P<product_id>[^/.]+)')
    def check(self, request, product_id=None):
        is_favorite = Favorite.objects.filter(
            user=request.user, product_id=product_id).exists()
        return Response({
            "success": True, "code": 200, "message": "Checked",
            "timestamp": int(time.time()),
            "data": {"is_favorite": is_favorite, "product_id": product_id},
        })

    @action(detail=False, methods=['post'], url_path='toggle')
    def toggle(self, request):
        product_id = request.data.get('product_id')

        if not product_id:
            return self._error("product_id is required", code=400)

        product = None

        try:
            from store.models import SellerProduct
            seller_product = SellerProduct.objects.get(
                id=product_id, status='APPROVED')
            product = seller_product.linked_product
        except SellerProduct.DoesNotExist:
            pass

        if not product:
            product = Product.objects.filter(id=product_id).first()

        if not product:
            return self._error("Product not found", code=404)

        favorite = Favorite.objects.filter(
            user=request.user, product=product).first()
        if favorite:
            favorite.delete()
            return self._success(
                {"is_favorite": False, "product_id": product_id},
                message="Removed from favorites",
            )

        Favorite.objects.create(user=request.user, product=product)
        return self._success(
            {"is_favorite": True, "product_id": product_id},
            message="Added to favorites",
            code=201,
        )


# -------------------------- Product Price Drop Alerts & Threshold Notification ViewSet --------------------------
class PriceAlertViewSet(viewsets.ModelViewSet):
    """User can set up to 5 alerts (Free) or Unlimited (Paid)"""
    permission_classes = [IsAuthenticated]
    serializer_class = PriceAlertSerializer

    def get_queryset(self):
        return PriceAlert.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        user = request.user
        sub = getattr(user, 'subscription', None)

        # ১. সাবস্ক্রিপশন লিমিট চেক (ডক অনুযায়ী)
        alert_count = PriceAlert.objects.filter(
            user=user, is_active=True).count()
        limit = sub.plan.price_alerts_limit if sub and sub.is_active else 5

        if limit != -1 and alert_count >= limit:
            return Response({
                "success": False,
                "message": f"Alert limit reached. You can only set {limit} alerts."
            }, status=400)

        return super().create(request, *args, **kwargs)

