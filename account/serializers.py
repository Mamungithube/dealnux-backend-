from rest_framework import serializers
from account.models import Profile ,User
from django.contrib.auth import get_user_model , password_validation
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.conf import settings
from django.http import HttpResponse
from django.core.exceptions import ValidationError

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
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['full_name', 'email', 'password',
                  'confirm_password', 'address', 'interests', 'profile_picture']
        extra_kwargs = {
            'password': {'write_only': True},
        }

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError(
                "Password and Confirm Password do not match")
        password_validation.validate_password(data['password'])
        
        return data
    
    def create(self, validated_data):
        validated_data.pop('confirm_password')
        user = User.objects.create_user(**validated_data)
        user.is_active = False
        user.save()
        otp = generate_otp()
        Profile.object.create(user=user , otp =otp)

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
