from rest_framework import serializers
from account.models import Profile, User
from django.contrib.auth import get_user_model, password_validation
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
import json
import random

User = get_user_model()


def generate_otp():
    return str(random.randint(1000, 9999))


"""--------User Serializer--------"""


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'is_active', 'is_staff']
        extra_kwargs = {
            'name': {'required': True},
            'email': {'required': True},
        }

    def update(self, instance, validated_data):
        instance.name = validated_data.get('name', instance.name)
        instance.email = validated_data.get('email', instance.email)
        instance.save()
        return instance


"""--------Register Serializer--------"""


class RegisterSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ['name', 'email', 'password']
        extra_kwargs = {
            'password': {'write_only': True},
        }

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        user.is_active = False

        #  Save OTP directly in User model
        otp = generate_otp()
        user.otp = otp
        user.save()

        # Send email with OTP
        subject = 'Your OTP Code - Email Verification Your Account'
        html_content = render_to_string(
            'send_code.html', {'otp': otp, 'user': user}
        )
        try:
            msg = EmailMessage(
                subject=subject,
                body=html_content,
                from_email=settings.EMAIL_HOST_USER,
                to=[user.email],
            )
            msg.content_subtype = 'html'
            msg.send()
        except Exception as e:
            print(f"Failed to send email to {user.email}: {str(e)}")

        return user


# ==================== Reset Password Serializer ====================
class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError("Passwords do not match")
        return data


# ==================== Change Password Serializer ====================
class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True)
    confirm_password = serializers.CharField(required=True, write_only=True)

    def validate_new_password(self, value):
        password_validation.validate_password(value, self.context['request'].user)
        return value

    def validate(self, data):
        if data["new_password"] != data["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "New password and confirm password do not match."})
        return data


# ==================== Login Serializer ====================
class LoginSerializer(serializers.Serializer):
    email = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True)


# ==================== User Login Serializer ====================
class UserLoginSerializer(serializers.ModelSerializer):
    tokens = serializers.SerializerMethodField()

    def get_tokens(self, user):
        refresh = RefreshToken.for_user(user)
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }

    class Meta:
        model = User
        fields = ['email', 'tokens']


# ==================== Profile Serializer (Read-Only/Response) ====================
class ProfileSerializer(serializers.ModelSerializer):
    name                 = serializers.SerializerMethodField()
    email                = serializers.SerializerMethodField()
    first_name           = serializers.SerializerMethodField()  # ← নতুন
    last_name            = serializers.SerializerMethodField()  # ← নতুন
    refaradal_code       = serializers.SerializerMethodField()
    interests            = serializers.SerializerMethodField()
    balance              = serializers.SerializerMethodField()
    has_claimed_referral = serializers.SerializerMethodField()
    referred_by          = serializers.SerializerMethodField()

    class Meta:
        model  = Profile
        fields = [
            'name', 'first_name', 'last_name', 'email',  # ← নতুন
            'profile_picture',
            'address', 'address_2', 'city', 'state', 'zip_code', 'country',  # ← নতুন
            'interests',
            'refaradal_code', 'balance', 'has_claimed_referral', 'referred_by',
        ]

    def get_name(self, obj):
        return getattr(obj.user, 'name', '') if obj.user else ''

    def get_email(self, obj):
        return getattr(obj.user, 'email', '') if obj.user else ''

    def get_first_name(self, obj):  # ← নতুন
        return getattr(obj.user, 'first_name', '') if obj.user else ''

    def get_last_name(self, obj):   # ← নতুন
        return getattr(obj.user, 'last_name', '') if obj.user else ''

    def get_refaradal_code(self, obj):
        return getattr(obj.user, 'referral_code', '') if obj.user else ''

    def get_balance(self, obj):
        return float(getattr(obj.user, 'balance', 0)) if obj.user else 0

    def get_has_claimed_referral(self, obj):
        return getattr(obj.user, 'has_claimed_referral', False) if obj.user else False

    def get_referred_by(self, obj):
        if obj.user and obj.user.referred_by:
            return {
                'name':          obj.user.referred_by.name,
                'email':         obj.user.referred_by.email,
                'referral_code': obj.user.referred_by.referral_code
            }
        return None

    def get_interests(self, obj):
        if not obj.interests:
            return []
        data = obj.interests
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (ValueError, TypeError):
                return []
        if isinstance(data, list) and len(data) > 0:
            if isinstance(data[0], str) and data[0].startswith('['):
                try:
                    return json.loads(data[0])
                except:
                    return data
        return data if isinstance(data, list) else []


"""==================== Profile Setup Serializer (Write) ===================="""


class AddressSerializer(serializers.Serializer):
    address   = serializers.CharField(max_length=255)
    address_2 = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    city      = serializers.CharField(max_length=100)
    state     = serializers.CharField(max_length=100)
    zip_code  = serializers.CharField(max_length=20)
    country   = serializers.CharField(max_length=100)


class ProfileSetupSerializer(serializers.Serializer):
    email            = serializers.EmailField(required=True)
    address          = serializers.CharField(max_length=255, required=False, allow_blank=True)
    address_2        = serializers.CharField(max_length=255, required=False, allow_blank=True)
    city             = serializers.CharField(max_length=100, required=False, allow_blank=True)
    state            = serializers.CharField(max_length=100, required=False, allow_blank=True)
    zip_code         = serializers.CharField(max_length=20, required=False, allow_blank=True)
    country          = serializers.CharField(max_length=100, required=False, allow_blank=True)
    interests        = serializers.ListField(
                           child=serializers.CharField(),
                           required=False, allow_empty=True)
    profile_picture  = serializers.ImageField(required=False, allow_null=True)
    referred_by_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class ProfileUpdateSerializer(serializers.ModelSerializer):
    name         = serializers.CharField(source='user.name', required=False)
    first_name   = serializers.CharField(source='user.first_name', required=False)
    last_name    = serializers.CharField(source='user.last_name', required=False)
    address      = serializers.CharField(max_length=255, required=False, allow_blank=True)
    address_2    = serializers.CharField(max_length=255, required=False, allow_blank=True)
    city         = serializers.CharField(max_length=100, required=False, allow_blank=True)
    state        = serializers.CharField(max_length=100, required=False, allow_blank=True)
    zip_code     = serializers.CharField(max_length=20, required=False, allow_blank=True)
    country      = serializers.CharField(max_length=100, required=False, allow_blank=True)
    interests    = serializers.ListField(
                       child=serializers.CharField(),
                       required=False, allow_empty=True)

    class Meta:
        model  = Profile
        fields = [
            'name', 'first_name', 'last_name',
            'profile_picture',
            'address', 'address_2', 'city', 'state', 'zip_code', 'country',
            'interests',
        ]

    def update(self, instance, validated_data):
        interests_list = validated_data.pop('interests', None)
        if interests_list is not None:
            instance.interests = json.dumps(interests_list)

        user_data = validated_data.pop('user', {})
        if user_data:
            for attr, value in user_data.items():
                setattr(instance.user, attr, value)
            instance.user.save()

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance