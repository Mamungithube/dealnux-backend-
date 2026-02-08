from django.contrib import admin

# Register your models here.

from .models import User,Profile


class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'name', 'ads_provided', 'is_staff', 'is_active')
    list_editable = ('ads_provided',)
    search_fields = ('email', 'name')
    ordering = ('email',)

class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'otp', 'address')
    search_fields = ('user__email', 'user__name')
    ordering = ('user__email',)

admin.site.register(User, UserAdmin)
admin.site.register(Profile, ProfileAdmin)