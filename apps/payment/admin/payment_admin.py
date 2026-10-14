from account.utils.admin_permissions import AdminReadOnlyFinancialMixin
from django.contrib import admin, messages
from django.db.models import Sum
from django.http import HttpResponseRedirect
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import RangeDateFilter
from unfold.decorators import display

from ..models import Payment


@admin.register(Payment)
class PaymentAdmin(AdminReadOnlyFinancialMixin, ModelAdmin):
    compressed_fields   = True
    warn_unsaved_form   = True
    list_fullwidth      = True
    list_filter_submit  = True

    def changelist_view(self, request, extra_context=None):
        if not request.user.is_superuser and request.user.groups.filter(name='Admin_Associate').exists():
            messages.error(request, "Permission Denied: Financial records are restricted to Managers only.")
            return HttpResponseRedirect("/admin/")
        return super().changelist_view(request, extra_context)
    
    def has_module_permission(self, request):
        return request.user.is_superuser or request.user.groups.filter(name='Manager').exists()

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        self.total_revenue = qs.filter(status='PAID').aggregate(Sum('final_amount'))['final_amount__sum'] or 0
        return qs

    list_display = [
        'display_buyer',
        'display_product',
        'id',
        'display_amount',
        'display_status',
        'display_stripe_session',
        'created_at',
    ]

    list_filter = [
        'status',
        'currency',
        ('created_at', RangeDateFilter),
    ]

    search_fields = [
        'buyer__email',
        'buyer__username',
        'seller_product__title',
        'stripe_checkout_session_id',
        'stripe_payment_intent_id',
    ]

    readonly_fields = [
        'buyer',
        'shipping_address',
        'note',
        'seller_product',
        'quantity',
        'coupon_code',
        'unit_price',
        'discount_amount',
        'currency',
        'status',
        'order',
        'stripe_checkout_session_id',
        'stripe_payment_intent_id',
        'stripe_checkout_url',
        'total_amount',
        'final_amount',
        'created_at',
        'updated_at',
    ]

    fieldsets = (
        ('Buyer Info', {
            'fields': ('buyer', 'shipping_address', 'note'),
        }),
        ('Product', {
            'fields': ('seller_product', 'quantity', 'coupon_code'),
        }),
        ('Amounts', {
            'fields': ('unit_price', 'total_amount', 'discount_amount', 'final_amount', 'currency'),
        }),
        ('Stripe', {
            'fields': (
                'stripe_checkout_session_id',
                'stripe_payment_intent_id',
                'stripe_checkout_url',
            ),
        }),
        ('Status', {
            'fields': ('status', 'order'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
        }),
    )

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions
    
    @display(description='Admin Fee', ordering='service_fee')
    def admin_fee_display(self, obj):
        return format_html('<b style="color: #10b981;">${}</b>', obj.service_fee)

    @display(description='Buyer', ordering='buyer__email')
    def display_buyer(self, obj):
        return format_html(
            '<span style="font-weight:500">{}</span>',
            obj.buyer.email
        )

    @display(description='Product')
    def display_product(self, obj):
        if obj.seller_product:
            return format_html(
                '{}<br><small style="color:#888">{}</small>',
                obj.seller_product.title,
                obj.seller_product.seller.shop_name,
            )
        return '—'

    @display(description='Amount')
    def display_amount(self, obj):
        if obj.discount_amount > 0:
            return format_html(
                '<span style="font-weight:600;color:#10b981">{} {}</span>'
                '<br><small style="color:#888;text-decoration:line-through">{}</small>'
                '<br><small style="color:#f59e0b">-{} discount</small>',
                obj.final_amount, obj.currency.upper(),
                obj.total_amount,
                obj.discount_amount,
            )
        return format_html(
            '<span style="font-weight:600">{} {}</span>',
            obj.final_amount, obj.currency.upper()
        )

    @display(description='Status')
    def display_status(self, obj):
        colors = {
            'PENDING':   '#f59e0b',
            'PAID':      '#10b981',
            'FAILED':    '#ef4444',
            'REFUNDED':  '#6366f1',
            'CANCELLED': '#6b7280',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:3px 10px;border-radius:999px;font-size:11px;font-weight:600">{}</span>',
            color, obj.status
        )

    @display(description='Stripe Session')
    def display_stripe_session(self, obj):
        if obj.stripe_checkout_session_id:
            short = obj.stripe_checkout_session_id[:20] + '...'
            return format_html('<code style="font-size:11px">{}</code>', short)
        return '—'
