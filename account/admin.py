# account/admin.py
from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display
from unfold.enums import ActionVariant
from unfold.decorators import action
from django.utils.html import format_html
from .models import User, Profile
from django.contrib.auth.models import Group
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from django.http import HttpResponseRedirect

if admin.site.is_registered(User):
    admin.site.unregister(User)
if admin.site.is_registered(Group):
    admin.site.unregister(Group)
if admin.site.is_registered(OutstandingToken):
    admin.site.unregister(OutstandingToken)
if admin.site.is_registered(BlacklistedToken):
    admin.site.unregister(BlacklistedToken)


# ============================================================================
# Helper: Check roles
# ============================================================================
def is_manager(user):
    """Superuser = Manager — full access"""
    return user.is_superuser

def is_admin_only(user):
    """Staff + Admin group = Admin — limited access"""
    return user.is_staff and not user.is_superuser and user.groups.filter(name='Admin').exists()


# ============================================================================
# Group Admin — Manager only
# ============================================================================
@admin.register(Group)
class GroupAdmin(ModelAdmin):
    list_display = ['name', 'member_count']
    search_fields = ['name']

    def has_module_perms(self, request):
        return is_manager(request.user)

    def has_view_permission(self, request, obj=None):
        return is_manager(request.user)

    def has_add_permission(self, request):
        return is_manager(request.user)

    def has_change_permission(self, request, obj=None):
        return is_manager(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_manager(request.user)

    @display(description='Members')
    def member_count(self, obj):
        return obj.user_set.count()


# ============================================================================
# User Admin
# ============================================================================
@admin.register(User)
class UserAdmin(ModelAdmin):
    list_display = ('email', 'name', 'display_role', 'is_active', 'balance', 'has_referral_reward_awarded')
    search_fields = ('email', 'name')

    def get_fieldsets(self, request, obj=None):
        base = [
            ('Basic Info', {'fields': ('email', 'name', 'is_active')}),
            ('Roles & Permissions', {'fields': ('is_staff', 'groups')}),
        ]
        # Manager only: superuser toggle & financial fields
        if is_manager(request.user):
            base.append(('Manager Only', {'fields': ('is_superuser', 'balance', 'has_referral_reward_awarded', 'ads_provided')}))
        return base

    def get_readonly_fields(self, request, obj=None):
        # Admin (non-manager) cannot change financial or role-escalation fields
        if is_admin_only(request.user):
            return ('email', 'balance', 'is_superuser', 'ads_provided',
                    'has_referral_reward_awarded', 'referred_by', 'referral_code')
        return ('email',)

    actions_row = [
        'suspend_user_row',
        'reinstate_user_row',
        'grant_admin_access',       # Manager only
        'revoke_admin_access',      # Manager only
        'issue_referral_credit_manually',
        'delete_user_permanent',
    ]

    # --- Grant Admin Access (Manager only) ---
    @action(description="Grant Admin Access", url_path="grant-admin", variant=ActionVariant.SUCCESS)
    def grant_admin_access(self, request, object_id):
        if not is_manager(request.user):
            self.message_user(request, "Permission denied. Only managers can grant admin access.", level='error')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/admin/'))

        user = self.get_queryset(request).get(pk=object_id)
        admin_group, _ = Group.objects.get_or_create(name='Admin')
        user.is_staff = True
        user.groups.add(admin_group)
        user.save()
        self.message_user(request, f"✓ {user.email} granted Admin access.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/admin/'))

    # --- Revoke Admin Access (Manager only) ---
    @action(description="Revoke Admin Access", url_path="revoke-admin", variant=ActionVariant.DANGER)
    def revoke_admin_access(self, request, object_id):
        if not is_manager(request.user):
            self.message_user(request, "Permission denied.", level='error')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/admin/'))

        user = self.get_queryset(request).get(pk=object_id)
        admin_group = Group.objects.filter(name='Admin').first()
        if admin_group:
            user.groups.remove(admin_group)
        user.is_staff = False
        user.save()
        self.message_user(request, f"✓ {user.email} admin access revoked.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/admin/'))

    # --- Manual Referral Credit (Manager only) ---
    @action(description="Issue Referral Credit", url_path="issue-referral", variant=ActionVariant.PRIMARY)
    def issue_referral_credit_manually(self, request, object_id):
        if not is_manager(request.user):
            self.message_user(request, "Permission denied.", level='error')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/admin/'))

        from decimal import Decimal
        from django.db import transaction
        user = self.get_queryset(request).get(pk=object_id)
        if not user.referred_by:
            self.message_user(request, "Error: No referrer found.", level="error")
        elif user.has_referral_reward_awarded:
            self.message_user(request, "Notice: Already awarded.", level="warning")
        else:
            with transaction.atomic():
                user.referred_by.balance += Decimal('10.00')
                user.referred_by.save()
                user.has_referral_reward_awarded = True
                user.save()
                self.message_user(request, f"✓ Credit issued to {user.referred_by.email}")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/admin/'))

    # --- Suspend ---
    @action(description="Suspend User", url_path="suspend", variant=ActionVariant.DANGER)
    def suspend_user_row(self, request, object_id):
        user = self.get_queryset(request).get(pk=object_id)
        user.is_active = False
        user.save()
        self.message_user(request, f"User {user.email} suspended.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/admin/'))

    # --- Reinstate ---
    @action(description="Reinstate User", url_path="reinstate", variant=ActionVariant.SUCCESS)
    def reinstate_user_row(self, request, object_id):
        user = self.get_queryset(request).get(pk=object_id)
        user.is_active = True
        user.save()
        self.message_user(request, f"User {user.email} reinstated.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/admin/'))

    # --- Delete Permanent (Manager only) ---
    @action(description="Delete Permanent", url_path="delete-permanent", variant=ActionVariant.DANGER)
    def delete_user_permanent(self, request, object_id):
        if not is_manager(request.user):
            self.message_user(request, "Permission denied.", level='error')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/admin/'))

        user = self.get_queryset(request).get(pk=object_id)
        user.delete()
        self.message_user(request, "User deleted permanently.")
        from django.urls import reverse
        return HttpResponseRedirect(reverse("admin:account_user_changelist"))

    @display(description='Role', label={
        'Manager': 'success',
        'Admin': 'warning',
        'User': 'info',
    })
    def display_role(self, obj):
        if obj.is_superuser:
            return 'Manager'
        if obj.is_staff:
            return 'Admin'
        return 'User'


@admin.register(Profile)
class ProfileAdmin(ModelAdmin):
    list_display = ('user', 'display_profile_picture', 'address')
    readonly_fields = ('display_profile_picture',)

    @display(description='Profile Picture')
    def display_profile_picture(self, obj):
        if obj.profile_picture:
            return format_html(
                '<img src="{}" style="width: 40px; height: 40px; border-radius: 50%;" />',
                obj.profile_picture.url
            )
        return "No Image"