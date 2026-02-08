from rest_framework import serializers
from account.models import Profile ,User
from django.contrib.auth import get_user_model , password_validation
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
import json
from django.db import transaction

User = get_user_model()

import random

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
        
        # ✅ OTP সরাসরি User মডেলে সেভ করুন
        otp = generate_otp()
        user.otp = otp  
        user.save()

        # ❌ Profile তৈরি করবেন না এখানে
        # Profile.objects.create(user=user, otp=otp)  # এটা মুছে দিন

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
    name = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    refaradal_code = serializers.SerializerMethodField()
    interests = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = ['name', 'email', 'profile_picture', 'address', 'interests', 'refaradal_code']

    def get_name(self, obj):
        return getattr(obj.user, 'name', '') if obj.user else ''

    def get_email(self, obj):
        return getattr(obj.user, 'email', '') if obj.user else ''

    def get_refaradal_code(self, obj):
        return getattr(obj.user, 'refarral_code', '') if obj.user else ''

    def get_interests(self, obj):
        # ডাটাবেস থেকে স্ট্রিং এনে লিস্টে রূপান্তর করে ফ্রন্টএন্ডে পাঠানো
        if obj.interests:
            try:
                return json.loads(obj.interests)
            except (ValueError, TypeError):
                return []
        return []



class ProfileSetupSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)  # ✅ Email দিয়ে user identify করবে
    address = serializers.CharField(required=False, allow_blank=True)
    interests = serializers.ListField(
        child=serializers.CharField(), 
        required=False,
        allow_empty=True
    )
    profile_picture = serializers.ImageField(required=False, allow_null=True)
    referred_by_code = serializers.CharField(
        required=False, 
        allow_blank=True, 
        allow_null=True
    )

# ==================== Profile Update Serializer (Write) ====================
class ProfileUpdateSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='user.name', required=True)
    referred_by_code = serializers.CharField(write_only=True, required=False, allow_null=True)
    interests = serializers.ListField(child=serializers.CharField(), required=False)

    class Meta:
        model = Profile
        fields = ['name', 'profile_picture', 'address', 'interests', 'referred_by_code']

    def update(self, instance, validated_data):
        referred_by_code = validated_data.pop('referred_by_code', None)
        user = instance.user

        # ১. রেফারাল লজিক
        if referred_by_code:
            try:
                # যার কোড ব্যবহার করা হচ্ছে তাকে খোঁজা
                referrer = User.objects.get(referral_code=referred_by_code)
                
                # নিজের কোড নিজে ব্যবহার করা যাবে না
                if referrer == user:
                    raise serializers.ValidationError({"referred_by_code": "You cannot use your own referral code."})
                
                # এক ইউজার একবারই রেফারাল বোনাস পাবে (যদি আগে ব্যালেন্স ০ থাকে বা নির্দিষ্ট কোনো চেক)
                # এখানে একটি flag ব্যবহার করা ভালো (যেমন: is_referred = BooleanField) যাতে বারবার বোনাস না নেয়
                
                with transaction.atomic():
                    referrer.balance += 10
                    referrer.save()
                    
                    user.balance += 10
                    user.save()
            except User.DoesNotExist:
                raise serializers.ValidationError({"referred_by_code": "Invalid referral code."})

        # ২. বাকি আপডেট লজিক (আপনার আগের কোড অনুযায়ী)
        user_data = validated_data.pop('user', {})
        if user_data:
            user.name = user_data.get('name', user.name)
            user.save()

        interests_list = validated_data.pop('interests', None)
        if interests_list is not None:
            instance.interests = json.dumps(interests_list)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
            
        instance.save()
        return instance