from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, NotFound
from django.db.models import F
from django.db import IntegrityError, transaction
from .models import AdDailyPerformance, AdReview, AdvertiserRequest, CustomAd, AdSetting
from .serializers import (
    AdvertiserRequestSerializer,
    AdSerializer,
    AdPublicSerializer
)
import math
from .utils import get_weighted_ads
from account.models import User
from django.db.models import Sum
from rest_framework.decorators import action
from .permissions import IsAdminUser
import time
from django.http import Http404
from django.utils import timezone
from django.core.cache import cache


# ১. Advertiser Request Apply
class ApplyForAdvertiserView(generics.CreateAPIView):
    """
    User can apply to become an advertiser
    POST: /api/ads/apply/
    """
    serializer_class = AdvertiserRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # Check if already approved advertiser
        if request.user.ads_provided:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "You are already an approved advertiser.",
                    "timestamp": int(time.time()),
                    "data": {
                        "detail": "You are already an approved advertiser."
                    }
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check pending request
        if AdvertiserRequest.objects.filter(user=request.user, is_reviewed=False).exists():
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "Your previous request is still under review.",
                    "timestamp": int(time.time()),
                    "data": {
                        "detail": "Your previous request is still under review."
                    }
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate serializer
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "Invalid input data.",
                    "timestamp": int(time.time()),
                    "data": serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create advertiser request
        try:
            self.perform_create(serializer)
            return Response(
                {
                    "success": True,
                    "code": status.HTTP_201_CREATED,
                    "message": "Advertiser request submitted successfully.",
                    "timestamp": int(time.time()),
                    "data": serializer.data
                },
                status=status.HTTP_201_CREATED
            )
        except IntegrityError as e:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "An error occurred while processing your request.",
                    "timestamp": int(time.time()),
                    "data": {"detail": [str(e)]}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Something went wrong on the server.",
                    "timestamp": int(time.time()),
                    "data": {"detail": [str(e)]}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


"""----------------------Create Ad (Only for approved advertisers)-----------------------"""


class CreateAdView(generics.CreateAPIView):
    serializer_class = AdSerializer
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        if not request.user.ads_provided:
            return Response({"error": "Not an approved advertiser"}, status=403)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # ১. বিজ্ঞাপনটি 'pending' হিসেবে সেভ করা (পেমেন্ট না হওয়া পর্যন্ত এটি লাইভ হবে না)
        ad = serializer.save(advertiser=request.user, is_approved=False, status='pending')
        
        # ২. পেমেন্ট রেকর্ড তৈরি করা
        payment = Payment.objects.create(
            buyer=request.user,
            ad=ad,
            payment_type='AD',
            unit_price=ad.total_budget,
            total_amount=ad.total_budget,
            final_amount=ad.total_budget,
            currency='usd', # বা আপনার কারেন্সি
            status='PENDING'
        )

        # ৩. Stripe Checkout Session তৈরি করা
        try:
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'usd',
                        'unit_amount': int(ad.total_budget * 100), # Cents এ রূপান্তর
                        'product_data': {
                            'name': f"Ad Campaign: {ad.title}",
                            'description': f"Budget for {ad.target_section} section",
                        },
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url=settings.STRIPE_SUCCESS_URL + "?session_id={CHECKOUT_SESSION_ID}",
                cancel_url=settings.STRIPE_CANCEL_URL,
                metadata={
                    'payment_id': payment.id,
                    'ad_id': ad.id,
                    'type': 'ad_payment'
                }
            )

            payment.stripe_checkout_session_id = session.id
            payment.stripe_checkout_url = session.url
            payment.save()

            return Response({
                "message": "Ad submitted. Please complete payment to proceed to admin review.",
                "checkout_url": session.url,
                "ad_id": ad.id
            }, status=201)

        except Exception as e:
            transaction.set_rollback(True)
            return Response({"error": str(e)}, status=500)


"""--------------------Public Ad List (Weighted Algorithm)-----------------------"""


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
            cache.delete('active_ads_pool')  # ✅ এই লাইনটা যোগ করো

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


"""--------------------Ad Click Tracker-----------------------"""


import time
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import CustomAd, AdSetting, AdDailyPerformance

class AdClickTrackerView(APIView):
    """
    Track ad clicks and update budget with dynamic CPC
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, ad_id):
        try:
            with transaction.atomic():
                # ১. ডাটাবেজ থেকে অ্যাডটি লক করে রিট্রিভ করা
                try:
                    ad = CustomAd.objects.select_for_update().get(id=ad_id)
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

                # ২. বর্তমান CPC রেট সংগ্রহ করা
                setting = AdSetting.objects.first()
                cpc = setting.cpc_amount if setting else 0.50

                # ৩. প্রাথমিক চেক: বাজেট আগেই শেষ হয়ে গেছে কিনা
                if ad.status == 'expired' or ad.spent_amount >= ad.total_budget:
                    # যদি বাজেট আগেই শেষ থাকে তবে স্ট্যাটাস নিশ্চিত করে রিটার্ন করা
                    if ad.status != 'expired':
                        ad.status = 'expired'
                        ad.save()
                    
                    return Response(
                        {
                            "success": False,
                            "code": status.HTTP_400_BAD_REQUEST,
                            "message": "Ad budget already exhausted.",
                            "timestamp": int(time.time()),
                            "data": {}
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # ৪. ক্লিিক এবং খরচ আপডেট করা (F expression ব্যবহার করে)
                ad.clicks = F('clicks') + 1
                ad.spent_amount = F('spent_amount') + cpc
                ad.save()

                # ৫. গুরুত্বপূর্ণ: ডাটাবেজ থেকে আপডেট হওয়া মানগুলো রিফ্রেশ করা
                # এটি না করলে 'spent_amount' একটি 'CombinedExpression' হয়ে থাকবে এবং এরর দিবে
                ad.refresh_from_db()

                # ৬. ডেইলি স্ট্যাটিস্টিকস আপডেট করা
                today = timezone.now().date()
                daily_stat, _ = AdDailyPerformance.objects.get_or_create(
                    ad=ad,
                    date=today,
                    defaults={'impressions': 0, 'clicks': 0}
                )
                AdDailyPerformance.objects.filter(id=daily_stat.id).update(
                    clicks=F('clicks') + 1
                )

                # ৭. নতুন ক্লিকের পর বাজেট চেক করা
                remaining = float(ad.total_budget - ad.spent_amount)
                
                if remaining <= 0:
                    ad.status = 'expired'
                    ad.save()
                    remaining = 0

                return Response(
                    {
                        "success": True,
                        "code": status.HTTP_200_OK,
                        "message": "Click tracked successfully.",
                        "timestamp": int(time.time()),
                        "data": {
                            "clicks": ad.clicks,
                            "spent_now": float(cpc),
                            "total_spent": float(ad.spent_amount),
                            "remaining": remaining,
                            "status": ad.status
                        }
                    },
                    status=status.HTTP_200_OK
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

"""----------------------Advertiser Dashboard (Own Ads)-----------------------"""


class AdvertiserAdDashboardView(generics.ListAPIView):
    """
    Advertiser can view their own ads
    GET: /api/ads/dashboard/
    """
    serializer_class = AdSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not self.request.user.ads_provided:
            raise PermissionDenied("You are not an advertiser")
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


"""--------------------Ad Details (Public)-----------------------"""


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


"""--------------------Update Ad (Only advertiser's own ad)-----------------------"""


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


"""--------------------Delete Ad (Only advertiser's own ad)-----------------------"""


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


"""--------------------Advertiser Request Status Check-----------------------"""


class CheckAdvertiserStatusView(APIView):
    """
    Check advertiser application status
    GET: /api/ads/status/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            user = request.user

            if user.ads_provided:
                return Response(
                    {
                        "success": True,
                        "code": status.HTTP_200_OK,
                        "message": "You are an approved advertiser.",
                        "timestamp": int(time.time()),
                        "data": {
                            "status": "approved"
                        }
                    },
                    status=status.HTTP_200_OK
                )

            try:
                req = AdvertiserRequest.objects.filter(
                    user=user).latest('applied_at')
                return Response(
                    {
                        "success": True,
                        "code": status.HTTP_200_OK,
                        "message": "Advertiser request status retrieved.",
                        "timestamp": int(time.time()),
                        "data": {
                            "status": "pending" if not req.is_reviewed else "rejected",
                            "applied_at": req.applied_at,
                            "rejection_reason": req.rejection_reason
                        }
                    },
                    status=status.HTTP_200_OK
                )
            except AdvertiserRequest.DoesNotExist:
                return Response(
                    {
                        "success": True,
                        "code": status.HTTP_200_OK,
                        "message": "You haven't applied yet.",
                        "timestamp": int(time.time()),
                        "data": {
                            "status": "not_applied"
                        }
                    },
                    status=status.HTTP_200_OK
                )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Failed to retrieve status.",
                    "timestamp": int(time.time()),
                    "data": {"detail": [str(e)]}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


"""--------------------Ad Configuration Options-----------------------"""


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


"""==================== ADMIN - ADVERTISER REQUEST MANAGEMENT ===================="""


class AdminAdvertiserRequestListView(generics.ListAPIView):
    """
    Admin can view all advertiser requests
    GET: /api/ads/admin/requests/?status=pending|approved|rejected
    """
    serializer_class = AdvertiserRequestSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        queryset = AdvertiserRequest.objects.all().order_by('-applied_at')

        status_filter = self.request.query_params.get('status')

        if status_filter == 'pending':
            queryset = queryset.filter(is_reviewed=False)
        elif status_filter == 'approved':
            queryset = queryset.filter(
                is_reviewed=True, user__ads_provided=True)
        elif status_filter == 'rejected':
            queryset = queryset.filter(
                is_reviewed=True, user__ads_provided=False)

        return queryset

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return Response(
                {
                    "success": True,
                    "code": status.HTTP_200_OK,
                    "message": "Advertiser requests retrieved successfully.",
                    "timestamp": int(time.time()),
                    "data": {
                        "requests": serializer.data,
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
                    "message": "Failed to retrieve requests.",
                    "timestamp": int(time.time()),
                    "data": {"detail": [str(e)]}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


"""--------------------Admin Approve Advertiser Request-----------------------"""


class AdminApproveAdvertiserView(APIView):
    """
    Admin approves advertiser request
    POST: /api/ads/admin/requests/<id>/approve/
    """
    permission_classes = [IsAdminUser]

    @transaction.atomic
    def post(self, request, pk):
        try:
            advertiser_request = AdvertiserRequest.objects.select_for_update().get(pk=pk)

            if advertiser_request.is_reviewed:
                return Response(
                    {
                        "success": False,
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "This request has already been reviewed.",
                        "timestamp": int(time.time()),
                        "data": {
                            "detail": "This request has already been reviewed."
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            advertiser_request.approve()

            return Response(
                {
                    "success": True,
                    "code": status.HTTP_200_OK,
                    "message": f"{advertiser_request.user.email} is now an approved advertiser.",
                    "timestamp": int(time.time()),
                    "data": AdvertiserRequestSerializer(advertiser_request).data
                },
                status=status.HTTP_200_OK
            )

        except AdvertiserRequest.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_404_NOT_FOUND,
                    "message": "Advertiser request not found.",
                    "timestamp": int(time.time()),
                    "data": {
                        "detail": "Advertiser request not found."
                    }
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Failed to approve advertiser request.",
                    "timestamp": int(time.time()),
                    "data": {"detail": [str(e)]}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


"""--------------------Admin Reject Advertiser Request-----------------------"""


class AdminRejectAdvertiserView(APIView):
    """
    Admin rejects advertiser request
    POST: /api/ads/admin/requests/<id>/reject/
    Body: {"reason": "Invalid business details"}
    """
    permission_classes = [IsAdminUser]

    @transaction.atomic
    def post(self, request, pk):
        try:
            advertiser_request = AdvertiserRequest.objects.select_for_update().get(pk=pk)

            if advertiser_request.is_reviewed:
                return Response(
                    {
                        "success": False,
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "This request has already been reviewed.",
                        "timestamp": int(time.time()),
                        "data": {
                            "detail": "This request has already been reviewed."
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            reason = request.data.get('reason', '')

            if not reason:
                return Response(
                    {
                        "success": False,
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "Rejection reason is required.",
                        "timestamp": int(time.time()),
                        "data": {"reason": ["This field is required."]}
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            advertiser_request.reject(reason=reason)

            return Response(
                {
                    "success": True,
                    "code": status.HTTP_200_OK,
                    "message": "Advertiser request rejected.",
                    "timestamp": int(time.time()),
                    "data": {
                        "reason": reason,
                        "request": AdvertiserRequestSerializer(advertiser_request).data
                    }
                },
                status=status.HTTP_200_OK
            )

        except AdvertiserRequest.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_404_NOT_FOUND,
                    "message": "Advertiser request not found.",
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
                    "message": "Failed to reject advertiser request.",
                    "timestamp": int(time.time()),
                    "data": {"detail": [str(e)]}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


"""==================== ADMIN - AD MANAGEMENT ===================="""


class AdminAdListView(generics.ListAPIView):
    """
    Admin can view all ads
    GET: /api/ads/admin/ads/?status=pending|approved|rejected
    """
    serializer_class = AdSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        queryset = CustomAd.objects.all().select_related(
            'advertiser').order_by('-created_at')
        status_filter = self.request.query_params.get('status')

        if status_filter == 'pending':
            queryset = queryset.filter(
                is_approved=False, status='pending')  # ✅ ঠিক করা
        elif status_filter == 'approved':
            queryset = queryset.filter(is_approved=True, status='active')
        elif status_filter == 'rejected':
            queryset = queryset.filter(status='rejected')  # ✅ ঠিক করা

        return queryset

    def list(self, request, *args, **kwargs):
        try:
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


"""--------------------Admin Approve Ad-----------------------"""


class AdminApproveAdView(APIView):
    """
    Admin approves an ad
    POST: /api/ads/admin/ads/<id>/approve/
    """
    permission_classes = [IsAdminUser]

    @transaction.atomic
    def post(self, request, pk):
        try:
            ad = CustomAd.objects.select_for_update().get(pk=pk)

            if ad.is_approved:
                return Response(
                    {
                        "success": False,
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "This ad is already approved.",
                        "timestamp": int(time.time()),
                        "data": {
                            "detail": "This ad is already approved."
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            ad.is_approved = True
            ad.status = 'active'
            ad.save()

            AdReview.objects.create(
                ad=ad,
                reviewer=request.user,
                status='approved',
                feedback='Ad approved by admin'
            )

            return Response(
                {
                    "success": True,
                    "code": status.HTTP_200_OK,
                    "message": f"Ad '{ad.title}' has been approved and is now active.",
                    "timestamp": int(time.time()),
                    "data": AdSerializer(ad).data
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
                    "data": {
                        "detail": "Ad not found."
                    }
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Failed to approve ad.",
                    "timestamp": int(time.time()),
                    "data": {"detail": [str(e)]}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


"""--------------------Admin Reject Ad-----------------------"""


class AdminRejectAdView(APIView):
    """
    Admin rejects an ad
    POST: /api/ads/admin/ads/<id>/reject/
    Body: {"reason": "Inappropriate content", "feedback": "Please revise the image"}
    """
    permission_classes = [IsAdminUser]

    @transaction.atomic
    def post(self, request, pk):
        try:
            ad = CustomAd.objects.select_for_update().get(pk=pk)

            if ad.is_approved:
                return Response(
                    {
                        "success": False,
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "Cannot reject an already approved ad. Pause it instead.",
                        "timestamp": int(time.time()),
                        "data": {
                            "detail": "Cannot reject an already approved ad. Pause it instead."
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            reason = request.data.get('reason', '')
            feedback = request.data.get('feedback', '')

            if not reason:
                return Response(
                    {
                        "success": False,
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "Rejection reason is required.",
                        "timestamp": int(time.time()),
                        "data": {"reason": ["This field is required."]}
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # ✅ 'paused' থেকে 'rejected' এ ঠিক করা
            ad.is_approved = False
            ad.status = 'rejected'
            ad.save()

            AdReview.objects.create(
                ad=ad,
                reviewer=request.user,
                status='rejected',
                feedback=f"{reason}. {feedback}".strip('. ')
            )

            return Response(
                {
                    "success": True,
                    "code": status.HTTP_200_OK,
                    "message": "Ad rejected successfully.",
                    "timestamp": int(time.time()),
                    "data": {
                        "reason": reason,
                        "feedback": feedback,
                        "ad": AdSerializer(ad).data
                    }
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
                    "data": {"detail": "The requested ad does not exist."}
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Failed to reject ad.",
                    "timestamp": int(time.time()),
                    "data": {"detail": [str(e)]}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


"""--------------------Admin Pause/Unpause Ad-----------------------"""


class AdminPauseAdView(APIView):
    """
    Admin can pause/unpause an approved ad
    POST: /api/ads/admin/ads/<id>/pause/
    POST: /api/ads/admin/ads/<id>/unpause/
    """
    permission_classes = [IsAdminUser]

    @transaction.atomic
    def post(self, request, pk, action):
        try:
            ad = CustomAd.objects.select_for_update().get(pk=pk)

            if action == 'pause':
                if not ad.is_approved:
                    return Response(
                        {
                            "success": False,
                            "code": status.HTTP_400_BAD_REQUEST,
                            "message": "Only approved ads can be paused.",
                            "timestamp": int(time.time()),
                            "data": {}
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
                ad.status = 'paused'
                message = f"Ad '{ad.title}' has been paused."

            elif action == 'unpause':
                if not ad.is_approved:
                    return Response(
                        {
                            "success": False,
                            "code": status.HTTP_400_BAD_REQUEST,
                            "message": "Only approved ads can be unpaused.",
                            "timestamp": int(time.time()),
                            "data": {}
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
                ad.status = 'active'
                message = f"Ad '{ad.title}' is now active."

            else:
                return Response(
                    {
                        "success": False,
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "Invalid action. Use 'pause' or 'unpause'.",
                        "timestamp": int(time.time()),
                        "data": {"detail": "Invalid action. Use 'pause' or 'unpause'."}
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            ad.save()

            return Response(
                {
                    "success": True,
                    "code": status.HTTP_200_OK,
                    "message": message,
                    "timestamp": int(time.time()),
                    "data": AdSerializer(ad).data
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
                    "data": {"detail": "The requested ad does not exist."}
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Failed to update ad status.",
                    "timestamp": int(time.time()),
                    "data": {"detail": [str(e)]}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


"""==================== ADMIN - DASHBOARD STATS ===================="""


class AdminDashboardStatsView(APIView):
    """
    Admin dashboard statistics
    GET: /api/ads/admin/stats/
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        try:
            total_advertisers = User.objects.filter(ads_provided=True).count()
            pending_requests = AdvertiserRequest.objects.filter(
                is_reviewed=False).count()

            total_ads = CustomAd.objects.count()
            pending_ads = CustomAd.objects.filter(
                is_approved=False, status='pending').count()  # ✅ ঠিক করা
            active_ads = CustomAd.objects.filter(
                is_approved=True, status='active').count()

            total_revenue = CustomAd.objects.aggregate(
                total=Sum('spent_amount'))['total'] or 0

            recent_requests = AdvertiserRequest.objects.filter(
                is_reviewed=False
            ).order_by('-applied_at')[:5]

            recent_ads = CustomAd.objects.filter(
                is_approved=False, status='pending'
            ).order_by('-created_at')[:5]

            return Response(
                {
                    "success": True,
                    "code": status.HTTP_200_OK,
                    "message": "Dashboard statistics retrieved successfully.",
                    "timestamp": int(time.time()),
                    "data": {
                        'advertisers': {
                            'total': total_advertisers,
                            'pending_requests': pending_requests
                        },
                        'ads': {
                            'total': total_ads,
                            'pending': pending_ads,
                            'active': active_ads
                        },
                        'revenue': {
                            'total': float(total_revenue),
                            'currency': 'USD'
                        },
                        'recent_activity': {
                            'pending_requests': AdvertiserRequestSerializer(recent_requests, many=True).data,
                            'pending_ads': AdSerializer(recent_ads, many=True).data
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
                    "message": "Failed to retrieve dashboard statistics.",
                    "timestamp": int(time.time()),
                    "data": {"detail": [str(e)]}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


"""==================== BULK ACTIONS ===================="""


class AdminBulkApproveAdsView(APIView):
    """
    Bulk approve multiple ads
    POST: /api/ads/admin/ads/bulk-approve/
    Body: {"ad_ids": [1, 2, 3, 4]}
    """
    permission_classes = [IsAdminUser]

    @transaction.atomic
    def post(self, request):
        try:
            ad_ids = request.data.get('ad_ids', [])

            if not ad_ids:
                return Response(
                    {
                        "success": False,
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "Please provide ad_ids array.",
                        "timestamp": int(time.time()),
                        "data": {"ad_ids": ["This field is required."]}
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not isinstance(ad_ids, list):
                return Response(
                    {
                        "success": False,
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "ad_ids must be an array.",
                        "timestamp": int(time.time()),
                        "data": {"ad_ids": ["Invalid format."]}
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # ✅ Save with list() first.
            ads = list(CustomAd.objects.filter(
                id__in=ad_ids, is_approved=False))

            if not ads:
                return Response(
                    {
                        "success": False,
                        "code": status.HTTP_404_NOT_FOUND,
                        "message": "No pending ads found with the given IDs.",
                        "timestamp": int(time.time()),
                        "data": {}
                    },
                    status=status.HTTP_404_NOT_FOUND
                )

            # ✅ Bulk update
            CustomAd.objects.filter(id__in=[ad.id for ad in ads]).update(
                is_approved=True, status='active'
            )

            # ✅ Insert all in one query with bulk_create
            AdReview.objects.bulk_create([
                AdReview(
                    ad=ad,
                    reviewer=request.user,
                    status='approved',
                    feedback='Bulk approved by admin'
                )
                for ad in ads
            ])

            return Response(
                {
                    "success": True,
                    "code": status.HTTP_200_OK,
                    "message": f"{len(ads)} ads approved successfully.",
                    "timestamp": int(time.time()),
                    "data": {
                        "approved_count": len(ads),
                        "approved_ids": [ad.id for ad in ads]
                    }
                },
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Failed to approve ads.",
                    "timestamp": int(time.time()),
                    "data": {"detail": [str(e)]}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


"""--------------------Bulk Reject Ads-----------------------"""


class AdminBulkRejectAdsView(APIView):
    """
    Bulk reject multiple ads
    POST: /api/ads/admin/ads/bulk-reject/
    Body: {"ad_ids": [1, 2, 3], "reason": "Policy violation"}
    """
    permission_classes = [IsAdminUser]

    @transaction.atomic
    def post(self, request):
        try:
            ad_ids = request.data.get('ad_ids', [])
            reason = request.data.get('reason', '')

            if not ad_ids:
                return Response(
                    {
                        "success": False,
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "Please provide ad_ids array.",
                        "timestamp": int(time.time()),
                        "data": {"ad_ids": ["This field is required."]}
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not isinstance(ad_ids, list):
                return Response(
                    {
                        "success": False,
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "ad_ids must be an array.",
                        "timestamp": int(time.time()),
                        "data": {"ad_ids": ["Invalid format."]}
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not reason:
                return Response(
                    {
                        "success": False,
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "Rejection reason is required.",
                        "timestamp": int(time.time()),
                        "data": {"reason": ["This field is required."]}
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # ✅ Save with list() first.
            ads = list(CustomAd.objects.filter(id__in=ad_ids))

            if not ads:
                return Response(
                    {
                        "success": False,
                        "code": status.HTTP_404_NOT_FOUND,
                        "message": "No ads found with the given IDs.",
                        "timestamp": int(time.time()),
                        "data": {}
                    },
                    status=status.HTTP_404_NOT_FOUND
                )

            # ✅ Bulk update, status='rejected' fix
            CustomAd.objects.filter(id__in=[ad.id for ad in ads]).update(
                is_approved=False, status='rejected'
            )

            # ✅ Insert all in one query with bulk_create
            AdReview.objects.bulk_create([
                AdReview(
                    ad=ad,
                    reviewer=request.user,
                    status='rejected',
                    feedback=reason
                )
                for ad in ads
            ])

            return Response(
                {
                    "success": True,
                    "code": status.HTTP_200_OK,
                    "message": f"{len(ads)} ads rejected successfully.",
                    "timestamp": int(time.time()),
                    "data": {
                        "rejected_count": len(ads),
                        "rejected_ids": [ad.id for ad in ads],
                        "reason": reason
                    }
                },
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Failed to reject ads.",
                    "timestamp": int(time.time()),
                    "data": {"detail": [str(e)]}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
