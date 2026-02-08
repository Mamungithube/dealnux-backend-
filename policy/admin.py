from django.contrib import admin

# Register your models here.

from .models import Privacy_Policy, Terms_Of_Service, Cookie_Policy

admin.site.register(Privacy_Policy)
class TermsOfServiceAdmin(admin.ModelAdmin):
    list_display = ('last_updated', 'created_at')
    ordering = ('-last_updated',)
    search_fields = ('last_updated', 'created_at')
    readonly_fields = ('last_updated', 'created_at')


admin.site.register(Terms_Of_Service)
class CookiePolicyAdmin(admin.ModelAdmin):
    list_display = ('last_updated', 'created_at')
    ordering = ('-last_updated',)
    search_fields = ('last_updated', 'created_at')
    readonly_fields = ('last_updated', 'created_at')


admin.site.register(Cookie_Policy)
class PrivacyPolicyAdmin(admin.ModelAdmin):
    list_display = ('last_updated', 'created_at')
    ordering = ('-last_updated',)
    search_fields = ('last_updated', 'created_at')
    readonly_fields = ('last_updated', 'created_at')