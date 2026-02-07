from rest_framework import serializers
from account.models import Profile ,User
from django.contrib.auth import get_user_model , password_validation
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
import json

User = get_user_model()

import random

def generate_otp():
    return str(random.randint(1000, 9999))


"""--------User Serializer--------"""


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User 
        fields = ['id', 'Fullname', 'email', 'is_active', 'is_staff']
        extra_kwargs = {
            'Fullname': {'required': True},
            'email': {'required': True},
        }

    def update(self, instance, validated_data):
        instance.Fullname = validated_data.get('Fullname', instance.Fullname)
        instance.email = validated_data.get('email', instance.email)
        instance.save()
        return instance


"""--------Register Serializer--------"""


class RegisterSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ['Fullname', 'email', 'password']
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
            'send_code.html', {'otp': otp , 'user': user}
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



# ==================== Profile Serializer (Read-Only/Response) ====================
class ProfileSerializer(serializers.ModelSerializer):
    fullname = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    interests = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = ['fullname', 'email', 'profile_picture', 'address', 'interests']

    def get_fullname(self, obj):
        return getattr(obj.user, 'Fullname', '') if obj.user else ''

    def get_email(self, obj):
        return getattr(obj.user, 'email', '') if obj.user else ''

    def get_interests(self, obj):
        # ডাটাবেস থেকে স্ট্রিং এনে লিস্টে রূপান্তর করে ফ্রন্টএন্ডে পাঠানো
        if obj.interests:
            try:
                return json.loads(obj.interests)
            except (ValueError, TypeError):
                return []
        return []

# ==================== Profile Update Serializer (Write) ====================
class ProfileUpdateSerializer(serializers.ModelSerializer):
    fullname = serializers.CharField(source='user.Fullname', required=True)
    interests = serializers.ListField(
        child=serializers.CharField(), 
        required=False
    )

    class Meta:
        model = Profile
        fields = ['fullname', 'profile_picture', 'address', 'interests']

    def update(self, instance, validated_data):
        # ১. ইউজার ডাটা (Fullname) হ্যান্ডলিং
        user_data = validated_data.pop('user', {})
        if user_data and instance.user:
            fullname = user_data.get('Fullname')
            if fullname:
                instance.user.Fullname = fullname
                instance.user.save()
        
        # ২. Interests লিস্টকে JSON স্ট্রিং বানিয়ে ডাটাবেসে রাখা
        interests_list = validated_data.pop('interests', None)
        if interests_list is not None:
            instance.interests = json.dumps(interests_list)
        
        # ৩. বাকি সাধারণ ফিল্ডগুলো (address, profile_picture) আপডেট
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
            
        instance.save()
        return instance