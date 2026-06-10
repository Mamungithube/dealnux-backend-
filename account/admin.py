from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display
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


from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import action, display # <- এই ইম্পোর্টটা মিসিং ছিল
from unfold.enums import ActionVariant
from django.core.mail import send_mail # ইমেল পাঠানোর জন্য

class UserAdmin(ModelAdmin):
    list_display = ('email', 'name', 'is_active', 'balance', 'has_referral_reward_awarded')
    
    # [UPDATE] actions_row তে 'issue_referral_credit_manually' যোগ করা হয়েছে
    actions_row = [
        'suspend_user_row', 
        'reinstate_user_row', 
        'issue_referral_credit_manually', # নতুন বাটন
        'delete_user_permanent'
    ]

    # --- Manual Issue Referral Credit ---
    @action(
        description="Issue Referral Credit Manually", 
        url_path="issue-referral", 
        variant=ActionVariant.PRIMARY # বাটনটি নীল রঙের হবে
    )
    def issue_referral_credit_manually(self, request, object_id):
        from decimal import Decimal
        from django.db import transaction

        user = self.get_queryset(request).get(pk=object_id)

        if not user.referred_by:
            self.message_user(request, f"Error: User {user.email} was not referred by anyone.", level="error")
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/admin/'))

        if user.has_referral_reward_awarded:
            self.message_user(request, f"Notice: Referral credit already issued for {user.email}.", level="warning")
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/admin/'))

        try:
            with transaction.atomic():
                referrer = user.referred_by
                credit_amount = Decimal('10.00') 

                referrer.balance += credit_amount
                referrer.save(update_fields=['balance'])

                user.has_referral_reward_awarded = True
                user.save(update_fields=['has_referral_reward_awarded'])

                self.message_user(
                    request, 
                    f"Success! ${credit_amount} credit issued to {referrer.email} for referring {user.email}."
                )
        except Exception as e:
            self.message_user(request, f"Failed to issue credit: {str(e)}", level="error")
        
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/admin/'))

    # --- Suspend User ---
    @action(description="Suspend User", url_path="suspend", variant=ActionVariant.DANGER)
    def suspend_user_row(self, request, object_id):
        user = self.get_queryset(request).get(pk=object_id)
        user.is_active = False
        user.save()
        self.message_user(request, f"User {user.email} suspended.")
        
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/admin/'))

    @action(description="Reinstate User", url_path="reinstate", variant=ActionVariant.SUCCESS)
    def reinstate_user_row(self, request, object_id):
        user = self.get_queryset(request).get(pk=object_id)
        user.is_active = True
        user.save()
        self.message_user(request, f"User {user.email} reinstated.")
        
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/admin/'))

    @action(description="Delete Permanent", url_path="delete-permanent", variant=ActionVariant.DANGER)
    def delete_user_permanent(self, request, object_id):
        user = self.get_queryset(request).get(pk=object_id)
        user.delete()
        self.message_user(request, "User deleted permanently.")
        
        from django.urls import reverse
        return HttpResponseRedirect(reverse("admin:account_user_changelist"))

@admin.register(Profile)
class ProfileAdmin(ModelAdmin):
    list_display = ('user', 'display_profile_picture', 'address')
    readonly_fields = ('display_profile_picture',)

    @display(description='Profile Picture')
    def display_profile_picture(self, obj):
        if obj.profile_picture:
            return format_html('<img src="{}" style="width: 40px; height: 40px; border-radius: 50%;" />', obj.profile_picture.url)
        return "No Image"
    

