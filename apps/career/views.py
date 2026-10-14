import logging

from rest_framework import generics, status, permissions
from rest_framework.response import Response
from django.core.mail import send_mail
from django.conf import settings
from .models import CareerApplication
from .serializers import CareerApplicationSerializer
from .services import send_career_application_notification

logger = logging.getLogger(__name__)


# -------------------------- Career Application Create View (Public) --------------------------
class CareerApplicationCreateView(generics.CreateAPIView):
    serializer_class = CareerApplicationSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = serializer.save()

        send_career_application_notification(application)

        return Response(
            {"detail": "Application submitted successfully. We will contact you soon."},
            status=status.HTTP_201_CREATED
        )


# -------------------------- Career Application List View (Admin Only) --------------------------
class CareerApplicationListView(generics.ListAPIView):
    serializer_class = CareerApplicationSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = CareerApplication.objects.all()


# -------------------------- Career Role Choices List View (Public) --------------------------
class CareerRoleListView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        roles = [
            {"value": "Product Manager", "label": "Product Manager"},
            {"value": "Data Analyst", "label": "Data Analyst"},
            {"value": "Digital Marketing Specialist", "label": "Digital Marketing Specialist"},
            {"value": "Customer Support Specialist", "label": "Customer Support Specialist"},
            {"value": "Sales Executive", "label": "Sales Executive"},
            {"value": "Other", "label": "Other"},
        ]
        return Response({"roles": roles}, status=status.HTTP_200_OK)
