from rest_framework import generics, permissions
from .models import PressCoverage
from .serializers import PressCoverageSerializer


class PressCoverageListView(generics.ListAPIView):
    serializer_class = PressCoverageSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return PressCoverage.objects.filter(is_featured=True)