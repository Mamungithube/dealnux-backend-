import logging
from django.conf import settings
from django.core.mail import EmailMessage
from .models import PressInquiry

logger = logging.getLogger(__name__)


def send_press_inquiry_emails(inquiry: PressInquiry) -> bool:
    """
    Business logic for dispatching press inquiry notification & confirmation emails.
    """
    # 1. Send Email to Press Department
    try:
        press_email = EmailMessage(
            subject=f"New Press Inquiry: {inquiry.subject}",
            body=f"""Hello Press Team,

You have received a new media/press inquiry from the website.

Name    : {inquiry.full_name}
Email   : {inquiry.email}
Subject : {inquiry.subject}

Message:
{inquiry.message}

Received At: {inquiry.created_at}""",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=['press@dealnux.shop'],
            reply_to=[inquiry.email],
        )
        press_email.send(fail_silently=True)
    except Exception as e:
        logger.warning(f"Failed to send press team notification: {e}")

    # 2. Confirmation Email to the Sender
    try:
        user_conf = EmailMessage(
            subject="We received your Press Inquiry - Dealnux",
            body=f"Hi {inquiry.full_name},\n\nThank you for reaching out to Dealnux Press Room. We have received your inquiry regarding '{inquiry.subject}' and our media team will get back to you soon.\n\nBest Regards,\nDealnux Media Team",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[inquiry.email],
        )
        user_conf.send(fail_silently=True)
    except Exception as e:
        logger.warning(f"Failed to send sender confirmation email: {e}")

    return True
