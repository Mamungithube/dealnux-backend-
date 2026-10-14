import time
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from policy.services import record_user_cookie_consent


class CookieConsentView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        preferences = request.data
        if request.user.is_authenticated:
            record_user_cookie_consent(request.user, preferences)
            return Response({
                "success": True,
                "type": "authenticated",
                "timestamp": int(time.time()),
                "data": preferences
            })
        else:
            return Response({
                "success": True,
                "type": "guest",
                "timestamp": int(time.time()),
                "message": "Consent received. Frontend should store this in LocalStorage/Cookie."
            })
