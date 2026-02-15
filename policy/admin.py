from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Privacy_Policy, Terms_Of_Service, Cookie_Policy


@admin.register(Privacy_Policy)
class PrivacyPolicyAdmin(ModelAdmin):
    list_display = ('last_updated', 'created_at')
    ordering = ('-last_updated',)
    search_fields = ('last_updated', 'created_at')
    readonly_fields = ('last_updated', 'created_at')
    
    # Unfold specific
    list_filter_submit = True


@admin.register(Terms_Of_Service)
class TermsOfServiceAdmin(ModelAdmin):
    list_display = ('last_updated', 'created_at')
    ordering = ('-last_updated',)
    search_fields = ('last_updated', 'created_at')
    readonly_fields = ('last_updated', 'created_at')
    
    # Unfold specific
    list_filter_submit = True


@admin.register(Cookie_Policy)
class CookiePolicyAdmin(ModelAdmin):
    list_display = ('last_updated', 'created_at')
    ordering = ('-last_updated',)
    search_fields = ('last_updated', 'created_at')
    readonly_fields = ('last_updated', 'created_at')
    
    # Unfold specific
    list_filter_submit = True