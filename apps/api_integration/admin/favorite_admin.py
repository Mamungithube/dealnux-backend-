from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display
from django.utils.html import format_html
from django.urls import reverse

from ..models import Favorite


@admin.register(Favorite)
class FavoriteAdmin(ModelAdmin):
    list_display = ['user_email', 'product_title', 'product_image', 'product_price', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__email', 'product__title']
    readonly_fields = ['user', 'product', 'created_at', 'product_preview']
    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'user',
            'product',
        )

    fieldsets = (
        ('User Info', {
            'fields': ('user',)
        }),
        ('Product Info', {
            'fields': ('product', 'product_preview')
        }),
        ('Timestamps', {
            'fields': ('created_at',)
        }),
    )

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    @display(description='User')
    def user_email(self, obj):
        return format_html(
            '<span style="color: #2196F3; font-weight: bold;">👤 {}</span>',
            obj.user.email
        )

    @display(description='Product')
    def product_title(self, obj):
        url = reverse('admin:api_integration_product_change', args=[obj.product.pk])
        return format_html(
            '<a href="{}" style="color: #FF5722;">{}</a>',
            url, obj.product.title[:60]
        )

    @display(description='Image')
    def product_image(self, obj):
        if obj.product.main_image:
            return format_html(
                '<img src="{}" style="max-height: 45px; border-radius: 5px;" />',
                obj.product.main_image
            )
        return format_html('<span style="color: gray;">No Image</span>')

    @display(description='Price')
    def product_price(self, obj):
        price = obj.product.get_lowest_price()
        if price:
            return format_html(
                '<span style="color: green; font-weight: bold;">${}</span>', price
            )
        return format_html('<span style="color: gray;">N/A</span>')

    @display(description='Preview')
    def product_preview(self, obj):
        if obj.product.main_image:
            return format_html(
                '<img src="{}" style="max-height: 200px; border-radius: 10px;" />',
                obj.product.main_image
            )
        return 'No image'
