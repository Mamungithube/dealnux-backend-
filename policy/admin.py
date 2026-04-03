from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Privacy_Policy, Terms_Of_Service, Cookie_Policy , Review


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


@admin.register(Review)
class ReviewAdmin(ModelAdmin):
    list_display = ('user', 'rating','comment', 'created_at')
    ordering = ('-created_at',)
    search_fields = ('user__email', 'rating', 'created_at')
    list_filter = ('rating', 'created_at')
    readonly_fields = ('user', 'rating','comment', 'created_at')
    
    # Unfold specific
    list_filter_submit = True

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions