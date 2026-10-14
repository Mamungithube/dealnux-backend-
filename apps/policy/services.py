import logging
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction, IntegrityError
from django.utils import timezone

from .models import ContactMessage, Review

logger = logging.getLogger(__name__)


# ============================================================================
# Contact Support & Ticket Notification Services
# ============================================================================

def process_contact_submission(contact: ContactMessage) -> str:
    """
    Business logic for processing contact inquiries:
    - Normalizes ticket identifier format
    - Dispatches notification to admin
    - Dispatches confirmation email to inquiry submitter
    Returns formatted ticket_id string.
    """
    ticket_id = contact.ticket_id if str(contact.ticket_id).startswith("DNX-") else f"DNX-{contact.ticket_id}"

    from_email = (
        getattr(settings, 'NO_REPLY_EMAIL', None)
        or getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        or getattr(settings, 'EMAIL_HOST_USER', None)
        or 'noreply@dealnux.shop'
    )
    admin_recipient = getattr(settings, 'ADMIN_EMAIL', None) or 'admin@dealnux.com'

    # 1. Send inquiry notification to admin
    try:
        admin_email = EmailMessage(
            subject=f"[{ticket_id}] New Contact: {contact.subject}",
            body=f"""New contact message received!

Ticket ID   : {ticket_id}
Name        : {contact.full_name}
Email       : {contact.email}
Subject     : {contact.subject}

Message:
{contact.message}

Received At : {contact.created_at}""",
            from_email=from_email,
            to=[admin_recipient],
            reply_to=[contact.email],
        )
        admin_email.send(fail_silently=False)
    except Exception as e:
        logger.error(f"Failed to send contact notification email to admin ({admin_recipient}): {str(e)}", exc_info=True)

    # 2. Send confirmation ticket email to user
    try:
        user_email = EmailMessage(
            subject=f"[{ticket_id}] We’ve received your message | DealNux Support.",
            body=f"""Thank you for contacting DealNux. We’ve received your message, and our support team will review your inquiry and get back to you as soon as possible.

Ticket ID: {ticket_id}
Subject: {contact.subject}

Please keep your Ticket ID for reference if you need to follow up.

Thank you for choosing DealNux.

DealNux Admin
SHOP SMARTER. SAVE BIGGER.
www.dealnux.shop""",
            from_email=from_email,
            to=[contact.email],
        )
        user_email.send(fail_silently=False)
    except Exception as e:
        logger.error(f"Failed to send contact confirmation email to user ({contact.email}): {str(e)}", exc_info=True)

    return ticket_id


# ============================================================================
# Platform Review Services
# ============================================================================

def save_user_review(user, data: dict, serializer_class) -> tuple[dict, bool, str]:
    """
    Business logic for creating or updating a user's platform review.
    Returns (serialized_data, is_created, message).
    """
    existing_review = Review.objects.filter(user=user).first()

    if existing_review:
        serializer = serializer_class(existing_review, data=data, partial=True)
        message = "Review updated successfully."
        is_created = False
    else:
        serializer = serializer_class(data=data)
        message = "Review created successfully."
        is_created = True

    if not serializer.is_valid():
        raise ValueError(serializer.errors)

    with transaction.atomic():
        serializer.save(user=user)

    return serializer.data, is_created, message


# ============================================================================
# Cookie Consent Services
# ============================================================================

def record_user_cookie_consent(user, preferences: dict):
    """
    Saves cookie consent preferences for an authenticated user.
    """
    user.cookie_preferences = preferences
    user.cookie_consent_date = timezone.now()
    user.save(update_fields=['cookie_preferences', 'cookie_consent_date'])
    return preferences
