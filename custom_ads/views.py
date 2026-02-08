from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, NotFound
from django.db.models import F
from django.db import IntegrityError, transaction
from .models import AdReview, AdvertiserRequest, CustomAd
from .serializers import (
    AdvertiserRequestSerializer, 
    AdSerializer, 
    AdPublicSerializer
)
from .utils import get_weighted_ads
from account.models import User
from django.db.models import Sum
from rest_framework.decorators import action
from .permissions import IsAdminUser
import time


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
                    "data": {}
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
                    "data": {}
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


# ২. Create Ad (Only for approved advertisers)
class CreateAdView(generics.CreateAPIView):
    """
    Approved advertisers can create ads
    POST: /api/ads/create/
    """
    serializer_class = AdSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # Check if user is approved advertiser
        if not request.user.ads_provided:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_403_FORBIDDEN,
                    "message": "You must be an approved advertiser to create ads. Please apply first.",
                    "timestamp": int(time.time()),
                    "data": {}
                },
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Validate serializer
        serializer = self.get_serializer(data=request.data)
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
        
        # Create ad
        try:
            serializer.save(advertiser=request.user)
            return Response(
                {
                    "success": True,
                    "code": status.HTTP_201_CREATED,
                    "message": "Ad created successfully and submitted for review.",
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
                    "message": "Database error occurred.",
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
                    "message": "Failed to create ad.",
                    "timestamp": int(time.time()),
                    "data": {"detail": [str(e)]}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ৩. Public Ad List (Weighted Algorithm)
class AdListView(generics.ListAPIView):
    """
    Get weighted ads for display
    GET: /api/ads/list/?count=5
    """
    serializer_class = AdPublicSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        count = int(self.request.query_params.get('count', 3))
        count = min(count, 10)  # Max 10 ads
        return get_weighted_ads(count=count)

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
                        "count": len(serializer.data)
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


# ৪. Ad Click Tracker
class AdClickTrackerView(APIView):
    """
    Track ad clicks and update budget
    POST: /api/ads/click/<ad_id>/
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, ad_id):
        try:
            ad = CustomAd.objects.select_for_update().get(id=ad_id)
            
            # Update click count and spent amount
            ad.clicks = F('clicks') + 1
            ad.spent_amount = F('spent_amount') + 0.50  # $0.50 per click
            ad.save()
            
            # Refresh to get actual values
            ad.refresh_from_db()
            
            # Check if budget exceeded
            if ad.spent_amount >= ad.total_budget:
                ad.status = 'expired'
                ad.save()
                return Response(
                    {
                        "success": True,
                        "code": status.HTTP_200_OK,
                        "message": "Ad budget exhausted. Status set to expired.",
                        "timestamp": int(time.time()),
                        "data": {
                            "clicks": ad.clicks,
                            "spent": float(ad.spent_amount),
                            "total_budget": float(ad.total_budget),
                            "status": ad.status
                        }
                    },
                    status=status.HTTP_200_OK
                )
            
            return Response(
                {
                    "success": True,
                    "code": status.HTTP_200_OK,
                    "message": "Click tracked successfully.",
                    "timestamp": int(time.time()),
                    "data": {
                        "clicks": ad.clicks,
                        "spent": float(ad.spent_amount),
                        "remaining": float(ad.total_budget - ad.spent_amount)
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
                    "data": {}
                },
                status=status.HTTP_404_NOT_FOUND
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


# ৫. Advertiser Dashboard (Own Ads)
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


# ৬. Ad Detail View
class AdDetailView(generics.RetrieveAPIView):
    """
    Get single ad details
    GET: /api/ads/detail/<id>/
    """
    queryset = CustomAd.objects.filter(is_approved=True, status='active')
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
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Failed to retrieve ad details.",
                    "timestamp": int(time.time()),
                    "data": {"detail": [str(e)]}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ৭. Update Ad (Only advertiser's own ad)
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
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            
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


# ৮. Delete Ad (Only advertiser's own ad)
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
            self.perform_destroy(instance)
            return Response(
                {
                    "success": True,
                    "code": status.HTTP_200_OK,
                    "message": "Ad deleted successfully.",
                    "timestamp": int(time.time()),
                    "data": {}
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
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Failed to delete ad.",
                    "timestamp": int(time.time()),
                    "data": {"detail": [str(e)]}
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ৯. Advertiser Request Status Check
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
                req = AdvertiserRequest.objects.get(user=user)
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
                            {'width': 85, 'height': 16, 'label': '85 × 16 (Small Banner)'},
                            {'width': 120, 'height': 60, 'label': '120 × 60 (Large Banner)'},
                            {'width': 300, 'height': 250, 'label': '300 × 250 (Medium Rectangle)'},
                            {'width': 728, 'height': 90, 'label': '728 × 90 (Leaderboard)'},
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


# ==================== ADMIN - ADVERTISER REQUEST MANAGEMENT ====================

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
            queryset = queryset.filter(is_reviewed=True, user__ads_provided=True)
        elif status_filter == 'rejected':
            queryset = queryset.filter(is_reviewed=True, user__ads_provided=False)
        
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
                        "data": {}
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Approve the advertiser
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
                    "data": {}
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
                        "data": {}
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            reason = request.data.get('reason', 'No reason provided')
            
            if not reason or reason == 'No reason provided':
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
            
            # Reject the advertiser
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


# ==================== ADMIN - AD MANAGEMENT ====================

class AdminAdListView(generics.ListAPIView):
    """
    Admin can view all ads
    GET: /api/ads/admin/ads/?status=pending|approved|rejected
    """
    serializer_class = AdSerializer
    permission_classes = [IsAdminUser]
    
    def get_queryset(self):
        queryset = CustomAd.objects.all().select_related('advertiser').order_by('-created_at')
        
        status_filter = self.request.query_params.get('status')
        
        if status_filter == 'pending':
            queryset = queryset.filter(is_approved=False, status='active')
        elif status_filter == 'approved':
            queryset = queryset.filter(is_approved=True)
        elif status_filter == 'rejected':
            queryset = queryset.filter(is_approved=False, status='paused')
        
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
                        "data": {}
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Approve the ad
            ad.is_approved = True
            ad.status = 'active'
            ad.save()
            
            # Create review record
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
                    "data": {}
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
                        "data": {}
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            reason = request.data.get('reason', 'No reason provided')
            feedback = request.data.get('feedback', '')
            
            if not reason or reason == 'No reason provided':
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
            
            # Reject the ad
            ad.is_approved = False
            ad.status = 'paused'
            ad.save()
            
            # Create review record
            AdReview.objects.create(
                ad=ad,
                reviewer=request.user,
                status='rejected',
                feedback=f"{reason}. {feedback}"
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
                    "data": {}
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
                ad.status = 'paused'
                message = f"Ad '{ad.title}' has been paused."
            elif action == 'unpause':
                ad.status = 'active'
                message = f"Ad '{ad.title}' is now active."
            else:
                return Response(
                    {
                        "success": False,
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "Invalid action. Use 'pause' or 'unpause'.",
                        "timestamp": int(time.time()),
                        "data": {}
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
                    "data": {}
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


class AdminDashboardStatsView(APIView):
    """
    Admin dashboard statistics
    GET: /api/ads/admin/stats/
    """
    permission_classes = [IsAdminUser]
    
    def get(self, request):
        try:
            # Advertiser stats
            total_advertisers = User.objects.filter(ads_provided=True).count()
            pending_requests = AdvertiserRequest.objects.filter(is_reviewed=False).count()
            
            # Ad stats
            total_ads = CustomAd.objects.count()
            pending_ads = CustomAd.objects.filter(is_approved=False, status='active').count()
            active_ads = CustomAd.objects.filter(is_approved=True, status='active').count()
            
            # Revenue stats
            total_revenue = CustomAd.objects.aggregate(total=Sum('spent_amount'))['total'] or 0
            
            # Recent activities
            recent_requests = AdvertiserRequest.objects.filter(
                is_reviewed=False
            ).order_by('-applied_at')[:5]
            
            recent_ads = CustomAd.objects.filter(
                is_approved=False
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


# ==================== BULK ACTIONS ====================

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
            
            ads = CustomAd.objects.filter(id__in=ad_ids, is_approved=False)
            count = ads.update(is_approved=True, status='active')
            
            # Create review records
            for ad in ads:
                AdReview.objects.create(
                    ad=ad,
                    reviewer=request.user,
                    status='approved',
                    feedback='Bulk approved by admin'
                )
            
            return Response(
                {
                    "success": True,
                    "code": status.HTTP_200_OK,
                    "message": f"{count} ads approved successfully.",
                    "timestamp": int(time.time()),
                    "data": {
                        "approved_count": count,
                        "approved_ids": list(ads.values_list('id', flat=True))
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
            reason = request.data.get('reason', 'Rejected by admin')
            
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
            
            if not reason or reason == 'Rejected by admin':
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
            
            ads = CustomAd.objects.filter(id__in=ad_ids)
            count = ads.update(is_approved=False, status='paused')
            
            # Create review records
            for ad in ads:
                AdReview.objects.create(
                    ad=ad,
                    reviewer=request.user,
                    status='rejected',
                    feedback=reason
                )
            
            return Response(
                {
                    "success": True,
                    "code": status.HTTP_200_OK,
                    "message": f"{count} ads rejected successfully.",
                    "timestamp": int(time.time()),
                    "data": {
                        "rejected_count": count,
                        "rejected_ids": list(ads.values_list('id', flat=True)),
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