import math
import time
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
import stripe

from ..models import CustomAd
from ..serializers import AdPublicSerializer, AdSerializer
from ..services import record_ad_click
from ..utils import get_weighted_ads
from payment.models import Payment

stripe.api_key = settings.STRIPE_SECRET_KEY


class CreateAdView(generics.CreateAPIView):
    serializer_class = AdSerializer
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        if not request.user.ads_provided:
            return Response({"error": "Not an approved advertiser"}, status=403)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ad = serializer.save(advertiser=request.user,
                             is_approved=False, status='pending')

        payment = Payment.objects.create(
            buyer=request.user,
            ad=ad,
            payment_type='AD',
            unit_price=ad.total_budget,
            total_amount=ad.total_budget,
            final_amount=ad.total_budget,
            currency='usd',
            status='PENDING'
        )

        try:
            session = stripe.checkout.Session.create(
                ui_mode='embedded',
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'usd',
                        'unit_amount': int(ad.total_budget * 100),
                        'product_data': {
                            'name': f"Ad Campaign: {ad.title}",
                        },
                    },
                    'quantity': 1,
                }],
                mode='payment',
                return_url=settings.STRIPE_RETURN_URL +
                "?session_id={CHECKOUT_SESSION_ID}",
                metadata={
                    'payment_id': payment.id,
                    'ad_id': ad.id,
                    'type': 'ad_payment'
                }
            )

            mobile_intent = stripe.PaymentIntent.create(
                amount=int(ad.total_budget * 100),
                currency='usd',
                automatic_payment_methods={"enabled": True},
                metadata={'payment_id': payment.id,
                          'ad_id': ad.id, 'type': 'ad_payment'}
            )

            payment.stripe_checkout_session_id = session.id
            payment.stripe_payment_intent_id = mobile_intent.id
            payment.save()

            return Response({
                "message": "Embedded Checkout Session Created.",  # web
                "payment_intent_client_secret": mobile_intent.client_secret,  # app
                "client_secret": session.client_secret,
                "session_id": session.id,
                "payment_id": payment.id
            }, status=201)

        except stripe.error.StripeError as e:
            return Response({'error': str(e)}, status=500)


class AdListView(generics.ListAPIView):
    """
    Get weighted ads for display
    GET: /api/ads/list/?count=5
    """
    serializer_class = AdPublicSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        expired_count = CustomAd.objects.filter(
            status='active',
            end_date__lt=timezone.now()
        ).update(status='expired')

        if expired_count > 0:
            cache.delete('active_ads_pool')

        count = int(self.request.query_params.get('count', 3))
        count = min(count, 10)
        return get_weighted_ads(count=count)

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()

            try:
                page = max(1, int(request.query_params.get('page', 1)))
                page_size = min(
                    max(1, int(request.query_params.get('page_size', 10))), 50)
            except (ValueError, TypeError):
                page, page_size = 1, 10

            serializer = self.get_serializer(queryset, many=True)
            all_results = serializer.data
            total_count = len(all_results)
            total_pages = math.ceil(total_count / page_size)

            start = (page - 1) * page_size
            end = start + page_size
            results = all_results[start:end]

            return Response({
                "success":   True,
                "code":      status.HTTP_200_OK,
                "message":   "Ads retrieved successfully.",
                "timestamp": int(time.time()),
                "data": results,
                "pagination": {
                    "total_count":  total_count,
                    "total_pages":  total_pages,
                    "current_page": page,
                    "page_size":    page_size,
                    "has_next":     page < total_pages,
                    "has_previous": page > 1,
                    "next_page":    page + 1 if page < total_pages else None,
                    "prev_page":    page - 1 if page > 1 else None,
                },
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                "success":   False,
                "code":      status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message":   "Failed to retrieve ads.",
                "timestamp": int(time.time()),
                "data":      {"detail": [str(e)]},
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdClickTrackerView(APIView):
    """
    Track ad clicks and update budget with dynamic CPC
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, ad_id):
        try:
            data = record_ad_click(ad_id)
            return Response(
                {
                    "success": True,
                    "code": status.HTTP_200_OK,
                    "message": "Click tracked successfully.",
                    "timestamp": int(time.time()),
                    "data": data
                },
                status=status.HTTP_200_OK
            )
        except CustomAd.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_404_NOT_FOUND,
                    "message": "Ad not found.",
                    "timestamp": int(time.time()),
                    "data": {}
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except ValueError as ve:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": str(ve),
                    "timestamp": int(time.time()),
                    "data": {}
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Failed to track click.",
                    "timestamp": int(time.time()),
                    "data": {"detail": [str(e)]}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdvertiserAdDashboardView(generics.ListAPIView):
    """
    Advertiser can view their own ads
    GET: /api/ads/dashboard/
    """
    serializer_class = AdSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not self.request.user.ads_provided:
            raise permissions.exceptions.PermissionDenied("You are not an advertiser")
        return CustomAd.objects.filter(advertiser=self.request.user)

    def list(self, request, *args, **kwargs):
        try:
            if not request.user.ads_provided:
                return Response(
                    {
                        "success": False,
                        "code": status.HTTP_403_FORBIDDEN,
                        "message": "You are not an advertiser.",
                        "timestamp": int(time.time()),
                        "data": {}
                    },
                    status=status.HTTP_403_FORBIDDEN
                )

            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return Response(
                {
                    "success": True,
                    "code": status.HTTP_200_OK,
                    "message": "Ads retrieved successfully.",
                    "timestamp": int(time.time()),
                    "data": {
                        "ads": serializer.data,
                        "total": queryset.count()
                    }
                },
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Failed to retrieve ads.",
                    "timestamp": int(time.time()),
                    "data": {"detail": [str(e)]}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdDetailView(generics.RetrieveAPIView):
    queryset = CustomAd.objects.all()
    serializer_class = AdPublicSerializer
    permission_classes = [permissions.AllowAny]

    def retrieve(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return Response(
                {
                    "success": True,
                    "code": status.HTTP_200_OK,
                    "message": "Ad details retrieved successfully.",
                    "timestamp": int(time.time()),
                    "data": serializer.data
                },
                status=status.HTTP_200_OK
            )
        except Http404:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_404_NOT_FOUND,
                    "message": "Ad not found or is not active.",
                    "timestamp": int(time.time()),
                    "data": {"detail": "No CustomAd matches the given query."}
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "An unexpected error occurred.",
                    "timestamp": int(time.time()),
                    "data": {"detail": str(e)}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class UpdateAdView(generics.UpdateAPIView):
    """
    Update own ad
    PUT/PATCH: /api/ads/update/<id>/
    """
    serializer_class = AdSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return CustomAd.objects.filter(advertiser=self.request.user)

    def update(self, request, *args, **kwargs):
        try:
            partial = kwargs.pop('partial', False)
            instance = self.get_object()
            serializer = self.get_serializer(
                instance, data=request.data, partial=partial)

            if not serializer.is_valid():
                return Response(
                    {
                        "success": False,
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "Invalid ad data.",
                        "timestamp": int(time.time()),
                        "data": serializer.errors
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            self.perform_update(serializer)
            return Response(
                {
                    "success": True,
                    "code": status.HTTP_200_OK,
                    "message": "Ad updated successfully.",
                    "timestamp": int(time.time()),
                    "data": serializer.data
                },
                status=status.HTTP_200_OK
            )
        except CustomAd.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_404_NOT_FOUND,
                    "message": "Ad not found or you don't have permission to update it.",
                    "timestamp": int(time.time()),
                    "data": {}
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Failed to update ad.",
                    "timestamp": int(time.time()),
                    "data": {"detail": [str(e)]}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DeleteAdView(generics.DestroyAPIView):
    """
    Delete own ad
    DELETE: /api/ads/delete/<id>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return CustomAd.objects.filter(advertiser=self.request.user)

    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            ad_id = instance.id
            ad_title = instance.title

            self.perform_destroy(instance)
            return Response(
                {
                    "success": True,
                    "code": status.HTTP_200_OK,
                    "message": "Ad deleted successfully.",
                    "timestamp": int(time.time()),
                    "data": {
                        "id": ad_id,
                        "title": ad_title
                    }
                },
                status=status.HTTP_200_OK
            )
        except CustomAd.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_404_NOT_FOUND,
                    "message": "Ad not found or you don't have permission to delete it.",
                    "timestamp": int(time.time()),
                    "data": {}
                },
                status=status.HTTP_404_NOT_FOUND
            )


class AdConfigView(APIView):
    """
    Configuration options for ad creation form
    GET: /api/ads/config/
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        try:
            return Response(
                {
                    "success": True,
                    "code": status.HTTP_200_OK,
                    "message": "Ad configuration retrieved successfully.",
                    "timestamp": int(time.time()),
                    "data": {
                        'target_sections': [
                            {'value': key, 'label': label}
                            for key, label in CustomAd.TARGET_SECTION_CHOICES
                        ],
                        'ad_sizes': [
                            {'width': 85, 'height': 16,
                                'label': '85 × 16 (Small Banner)'},
                            {'width': 120, 'height': 60,
                                'label': '120 × 60 (Large Banner)'},
                            {'width': 300, 'height': 250,
                                'label': '300 × 250 (Medium Rectangle)'},
                            {'width': 728, 'height': 90,
                                'label': '728 × 90 (Leaderboard)'},
                        ],
                        'budget_info': {
                            'min_budget': 10.00,
                            'cost_per_click': 0.50,
                            'currency': 'USD'
                        }
                    }
                },
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Failed to retrieve configuration.",
                    "timestamp": int(time.time()),
                    "data": {"detail": [str(e)]}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
