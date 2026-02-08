# ads/permissions.py (নতুন ফাইল)
from rest_framework import permissions

class IsAdminUser(permissions.BasePermission):
    """Only admin/staff users can access"""
    def has_permission(self, request, view):
        return request.user and request.user.is_staff


class IsAdvertiserOwner(permissions.BasePermission):
    """Only ad owner can edit their own ads"""
    def has_object_permission(self, request, view, obj):
        return obj.advertiser == request.user


class IsApprovedAdvertiser(permissions.BasePermission):
    """Only approved advertisers can create ads"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.ads_provided