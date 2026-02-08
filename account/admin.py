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

class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user',     'address')
    search_fields = ('user__email', 'user__name')
    ordering = ('user__email',)

admin.site.register(User, UserAdmin)
admin.site.register(Profile, ProfileAdmin)