"""
Fixed email test — from_email must match EMAIL_HOST_USER for Gmail.
Run: .venv\Scripts\python.exe scratch\test_email.py
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

import django
from django.conf import settings

HOST_USER = os.getenv("EMAIL_HOST_USER", "")

if not settings.configured:
    settings.configure(
        EMAIL_BACKEND=os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"),
        EMAIL_HOST=os.getenv("EMAIL_HOST", "smtp.gmail.com"),
        EMAIL_PORT=int(os.getenv("EMAIL_PORT", "587")),
        EMAIL_USE_TLS=os.getenv("EMAIL_USE_TLS", "True") == "True",
        EMAIL_HOST_USER=HOST_USER,
        EMAIL_HOST_PASSWORD=os.getenv("EMAIL_HOST_PASSWORD"),
        # CRITICAL: from_email must match the authenticated Gmail account
        DEFAULT_FROM_EMAIL=HOST_USER,
    )
    django.setup()

from django.core.mail import send_mail

RECIPIENT = "orroshidmdmamun50@gmail.com"

print("\nSending test email to:", RECIPIENT)
print("  HOST      :", os.getenv("EMAIL_HOST"))
print("  PORT      :", os.getenv("EMAIL_PORT"))
print("  LOGIN AS  :", HOST_USER)
print("  FROM      :", HOST_USER, "  <-- fixed to match login")
print()

try:
    result = send_mail(
        subject="[DealNux] Email Test v2 - Career Notification",
        message=(
            "Test email from DealNux backend.\n\n"
            "If you received this, Gmail SMTP is working correctly.\n"
            "Career application notifications will reach the client.\n\n"
            "FROM account: " + HOST_USER
        ),
        from_email=HOST_USER,   # MUST match EMAIL_HOST_USER for Gmail
        recipient_list=[RECIPIENT],
        fail_silently=False,
    )
    print("SUCCESS -- send_mail returned:", result)
    print("Check inbox AND spam folder of:", RECIPIENT)
except Exception as e:
    print("FAILED --", type(e).__name__, ":", e)
    sys.exit(1)
