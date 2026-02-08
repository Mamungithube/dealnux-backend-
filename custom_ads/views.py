from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, NotFound
from django.db.models import F
from django.db import IntegrityError
from .models import AdReview, AdvertiserRequest, CustomAd
from .serializers import (
    AdvertiserRequestSerializer, 
    AdSerializer, 
    AdPublicSerializer
)
from .utils import get_weighted_ads
from account.models import User
from django.db.models import Sum

# ১. Advertiser Request Apply
class ApplyForAdvertiserView(generics.CreateAPIView):
    """
    User can apply to become an advertiser
    POST: /api/ads/apply/
    """
    serializer_class = AdvertiserRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        if request.user.ads_provided:
            return Response(
                {"detail": "You are already an approved advertiser."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check pending request
        if AdvertiserRequest.objects.filter(
            user=request.user, 
            is_reviewed=False
        ).exists():
            return Response(
                {"detail": "Your previous request is still under review."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            return super().post(request, *args, **kwargs)
        except IntegrityError:
            return Response(
                {"detail": "An error occurred. Please try again."}, 
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

    def perform_create(self, serializer):
        if not self.request.user.ads_provided:
            raise PermissionDenied(
                "You must be an approved advertiser to create ads. "
                "Please apply first."
            )
        
        try:
            serializer.save(advertiser=self.request.user)
        except IntegrityError as e:
            raise PermissionDenied(f"Database error: {str(e)}")


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
                return Response({
                    "status": "success",
                    "message": "Ad budget exhausted. Status set to expired."
                }, status=status.HTTP_200_OK)
            
            return Response({
                "status": "success",
                "clicks": ad.clicks,
                "spent": float(ad.spent_amount),
                "remaining": float(ad.total_budget - ad.spent_amount)
            }, status=status.HTTP_200_OK)
            
        except CustomAd.DoesNotExist:
            raise NotFound("Ad not found")
        except Exception as e:
            return Response(
                {"error": str(e)}, 
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


# ৬. Ad Detail View
class AdDetailView(generics.RetrieveAPIView):
    """
    Get single ad details
    GET: /api/ads/detail/<id>/
    """
    queryset = CustomAd.objects.filter(
        is_approved=True, 
        status='active'
    )
    serializer_class = AdPublicSerializer
    permission_classes = [permissions.AllowAny]


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


# ৮. Delete Ad (Only advertiser's own ad)
class DeleteAdView(generics.DestroyAPIView):
    """
    Delete own ad
    DELETE: /api/ads/delete/<id>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return CustomAd.objects.filter(advertiser=self.request.user)


# ৯. Advertiser Request Status Check
class CheckAdvertiserStatusView(APIView):
    """
    Check advertiser application status
    GET: /api/ads/status/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        
        if user.ads_provided:
            return Response({
                "status": "approved",
                "message": "You are an approved advertiser"
            })
        
        try:
            req = AdvertiserRequest.objects.get(user=user)
            return Response({
                "status": "pending" if not req.is_reviewed else "rejected",
                "applied_at": req.applied_at,
                "rejection_reason": req.rejection_reason
            })
        except AdvertiserRequest.DoesNotExist:
            return Response({
                "status": "not_applied",
                "message": "You haven't applied yet"
            })
        

class AdConfigView(APIView):
    """
    Configuration options for ad creation form
    GET: /api/ads/config/
    """
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        return Response({
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
        })
    


# views.py এর শেষে যোগ করুন

from rest_framework.decorators import action
from .permissions import IsAdminUser
from django.db import transaction


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
                    {"error": "This request has already been reviewed."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Approve the advertiser
            advertiser_request.approve()
            
            # Optional: Send email notification
            # send_mail(
            #     subject='Your Advertiser Request has been Approved!',
            #     message=f'Congratulations! You can now create ads.',
            #     from_email='noreply@yoursite.com',
            #     recipient_list=[advertiser_request.user.email],
            # )
            
            return Response({
                "success": True,
                "message": f"{advertiser_request.user.email} is now an approved advertiser.",
                "data": AdvertiserRequestSerializer(advertiser_request).data
            }, status=status.HTTP_200_OK)
            
        except AdvertiserRequest.DoesNotExist:
            raise NotFound("Advertiser request not found")


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
                    {"error": "This request has already been reviewed."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            reason = request.data.get('reason', 'No reason provided')
            
            # Reject the advertiser
            advertiser_request.reject(reason=reason)
            
            # Optional: Send email notification
            # send_mail(
            #     subject='Your Advertiser Request Update',
            #     message=f'Unfortunately, your request was not approved. Reason: {reason}',
            #     from_email='noreply@yoursite.com',
            #     recipient_list=[advertiser_request.user.email],
            # )
            
            return Response({
                "success": True,
                "message": "Advertiser request rejected.",
                "reason": reason,
                "data": AdvertiserRequestSerializer(advertiser_request).data
            }, status=status.HTTP_200_OK)
            
        except AdvertiserRequest.DoesNotExist:
            raise NotFound("Advertiser request not found")


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
                    {"error": "This ad is already approved."},
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
            
            # Optional: Send email notification
            # send_mail(
            #     subject='Your Ad has been Approved!',
            #     message=f'Your ad "{ad.title}" is now live.',
            #     from_email='noreply@yoursite.com',
            #     recipient_list=[ad.advertiser.email],
            # )
            
            return Response({
                "success": True,
                "message": f"Ad '{ad.title}' has been approved and is now active.",
                "data": AdSerializer(ad).data
            }, status=status.HTTP_200_OK)
            
        except CustomAd.DoesNotExist:
            raise NotFound("Ad not found")


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
                    {"error": "Cannot reject an already approved ad. Pause it instead."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            reason = request.data.get('reason', 'No reason provided')
            feedback = request.data.get('feedback', '')
            
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
            
            # Optional: Send email notification
            # send_mail(
            #     subject='Your Ad Review Update',
            #     message=f'Your ad "{ad.title}" was not approved. Reason: {reason}',
            #     from_email='noreply@yoursite.com',
            #     recipient_list=[ad.advertiser.email],
            # )
            
            return Response({
                "success": True,
                "message": "Ad rejected.",
                "reason": reason,
                "feedback": feedback,
                "data": AdSerializer(ad).data
            }, status=status.HTTP_200_OK)
            
        except CustomAd.DoesNotExist:
            raise NotFound("Ad not found")


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
                    {"error": "Invalid action. Use 'pause' or 'unpause'."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            ad.save()
            
            return Response({
                "success": True,
                "message": message,
                "data": AdSerializer(ad).data
            }, status=status.HTTP_200_OK)
            
        except CustomAd.DoesNotExist:
            raise NotFound("Ad not found")


class AdminDashboardStatsView(APIView):
    """
    Admin dashboard statistics
    GET: /api/ads/admin/stats/
    """
    permission_classes = [IsAdminUser]
    
    def get(self, request):
        # Advertiser stats
        total_advertisers = User.objects.filter(ads_provided=True).count()
        pending_requests = AdvertiserRequest.objects.filter(is_reviewed=False).count()
        
        # Ad stats
        total_ads = CustomAd.objects.count()
        pending_ads = CustomAd.objects.filter(is_approved=False, status='active').count()
        active_ads = CustomAd.objects.filter(is_approved=True, status='active').count()
        
        # Revenue stats
        total_revenue = CustomAd.objects.aggregate(
            total=Sum('spent_amount')
        )['total'] or 0
        
        # Recent activities
        recent_requests = AdvertiserRequest.objects.filter(
            is_reviewed=False
        ).order_by('-applied_at')[:5]
        
        recent_ads = CustomAd.objects.filter(
            is_approved=False
        ).order_by('-created_at')[:5]
        
        return Response({
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
        })


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
        ad_ids = request.data.get('ad_ids', [])
        
        if not ad_ids:
            return Response(
                {"error": "Please provide ad_ids array"},
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
        
        return Response({
            "success": True,
            "message": f"{count} ads approved successfully.",
            "approved_ids": list(ads.values_list('id', flat=True))
        })


class AdminBulkRejectAdsView(APIView):
    """
    Bulk reject multiple ads
    POST: /api/ads/admin/ads/bulk-reject/
    Body: {"ad_ids": [1, 2, 3], "reason": "Policy violation"}
    """
    permission_classes = [IsAdminUser]
    
    @transaction.atomic
    def post(self, request):
        ad_ids = request.data.get('ad_ids', [])
        reason = request.data.get('reason', 'Rejected by admin')
        
        if not ad_ids:
            return Response(
                {"error": "Please provide ad_ids array"},
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
        
        return Response({
            "success": True,
            "message": f"{count} ads rejected successfully.",
            "rejected_ids": list(ads.values_list('id', flat=True))
        })