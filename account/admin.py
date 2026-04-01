from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display
from django.utils.html import format_html
from .models import User, Profile
from django.contrib.auth.models import Group
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

"""=========================unregister Models from admin========================="""


if admin.site.is_registered(OutstandingToken):
    admin.site.unregister(OutstandingToken)
if admin.site.is_registered(BlacklistedToken):
    admin.site.unregister(BlacklistedToken)
admin.site.unregister(Group)


"""=========================Register Models to admin========================="""

@admin.register(User)
class UserAdmin(ModelAdmin):
    list_display = (
        'email', 'otp', 'name', 'ads_provided', 'is_active',
        'date_joined', 'referral_code', 'balance',
        'has_claimed_referral', 'referred_by'
    )
    # list_editable = ('ads_provided',) 
    search_fields = ('email', 'name', 'referral_code')
    list_filter = ('has_claimed_referral', 'is_active', 'ads_provided')
    ordering = ('email',)
    # readonly_fields = ('email',  'referral_code', 'has_claimed_referral', 'balance', 
    #                    'referred_by', 'ads_provided', 'is_active', 'otp', 
    #                    'profile_setup_completed', 'date_joined','last_login', 'is_superuser', 
    #                    'first_name', 'last_name', 'is_staff', 'is_active', 'date_joined', 
    #                    'profile_setup_completed','groups', 'user_permissions','password','name',
    #                    'address' , 'savings_comparison', 'savings_coupons', 'total_lifetime_savings')
    
    # Unfold specific configurations
    list_filter_submit = True 
    list_fullwidth = True 


@admin.register(Profile)
class ProfileAdmin(ModelAdmin):
    list_display = ('user', 'display_profile_picture', 'address', 'interests', 'profile_picture')
    search_fields = ('user__email', 'user__name')
    ordering = ('user__email',)
    readonly_fields = ('user', 'display_profile_picture', 'address', 'interests', 'profile_picture')
    
    # Unfold specific
    list_filter_submit = True

    @display(description='Profile Picture')
    def display_profile_picture(self, obj):
        if obj.profile_picture:
            return format_html(
                '<img src="{}" style="width: 50px; height: 50px; border-radius: 50%; object-fit: cover;" />',
                obj.profile_picture.url
            )
        return "No Image"