from django.shortcuts import render
# Create your views here.
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from policy.models import Privacy_Policy, Cookie_Policy, Terms_Of_Service
from policy.serializers import PrivacyPolicySerializer, CookiePolicySerializer, TermsOfServiceSerializer

class PrivacyPolicyView(APIView):
    def get(self, request, format=None):
        privacy_policy = Privacy_Policy.objects.first()
        serializer = PrivacyPolicySerializer(privacy_policy)
        return Response(serializer.data)
    
    def post(self, request, format=None):
        serializer = PrivacyPolicySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def update(self, request, format=None):
        privacy_policy = Privacy_Policy.objects.first()
        serializer = PrivacyPolicySerializer(privacy_policy, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, format=None):
        privacy_policy = Privacy_Policy.objects.first()
        if privacy_policy:
            privacy_policy.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    

class CookiePolicyView(APIView):
    def get(self, request, format=None):
        cookie_policy = Cookie_Policy.objects.first()
        serializer = CookiePolicySerializer(cookie_policy)
        return Response(serializer.data)
    
    def post(self, request, format=None):
        serializer = CookiePolicySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, format=None):
        cookie_policy = Cookie_Policy.objects.first()
        serializer = CookiePolicySerializer(cookie_policy, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, format=None):
        cookie_policy = Cookie_Policy.objects.first()
        if cookie_policy:
            cookie_policy.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    

class TermsOfServiceView(APIView):
    def get(self, request, format=None):
        terms_of_service = Terms_Of_Service.objects.first()
        serializer = TermsOfServiceSerializer(terms_of_service)
        return Response(serializer.data)
    
    def post(self, request, format=None):
        serializer = TermsOfServiceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def update(self, request, format=None):
        terms_of_service = Terms_Of_Service.objects.first()
        serializer = TermsOfServiceSerializer(terms_of_service, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, format=None):
        terms_of_service = Terms_Of_Service.objects.first()
        if terms_of_service:
            terms_of_service.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    

    
