import time
from django.db import IntegrityError
from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response

from ..models import AdvertiserRequest
from ..serializers import AdvertiserRequestSerializer


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
