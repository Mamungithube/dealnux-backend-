from rest_framework import generics, permissions, status
from rest_framework.response import Response

from policy.models import ContactMessage
from policy.serializers import ContactMessageSerializer
from policy.services import process_contact_submission


class ContactMessageCreateView(generics.CreateAPIView):
    serializer_class = ContactMessageSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        contact = serializer.save()

        # Delegate business logic (notifications, emails, formatting) to service layer
        ticket_id = process_contact_submission(contact)

        return Response(
            {
                "detail": "Message sent successfully. We'll reply within one business day.",
                "ticket_id": ticket_id,
            },
            status=status.HTTP_201_CREATED
        )


class ContactMessageListView(generics.ListAPIView):
    serializer_class = ContactMessageSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = ContactMessage.objects.all()
