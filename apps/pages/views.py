from rest_framework import generics, permissions, status
from rest_framework.response import Response
from .models import PressCoverage
from .serializers import PressCoverageSerializer, PressInquirySerializer
from .services import send_press_inquiry_emails


# -------------------------- Press Coverage List View (Public Featured Press) --------------------------
class PressCoverageListView(generics.ListAPIView):
    serializer_class = PressCoverageSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return PressCoverage.objects.filter(is_featured=True)


# -------------------------- Press Inquiry Create View (Public Media Contact) --------------------------
class PressInquiryCreateView(generics.CreateAPIView):
    serializer_class = PressInquirySerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        inquiry = serializer.save()

        send_press_inquiry_emails(inquiry)

        return Response(
            {"success": True, "message": "Your inquiry has been sent to our press team."},
            status=status.HTTP_201_CREATED
        )