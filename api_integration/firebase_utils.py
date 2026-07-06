
import os
import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings

certificate_path = os.path.join(settings.BASE_DIR, 'firebase-key.json')

import logging
logger = logging.getLogger(__name__)

import json

if not firebase_admin._apps:
    try:
        firebase_creds_json = os.environ.get('FIREBASE_CREDENTIALS_JSON')
        if firebase_creds_json:
            creds_dict = json.loads(firebase_creds_json)
            cred = credentials.Certificate(creds_dict)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase initialized successfully using environment variable.")
        else:
            cred = credentials.Certificate(certificate_path)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase initialized successfully using root key file.")
    except Exception as e:
        logger.error(f"Firebase Error: {str(e)}")

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