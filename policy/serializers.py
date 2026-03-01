from rest_framework import serializers
from .models import Privacy_Policy, Cookie_Policy, Terms_Of_Service

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