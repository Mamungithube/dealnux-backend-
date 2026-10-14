import logging
from django.db import IntegrityError
from rest_framework.views import APIView
from rest_framework import permissions, status

from policy.models import Review
from policy.serializers import ReviewSerializer
from policy.services import save_user_review
from .base import api_response

logger = logging.getLogger(__name__)


class ReviewView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            reviews = Review.objects.all().order_by('-created_at')
            serializer = ReviewSerializer(reviews, many=True)
            return api_response(
                success=True,
                code=status.HTTP_200_OK,
                message="Reviews retrieved successfully.",
                data=serializer.data
            )
        except Exception as e:
            logger.error(f"Error fetching reviews: {str(e)}")
            return api_response(
                success=False,
                code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                message="Something went wrong while fetching reviews.",
                data=None
            )

    def post(self, request):
        try:
            data, is_created, message = save_user_review(request.user, request.data, ReviewSerializer)
            return api_response(
                success=True,
                code=status.HTTP_201_CREATED if is_created else status.HTTP_200_OK,
                message=message,
                data=data
            )
        except ValueError as e:
            return api_response(
                success=False,
                code=status.HTTP_400_BAD_REQUEST,
                message="Validation error.",
                data=e.args[0] if e.args else None
            )
        except IntegrityError as e:
            logger.warning(f"Review IntegrityError for user {request.user.id}: {str(e)}")
            return api_response(
                success=False,
                code=status.HTTP_400_BAD_REQUEST,
                message="You have already submitted a review.",
                data=None
            )
        except Exception as e:
            logger.error(f"Unexpected error creating review for user {request.user.id}: {str(e)}")
            return api_response(
                success=False,
                code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                message="Something went wrong. Please try again later.",
                data=None
            )
