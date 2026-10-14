import os
import requests
import jwt
from jwt.algorithms import RSAAlgorithm
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from account.models import User, Profile


# -------------------------- Google OAuth2 Social Login API View --------------------------
@api_view(['POST'])
@permission_classes([AllowAny])
def google_login(request):
    access_token = request.data.get('access_token')
    if not access_token:
        return Response({'error': 'Token required'}, status=400)

    try:
        userinfo_response = requests.get(
            'https://www.googleapis.com/oauth2/v3/userinfo',
            headers={'Authorization': f'Bearer {access_token}'}
        )

        if userinfo_response.status_code != 200:
            return Response({'error': 'Invalid token'}, status=400)

        userinfo = userinfo_response.json()
        email = userinfo.get('email')
        name = userinfo.get('name', '')

        if not email:
            return Response({'error': 'Email not found'}, status=400)

        user, created = User.objects.get_or_create(
            email=email,
            defaults={'is_active': True}
        )
        if created and name:
            user.name = name
            user.save()

        Profile.objects.get_or_create(user=user)

        refresh = RefreshToken.for_user(user)
        return Response({
            "success": True,
            "code": 200,
            "message": "Google login successful",
            "data": {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "profile_setup_completed": user.profile_setup_completed
                }
            }
        })
    except Exception as e:
        return Response({'error': str(e)}, status=400)


# -------------------------- Apple Sign-In OAuth Social Login API View --------------------------
@api_view(['POST'])
@permission_classes([AllowAny])
def apple_login(request):
    identity_token = request.data.get('access_token')
    if not identity_token:
        return Response({'error': 'Token required'}, status=400)

    try:
        apple_keys = requests.get('https://appleid.apple.com/auth/keys').json()

        header = jwt.get_unverified_header(identity_token)
        key = next(k for k in apple_keys['keys'] if k['kid'] == header['kid'])

        public_key = RSAAlgorithm.from_jwk(key)

        payload = jwt.decode(
            identity_token,
            public_key,
            algorithms=['RS256'],
            audience=os.environ.get('APPLE_CLIENT_ID'),
        )

        email = payload.get('email')
        if not email:
            return Response({'error': 'Email not found'}, status=400)

        user, created = User.objects.get_or_create(
            email=email,
            defaults={'is_active': True}
        )

        Profile.objects.get_or_create(user=user)

        refresh = RefreshToken.for_user(user)
        return Response({
            "success": True,
            "code": 200,
            "message": "Apple login successful",
            "data": {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "profile_setup_completed": user.profile_setup_completed
                }
            }
        })
    except Exception as e:
        return Response({'error': str(e)}, status=400)
