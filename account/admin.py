from django.contrib import admin

# Register your models here.

from .models import User,Profile


class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'Fullname', 'is_staff', 'is_active')
    search_fields = ('email', 'Fullname')
    ordering = ('email',)

class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'otp', 'address')
    search_fields = ('user__email', 'user__Fullname')
    ordering = ('user__email',)

admin.site.register(User, UserAdmin)
admin.site.register(Profile, ProfileAdmin)