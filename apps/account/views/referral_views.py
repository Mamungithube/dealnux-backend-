from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from account.models import SiteSettings
from account.services import get_user_referral_statistics


# -------------------------- Site Settings & Referral Reward Config API View --------------------------
@api_view(['GET'])
@permission_classes([AllowAny])
def site_settings_view(request):
    settings_instance = SiteSettings.get()

    data = {
        'referral_reward_amount': float(settings_instance.referral_reward_amount),
        'user_referral_amount': 0.0
    }

    if request.user.is_authenticated:
        data['user_referral_amount'] = float(request.user.balance)

    return Response(data)


# -------------------------- User Referral Statistics & Earnings Overview View --------------------------
class ReferralStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        stats = get_user_referral_statistics(request.user)
        return Response({
            "success": True,
            "code": 200,
            "message": "Referral statistics retrieved.",
            "data": stats
        })
