import logging
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.conf import settings

logger = logging.getLogger(__name__)


def send_dealnux_email(subject, recipient_email, template_name, context, async_send=True):
    """
    Centralized email sender for DealNux.
    Dispatches asynchronously via Celery by default.
    Falls back to synchronous sending if Celery/broker is unavailable.
    """
    try:
        html_content = render_to_string(template_name, context)

        if async_send:
            try:
                from notifications.tasks import send_email_async_task
                send_email_async_task.delay(subject, recipient_email, html_content)
                return True
            except Exception as task_exc:
                logger.warning(
                    f"Celery async queue unavailable ({task_exc}), falling back to sync email sending to {recipient_email}."
                )

        # Synchronous fallback
        msg = EmailMessage(
            subject=subject,
            body=html_content,
            from_email=settings.EMAIL_HOST_USER,
            to=[recipient_email],
        )
        msg.content_subtype = "html"
        msg.send()
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {recipient_email}: {e}")
        return False
