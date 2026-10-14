import time
from django.db import transaction
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import AdvertiserRequest, CustomAd
from ..permissions import IsAdminUser
from ..serializers import AdSerializer, AdvertiserRequestSerializer
from ..services import (
    approve_advertiser_request,
    approve_custom_ad,
    bulk_approve_ads,
    bulk_reject_ads,
    get_admin_dashboard_stats,
    pause_or_unpause_ad,
    reject_advertiser_request,
    reject_custom_ad,
)


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

            advertiser_request = approve_advertiser_request(advertiser_request)

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

            advertiser_request = reject_advertiser_request(advertiser_request, reason=reason)

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
                is_approved=False, status='pending')
        elif status_filter == 'approved':
            queryset = queryset.filter(is_approved=True, status='active')
        elif status_filter == 'rejected':
            queryset = queryset.filter(status='rejected')

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
            ad = CustomAd.objects.get(pk=pk)

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

            ad = approve_custom_ad(ad, reviewer=request.user)

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


class AdminRejectAdView(APIView):
    """
    Admin rejects an ad
    POST: /api/ads/admin/ads/<id>/reject/
    Body: {"reason": "Inappropriate content", "feedback": "Please revise the image"}
    """
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            ad = CustomAd.objects.get(pk=pk)

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

            ad = reject_custom_ad(ad, reason=reason, feedback=feedback, reviewer=request.user)

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


class AdminPauseAdView(APIView):
    """
    Admin can pause/unpause an approved ad
    POST: /api/ads/admin/ads/<id>/pause/
    POST: /api/ads/admin/ads/<id>/unpause/
    """
    permission_classes = [IsAdminUser]

    def post(self, request, pk, action):
        try:
            ad = CustomAd.objects.get(pk=pk)
            ad, message = pause_or_unpause_ad(ad, action=action)

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

        except ValueError as ve:
            return Response(
                {
                    "success": False,
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": str(ve),
                    "timestamp": int(time.time()),
                    "data": {"detail": str(ve)}
                },
                status=status.HTTP_400_BAD_REQUEST
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


class AdminDashboardStatsView(APIView):
    """
    Admin dashboard statistics
    GET: /api/ads/admin/stats/
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        try:
            stats = get_admin_dashboard_stats()

            return Response(
                {
                    "success": True,
                    "code": status.HTTP_200_OK,
                    "message": "Dashboard statistics retrieved successfully.",
                    "timestamp": int(time.time()),
                    "data": {
                        'advertisers': stats['advertisers'],
                        'ads': stats['ads'],
                        'revenue': stats['revenue'],
                        'recent_activity': {
                            'pending_requests': AdvertiserRequestSerializer(stats['recent_requests'], many=True).data,
                            'pending_ads': AdSerializer(stats['recent_ads'], many=True).data
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


class AdminBulkApproveAdsView(APIView):
    """
    Bulk approve multiple ads
    POST: /api/ads/admin/ads/bulk-approve/
    Body: {"ad_ids": [1, 2, 3, 4]}
    """
    permission_classes = [IsAdminUser]

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

            ads = bulk_approve_ads(ad_ids=ad_ids, reviewer=request.user)

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


class AdminBulkRejectAdsView(APIView):
    """
    Bulk reject multiple ads
    POST: /api/ads/admin/ads/bulk-reject/
    Body: {"ad_ids": [1, 2, 3], "reason": "Policy violation"}
    """
    permission_classes = [IsAdminUser]

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

            ads = bulk_reject_ads(ad_ids=ad_ids, reason=reason, reviewer=request.user)

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
