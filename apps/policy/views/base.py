import time
from rest_framework.views import APIView
from rest_framework import permissions, status
from rest_framework.response import Response


from config.responses import api_response



class PolicyGetBaseView(APIView):
    """Reusable base view for public GET-only policy retrieval."""
    model = None
    serializer_class = None
    policy_name = "Policy"
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        policy = self.model.objects.first()
        if not policy:
            return api_response(
                success=False,
                code=status.HTTP_404_NOT_FOUND,
                message=f"{self.policy_name} not found.",
                data=None
            )
        serializer = self.serializer_class(policy)
        return api_response(
            success=True,
            code=status.HTTP_200_OK,
            message=f"{self.policy_name} retrieved successfully.",
            data=serializer.data
        )
