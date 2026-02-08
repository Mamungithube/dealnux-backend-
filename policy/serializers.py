from rest_framework import serializers

class PrivacyPolicySerializer(serializers.Serializer):
    content = serializers.CharField()
    created_at = serializers.DateTimeField()
    last_updated = serializers.DateTimeField()

class CookiePolicySerializer(serializers.Serializer):
    content = serializers.CharField()
    created_at = serializers.DateTimeField()
    last_updated = serializers.DateTimeField()

class TermsOfServiceSerializer(serializers.Serializer):
    content = serializers.CharField()
    created_at = serializers.DateTimeField()
    last_updated = serializers.DateTimeField()