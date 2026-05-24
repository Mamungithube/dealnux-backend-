from rest_framework import generics, status, permissions
from rest_framework.response import Response
from django.core.mail import send_mail
from django.conf import settings
from .models import CareerApplication
from .serializers import CareerApplicationSerializer


class CareerApplicationCreateView(generics.CreateAPIView):
    serializer_class = CareerApplicationSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = serializer.save()

        # Client-এর email-এ notification পাঠাও
        try:
            send_mail(
                subject=f"[Dealnux] New Career Application - {application.get_role_display()}",
                message=f"""
New application received!

Name     : {application.full_name}
Email    : {application.email}
Phone    : {application.phone}
Role     : {application.get_role_display()}

Experience:
{application.experience}

Why Join:
{application.why_join}

Portfolio : {application.portfolio_url or 'N/A'}
LinkedIn  : {application.linkedin_url or 'N/A'}

Applied At: {application.applied_at}

Login to admin panel to review: {settings.SITE_URL}/admin/career/careerapplication/
                """,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.ADMIN_EMAIL],
                fail_silently=True,
            )
        except Exception:
            pass

        return Response(
            {"detail": "Application submitted successfully. We will contact you soon."},
            status=status.HTTP_201_CREATED
        )


class CareerApplicationListView(generics.ListAPIView):
    serializer_class = CareerApplicationSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = CareerApplication.objects.all()