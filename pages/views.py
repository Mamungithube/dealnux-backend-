from rest_framework import generics, permissions
from .models import PressCoverage
from .serializers import PressCoverageSerializer


class PressCoverageListView(generics.ListAPIView):
    serializer_class = PressCoverageSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return PressCoverage.objects.filter(is_featured=True)
    



# In views.py
from django.core.mail import EmailMessage
from django.conf import settings
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from .serializers import PressInquirySerializer


class PressInquiryCreateView(generics.CreateAPIView):
    serializer_class = PressInquirySerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        inquiry = serializer.save()

        # 1. Send Email to Press Department
        try:
            press_email = EmailMessage(
                subject=f"New Press Inquiry: {inquiry.subject}",
                body=f"""Hello Press Team,

You have received a new media/press inquiry from the website.

Name    : {inquiry.full_name}
Email   : {inquiry.email}
Subject : {inquiry.subject}

Message:
{inquiry.message}

Received At: {inquiry.created_at}""",
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=['press@dealnux.shop'], # Fixed recipient
                reply_to=[inquiry.email],
            )
            press_email.send(fail_silently=True)
        except Exception:
            pass

        # 2. Confirmation Email to the Sender (Optional but professional)
        try:
            user_conf = EmailMessage(
                subject="We received your Press Inquiry - Dealnux",
                body=f"Hi {inquiry.full_name},\n\nThank you for reaching out to Dealnux Press Room. We have received your inquiry regarding '{inquiry.subject}' and our media team will get back to you soon.\n\nBest Regards,\nDealnux Media Team",
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[inquiry.email],
            )
            user_conf.send(fail_silently=True)
        except Exception:
            pass

        return Response(
            {"success": True, "message": "Your inquiry has been sent to our press team."},
            status=status.HTTP_201_CREATED
        )