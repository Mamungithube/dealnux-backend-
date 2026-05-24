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

from .models import (
    Privacy_Policy, Cookie_Policy, Terms_Of_Service, Review,
    EMI_Payment_Policy, Warranty_Policy, Exchange_Policy,
    Delivery_Policy, PreOrder_Policy, Refund_Policy, Return_Policy
)

class EMIPaymentPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model  = EMI_Payment_Policy
        fields = ['id', 'content', 'created_at', 'last_updated']

class WarrantyPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model  = Warranty_Policy
        fields = ['id', 'content', 'created_at', 'last_updated']

class ExchangePolicySerializer(serializers.ModelSerializer):
    class Meta:
        model  = Exchange_Policy
        fields = ['id', 'content', 'created_at', 'last_updated']

class DeliveryPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model  = Delivery_Policy
        fields = ['id', 'content', 'created_at', 'last_updated']

class PreOrderPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model  = PreOrder_Policy
        fields = ['id', 'content', 'created_at', 'last_updated']

class RefundPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model  = Refund_Policy
        fields = ['id', 'content', 'created_at', 'last_updated']

class ReturnPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model  = Return_Policy
        fields = ['id', 'content', 'created_at', 'last_updated']


class ReviewSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'user_email', 'rating', 'comment', 'created_at']
        read_only_fields = ['user', 'created_at']