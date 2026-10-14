from rest_framework import viewsets
from rest_framework.permissions import IsAdminUser
from account.models import User
from account.serializers import UserSerializer


# -------------------------- Admin User CRUD Management ViewSet --------------------------
class UserAPIView(viewsets.ModelViewSet):
    http_method_names = ['get', 'post', 'put', 'delete']
    permission_classes = [IsAdminUser]
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
