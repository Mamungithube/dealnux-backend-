import logging
from django.conf import settings
from django.core.mail import send_mail
from .models import CareerApplication

logger = logging.getLogger(__name__)


def send_career_application_notification(application: CareerApplication) -> bool:
    """
    Business logic for notifying admin when a new career application is submitted.
    """
    try:
        from_email = (
            getattr(settings, 'EMAIL_HOST_USER', None)
            or getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@dealnux.shop')
        )
        admin_email = getattr(settings, 'ADMIN_EMAIL', None) or 'admin@dealnux.com'

        send_mail(
            subject=f"[DealNux] New Career Application - {application.get_role_display()}",
            message=f"""
New application received!

Name     : {application.full_name}
Email    : {application.email}
Phone    : {application.phone}
Role     : {application.get_role_display()}

Experience:
{application.experience}

Why Join:
{application.why_join}

Portfolio : {application.portfolio_url or 'N/A'}
LinkedIn  : {application.linkedin_url or 'N/A'}

Applied At: {application.applied_at}

Login to admin panel to review: {getattr(settings, 'SITE_URL', '')}/admin/career/careerapplication/
            """,
            from_email=from_email,
            recipient_list=[admin_email],
            fail_silently=False,
        )
        logger.info(
            f"[Career] Notification email sent for application: {application.full_name} ({application.email})"
        )
        return True
    except Exception as e:
        logger.error(
            f"[Career] Failed to send notification email for application "
            f"'{application.full_name}' (id={application.pk}): {e}",
            exc_info=True,
        )
        return False
