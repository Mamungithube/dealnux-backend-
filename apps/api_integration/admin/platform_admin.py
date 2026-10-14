from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display
from django.utils.html import format_html

from ..models import Platform, Category


@admin.register(Platform)
class PlatformAdmin(ModelAdmin):
    list_display = ['name', 'code', 'api_enabled', 'api_usage_status', 'listings_count', 'created_at']
    list_filter = ['api_enabled', 'created_at']
    search_fields = ['name', 'code']
    readonly_fields = ['name', 'code', 'api_enabled', 'created_at', 'updated_at']

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions
    
    @display(description='API Usage & Cost', label={
        "High Usage": "danger",
        "Optimal": "success",
        "Low": "info",
    })
    def api_usage_status(self, obj):
        count = obj.listings.count()
        if count > 5000: return "High Usage"
        if count > 1000: return "Optimal"
        return "Low"

    @display(description='Active Listings')
    def listings_count(self, obj):
        count = obj.listings.filter(is_available=True).count()
        return format_html('<span style="color: green; font-weight: bold;">{}</span>', count)
    
    @display(description='API Usage & Cost')
    def display_api_usage(self, obj):
        usage = 65 
        color = "green" if usage < 80 else "red"
        return format_html(
            '<div style="width:100px; background:#eee; border-radius:4px;">'
            '<div style="width:{}px; background:{}; height:10px; border-radius:4px;"></div>'
            '</div><small>{}% Calls Used</small>', usage, color, usage
        )


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ['name', 'slug', 'parent', 'products_count', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'slug']
    readonly_fields = ['name', 'slug', 'parent', 'created_at', 'updated_at']

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    @display(description='Products')
    def products_count(self, obj):
        return obj.products.count()
