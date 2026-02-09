from django.contrib import admin

# Register your models here.

from .models import User,Profile


class UserAdmin(admin.ModelAdmin):
    list_display = ('email','otp', 'name', 'ads_provided', 'is_active', 
                    'date_joined', 'referral_code', 'balance', 
                    'has_claimed_referral' , 'referred_by')
    list_editable = ('ads_provided',)
    search_fields = ('email', 'name', 'referral_code')
    list_filter = ('has_claimed_referral', 'is_active', 'ads_provided')
    ordering = ('email',)
    readonly_fields = ('referral_code', 'has_claimed_referral')

from django.utils.html import format_html

class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'address', 'display_profile_picture')
    search_fields = ('user__email', 'user__name')
    ordering = ('user__email',)

    def display_profile_picture(self, obj):
        if obj.profile_picture:
            return format_html('<img src="{}" style="width: 50px; height: 50px; border-radius: 50%;" />', obj.profile_picture.url)
        return "No Image"

    display_profile_picture.short_description = 'Profile Picture'

admin.site.register(User, UserAdmin)
admin.site.register(Profile, ProfileAdmin)