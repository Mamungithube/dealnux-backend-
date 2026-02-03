from rest_framework import serializers
from account.models import Profile ,User
from django.contrib.auth import get_user_model , password_validation
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.conf import settings
from django.http import HttpResponse
from django.core.exceptions import ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

import random

def generate_otp():
    return str(random.randint(1000, 9999))


"""--------User Serializer--------"""


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User 
        fields = ['id', 'full_name', 'email', 'is_active', 'is_staff']
        extra_kwargs = {
            'full_name': {'required': True},
            'email': {'required': True},
        }

    def update(self, instance, validated_data):
        instance.full_name = validated_data.get('full_name', instance.full_name)
        instance.email = validated_data.get('email', instance.email)
        instance.save()
        return instance


"""--------Register Serializer--------"""


class RegisterSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ['full_name', 'email', 'password']
        extra_kwargs = {
            'password': {'write_only': True},
        }
    
    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        user.is_active = False
        user.save()
        otp = generate_otp()
        Profile.objects.create(user=user , otp =otp)

        # Send email with OTP
        subject = 'Your OTP Code - Email Verification Your Account'
        html_content = render_to_string(
            'send_email.html', {'otp': otp , 'user': user}
        )
        # send_email(user.email, subject, message)
        try:
            msg = EmailMessage(
                subject= subject,
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
            raise serializers.ValidationError({"confirm_password": "New password and confirm password do not match."})
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

