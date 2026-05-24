# api_integration/firebase_utils.py
import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings

# Initialize Firebase App
if not firebase_admin._apps:
    cred = credentials.Certificate("path/to/your/firebase-key.json")
    firebase_admin.initialize_app(cred)

def send_push_notification(user, title, body, data=None):
    """
    Sends FCM push notification to all devices of a user.
    """
    tokens = list(user.fcm_tokens.values_list('fcm_token', flat=True))
    if not tokens:
        return

    message = messaging.MulticastMessage(
        notification=messaging.Notification(title=title, body=body),
        data=data or {},
        tokens=tokens,
    )
    
    try:
        response = messaging.send_multicast(message)
        return response.success_count
    except Exception as e:
        print(f"Firebase error: {str(e)}")
        return 0