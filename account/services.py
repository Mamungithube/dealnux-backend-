import random
import json
import time
from django.db import transaction
from django.core.mail import EmailMessage
from django.conf import settings
from django.template.loader import render_to_string
from account.models import User, Profile


def generate_otp_code():
    """Generate a random 4-digit OTP code."""
    return str(random.randint(1000, 9999))


def send_otp_email(user, email, subject="Your New OTP Code", template_name="send_code.html"):
    """Send an OTP email to the specified email address."""
    otp_code = generate_otp_code()
    user.otp = otp_code
    user.save()

    html_content = render_to_string(template_name, {'otp': otp_code, 'user': user})

    msg = EmailMessage(
        subject=subject,
        body=html_content,
        from_email=settings.EMAIL_HOST_USER,
        to=[email],
    )
    msg.content_subtype = "html"
    msg.send()
    return otp_code


def verify_user_otp(email, otp):
    """
    Verify user OTP and activate account.
    Returns (success, message, user_object_or_error_dict).
    """
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return False, "No account found with this email address.", None

    if not user.otp:
        return False, "No OTP found. Please request a new OTP.", None

    if user.otp.strip().upper() != otp.strip().upper():
        return False, "The OTP you entered is incorrect.", None

    user.is_active = True
    user.otp = None
    user.save()
    return True, "Account verification successful.", user


def complete_profile_setup(user, validated_data):
    """
    Service to complete profile setup atomically and handle referral code.
    Returns (success, message, profile_instance_or_error_message).
    """
    with transaction.atomic():
        profile, created = Profile.objects.get_or_create(user=user)

        address_data = validated_data.get('address')
        interests = validated_data.get('interests')
        profile_picture = validated_data.get('profile_picture')
        referred_by_code = validated_data.get('referred_by_code')

        if address_data:
            profile.address = validated_data.get('address', '')
            profile.address_2 = validated_data.get('address_2', '')
            profile.city = validated_data.get('city', '')
            profile.state = validated_data.get('state', '')
            profile.zip_code = validated_data.get('zip_code', '')
            profile.country = validated_data.get('country', '')

        if interests:
            profile.interests = json.dumps(interests)

        if profile_picture:
            profile.profile_picture = profile_picture

        profile.save()

        if referred_by_code and not user.has_claimed_referral:
            referred_by_code = referred_by_code.strip()
            if not referred_by_code:
                return False, "Referral code cannot be empty.", None

            try:
                referrer = User.objects.get(referral_code=referred_by_code)
                if referrer == user:
                    return False, "You cannot use your own referral code.", None
                user.referred_by = referrer
                user.has_claimed_referral = True
            except User.DoesNotExist:
                return False, "Invalid referral code.", None

        user.profile_setup_completed = True
        user.save()
        return True, "Profile setup completed successfully.", profile
