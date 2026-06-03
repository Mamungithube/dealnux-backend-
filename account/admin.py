from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display
from django.utils.html import format_html
from .models import User, Profile
from django.contrib.auth.models import Group
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

# [FIX] আগে চেক করে আন-রেজিস্টার করা যাতে AlreadyRegistered এরর না আসে
if admin.site.is_registered(User):
    admin.site.unregister(User)

if admin.site.is_registered(Group):
    admin.site.unregister(Group)

if admin.site.is_registered(OutstandingToken):
    admin.site.unregister(OutstandingToken)

if admin.site.is_registered(BlacklistedToken):
    admin.site.unregister(BlacklistedToken)


@admin.register(User)
class UserAdmin(ModelAdmin):
    list_display = (
        'email', 'name', 'display_buyer_activity', 'is_active', 
        'date_joined', 'balance', 'referral_code'
    )
    search_fields = ('email', 'name', 'referral_code')
    list_filter = ('is_active', 'ads_provided', 'has_claimed_referral')
    ordering = ('-date_joined',)
    
    # Unfold specific
    list_filter_submit = True 
    list_fullwidth = True 

    # [Client Requirement] Buyer Activity Tracking (Alerts/Favorites)
    @display(description='Buyer Metrics (Alerts/Favs)', label=True)
    def display_buyer_activity(self, obj):
        # আপনার মডেল রিলেশন অনুযায়ী কাউন্ট
        alerts_count = obj.price_alerts.count() if hasattr(obj, 'price_alerts') else 0
        favs_count = obj.favorites.count() if hasattr(obj, 'favorites') else 0
        
        return format_html(
            '<span title="Price Alerts">🔔 {}</span> &nbsp; | &nbsp; <span title="Saved Deals">⭐ {}</span>',
            alerts_count, favs_count
        )

@admin.register(Profile)
class ProfileAdmin(ModelAdmin):
    list_display = ('user', 'display_profile_picture', 'address')
    readonly_fields = ('display_profile_picture',)

    @display(description='Profile Picture')
    def display_profile_picture(self, obj):
        if obj.profile_picture:
            return format_html('<img src="{}" style="width: 40px; height: 40px; border-radius: 50%;" />', obj.profile_picture.url)
        return "No Image"