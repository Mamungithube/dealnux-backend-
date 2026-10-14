from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import display

from ..models import Coupon


@admin.register(Coupon)
class CouponAdmin(ModelAdmin):
    compressed_fields = True
    list_fullwidth = True

    list_display = [
        'display_seller',
        'display_code',
        'display_discount',
        'used_count',
        'max_uses',
        'display_valid',
        'is_active',
        'expires_at',
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('seller')

    list_filter = ['discount_type', 'is_active', 'created_at']
    search_fields = ['code', 'seller__shop_name']
    readonly_fields = [
        'seller', 'code', 'discount_type', 'discount_value',
        'min_order_amount', 'created_at',
        'display_seller',
        'display_code',
        'display_discount',
        'used_count',
        'max_uses',
        'display_valid',
        'is_active',
        'expires_at',
    ]

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    fieldsets = (
        (_('🎟️ Coupon Info'), {
            'fields': ('seller', 'code', 'discount_type', 'discount_value'),
        }),
        (_('📋 Usage Limits'), {
            'fields': ('min_order_amount', 'max_uses', 'used_count'),
        }),
        (_('⚙️ Status'), {
            'fields': ('is_active', 'expires_at'),
        }),
    )

    @display(description=_('Code'), ordering='code')
    def display_code(self, obj):
        return format_html(
            '<code style="background:#000000;padding:3px 8px;'
            'border-radius:4px;font-weight:600;letter-spacing:1px">{}</code>',
            obj.code,
        )

    @display(description=_('Shop'), ordering='seller__shop_name')
    def display_seller(self, obj):
        return obj.seller.shop_name

    @display(description=_('Discount'), ordering='discount_value')
    def display_discount(self, obj):
        if obj.discount_type == 'PERCENTAGE':
            return format_html(
                '<strong style="color:#7c3aed">{}%</strong> off',
                obj.discount_value,
            )
        return format_html(
            '<strong style="color:#16a34a">${}</strong> off',
            obj.discount_value,
        )

    @display(description=_('Valid'), boolean=True, ordering='is_active')
    def display_valid(self, obj):
        return obj.is_valid
