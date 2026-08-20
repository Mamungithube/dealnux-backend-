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


# -------------------------- Category ReadOnly ViewSet (Category List & Tree Detail) --------------------------
class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    lookup_field = 'slug'

    @action(detail=False, methods=['get'], url_path='tree')
    def tree(self, request):
        parents = Category.objects.filter(
            parent=None).prefetch_related('children')
        serializer = CategoryTreeSerializer(parents, many=True)
        return Response({
            "success": True,
            "code": 200,
            "message": "Category tree retrieved successfully.",
            "data": serializer.data
        })


# -------------------------- Category Hierarchical Tree Structure API View --------------------------
class CategoryTreeView(APIView):
    permission_classes = [drf_permissions.AllowAny]

    def get(self, request):
        parents = Category.objects.filter(
            parent=None).prefetch_related('children')
        serializer = CategoryTreeSerializer(parents, many=True)
        return Response({
            "success": True,
            "code": 200,
            "message": "Category tree retrieved successfully.",
            "data": serializer.data
        })


# -------------------------- Top-Level Parent Categories List API View --------------------------
class CategoryParentListView(APIView):
    """Only parent categories"""

    def get(self, request):
        parents = Category.objects.filter(
            parent=None).only('id', 'name', 'slug')
        serializer = CategoryChildSerializer(parents, many=True)
        return Response({
            "success": True,
            "code": 200,
            "message": "Parent categories retrieved.",
            "data": serializer.data
        })


# -------------------------- Subcategories / Child Categories of Parent Category View --------------------------
class CategoryChildrenView(APIView):
    """Children of a parent"""

    def get(self, request, slug):
        try:
            parent = Category.objects.get(slug=slug, parent=None)
        except Category.DoesNotExist:
            return Response({
                "success": False,
                "code": 404,
                "message": "Category not found.",
                "data": {}
            }, status=404)

        children = parent.children.all().only('id', 'name', 'slug')
        serializer = CategoryChildSerializer(children, many=True)
        return Response({
            "success": True,
            "code": 200,
            "message": f"Children of '{parent.name}' retrieved.",
            "data": {
                "parent": {"id": parent.id, "name": parent.name, "slug": parent.slug},
                "children": serializer.data
            }
        })
