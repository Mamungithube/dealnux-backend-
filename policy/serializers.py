from rest_framework import serializers
from .models import Privacy_Policy, Cookie_Policy, Terms_Of_Service , Review

class PrivacyPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = Privacy_Policy
        fields = ['id', 'content', 'created_at', 'last_updated']

class CookiePolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = Cookie_Policy
        fields =['id', 'content', 'created_at', 'last_updated']

class TermsOfServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Terms_Of_Service
        fields =['id', 'content', 'created_at', 'last_updated']


class ReviewSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'user_email', 'rating', 'comment', 'created_at']
        read_only_fields = ['user', 'created_at']