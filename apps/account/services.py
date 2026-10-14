import random
import json
import time
from datetime import timedelta
from django.db import transaction
from django.core.mail import EmailMessage
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from account.models import User, Profile, SiteSettings
from payment.utils import refresh_subscription_limits
from payment.models import SubscriptionPlan, UserSubscription
from store.models import SellerRequest
from custom_ads.models import AdvertiserRequest


# ============================================================================
# OTP & Registration Services
# ============================================================================

def generate_otp_code() -> str:
    """Generate a random 4-digit OTP code."""
    return str(random.randint(1000, 9999))


def send_otp_email(user, email: str, subject: str = "Your New OTP Code", template_name: str = "send_code.html") -> str:
    """Send an OTP email to the specified email address."""
    otp_code = generate_otp_code()
    user.otp = otp_code
    user.save(update_fields=['otp'])

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


def resend_user_otp(email: str) -> tuple[bool, str]:
    """
    Business logic for resending activation OTP to a registered user.
    """
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return False, "No account found with this email address."

    send_otp_email(user, email, subject='Your New OTP Code', template_name='send_code.html')
    return True, "OTP has been resent to your email."


def verify_user_otp(email: str, otp: str) -> tuple[bool, str, User | None]:
    """
    Verify user OTP and activate account.
    Returns (success, message, user_object).
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
    user.save(update_fields=['is_active', 'otp'])
    return True, "Account verification successful.", user


# ============================================================================
# Password Management Services
# ============================================================================

def reset_user_password(email: str, new_password: str) -> tuple[bool, str]:
    """
    Business logic for password reset via forgot password.
    """
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return False, "Email not registered. Please sign up."

    user.set_password(new_password)
    user.save(update_fields=['password'])
    return True, "Password has been reset successfully."


# ============================================================================
# Profile Setup & Onboarding Services
# ============================================================================

def complete_profile_setup(user: User, validated_data: dict) -> tuple[bool, str, Profile | None, dict | None]:
    """
    Service to complete profile setup atomically and handle referral code.
    Returns (success, message, profile_instance, errors_dict).
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
            code_str = str(referred_by_code).strip()
            if not code_str:
                return False, "Referral code cannot be empty.", None, {"referred_by_code": ["Invalid referral code."]}

            try:
                referrer = User.objects.get(referral_code=code_str)
                if referrer == user:
                    return False, "You cannot use your own referral code.", None, {"referred_by_code": ["Invalid referral code."]}
                user.referred_by = referrer
                user.has_claimed_referral = True
            except User.DoesNotExist:
                return False, "Invalid referral code.", None, {"referred_by_code": ["Referral code not found."]}

        user.profile_setup_completed = True
        user.save()
        return True, "Profile setup completed successfully.", profile, None


# ============================================================================
# Account Deletion Services
# ============================================================================

def delete_user_account(user: User, data: dict) -> tuple[bool, str, dict | None, int]:
    """
    Business logic for safely verifying credentials and permanently deleting a user account.
    Returns (success, message, errors_dict, http_status_code).
    """
    email = data.get('email')
    password = data.get('password')
    otp = data.get('otp')

    errors = {}
    if not email:
        errors['email'] = ["Email address is required."]

    if not password and not otp:
        errors['password'] = ["Password or verification code (OTP) is required to confirm account deletion."]

    if errors:
        return False, "Email and password or verification code (OTP) are required to confirm account deletion.", errors, 400

    if str(email).strip().lower() != str(user.email).strip().lower():
        return False, "Email address does not match your account.", {"email": ["The provided email does not match your account email."]}, 400

    if otp:
        if not user.otp or str(user.otp).strip() != str(otp).strip():
            return False, "Invalid or expired verification code.", {"otp": ["Incorrect verification code."]}, 400
    else:
        if not user.has_usable_password():
            return False, "This account was created via social sign-in. Please request a verification code (OTP) to delete your account.", {"otp": ["Please click 'Send Verification Code' to verify with OTP."]}, 400
        if not user.check_password(password):
            return False, "Invalid password.", {"password": ["Incorrect password provided."]}, 400

    refresh_token = data.get('refresh')
    if refresh_token:
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            pass

    user.delete()
    return True, "Account deleted successfully.", None, 200


# ============================================================================
# Referral & Profile Status Services
# ============================================================================

def get_user_referral_statistics(user: User) -> dict:
    """
    Aggregates referral performance and earnings for a user.
    """
    reward_amount = float(SiteSettings.get().referral_reward_amount)
    referred_users = user.referrals.select_related('subscription').all().order_by('-date_joined')
    referrals_list = []
    successful_referrals_count = 0

    for ref_user in referred_users:
        is_awarded = ref_user.has_referral_reward_awarded
        if is_awarded:
            successful_referrals_count += 1

        sub = getattr(ref_user, 'subscription', None)
        referrals_list.append({
            "id": ref_user.id,
            "name": ref_user.name or ref_user.email,
            "email": ref_user.email,
            "date_joined": ref_user.date_joined,
            "has_claimed": ref_user.has_claimed_referral,
            "reward_awarded": is_awarded,
            "has_active_subscription": sub.is_active if sub else False
        })

    total_earnings = float(successful_referrals_count * reward_amount)

    return {
        "referral_code": user.referral_code or "",
        "balance": float(user.balance),
        "referral_reward_amount": reward_amount,
        "total_referrals": referred_users.count(),
        "successful_referrals": successful_referrals_count,
        "total_earnings": total_earnings,
        "referrals": referrals_list
    }


def get_user_account_statuses(user: User) -> dict:
    """
    Compiles auxiliary statuses (subscription, advertiser, seller) for profile view.
    """
    # 1. Advertiser Status
    if user.ads_provided:
        adv_status = {"status": "approved"}
    else:
        try:
            req = AdvertiserRequest.objects.get(user=user)
            adv_status = {
                "status": "pending" if not req.is_reviewed else "rejected",
                "applied_at": req.applied_at,
                "rejection_reason": req.rejection_reason
            }
        except AdvertiserRequest.DoesNotExist:
            adv_status = {"status": "not_applied"}

    # 2. Seller Status
    try:
        req = SellerRequest.objects.get(user=user)
        seller_data = {
            "status": req.status.lower(),
            "applied_at": req.created_at,
            "shop_name": req.trade_name,
        }
        if req.status == 'REJECTED':
            seller_data["admin_note"] = req.admin_note
    except SellerRequest.DoesNotExist:
        seller_data = {"status": "not_applied"}

    # 3. Subscription Status
    try:
        sub = UserSubscription.objects.get(user=user)
        if sub.is_active:
            sub = refresh_subscription_limits(sub)
        sub_data = {
            "plan_name": sub.plan.name,
            "status": sub.status,
            "is_active": sub.is_active,
            "expires_at": sub.expires_at,
            "days_remaining": sub.days_remaining,
            "clicks_left": sub.plan.clicks_per_day - sub.daily_click_count
        }
    except Exception:
        sub_data = {
            "plan_name": "None",
            "status": "INACTIVE",
            "is_active": False,
            "message": "No active subscription. Subscribe to access global deals."
        }

    return {
        "subscription": sub_data,
        "advertiser_status": adv_status,
        "seller_status": seller_data,
    }
