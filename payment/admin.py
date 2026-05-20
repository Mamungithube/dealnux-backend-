from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone

from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display, action
from unfold.contrib.filters.admin import RangeDateFilter

from .models import Payment, SellerPayout, SubscriptionPlan, UserSubscription


# ============================================================================
# Payment Admin
# ============================================================================

@admin.register(Payment)
class PaymentAdmin(ModelAdmin):
    compressed_fields   = True
    warn_unsaved_form   = True
    list_fullwidth      = True
    list_filter_submit  = True

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


# ============================================================================
# SellerPayout Admin
# ============================================================================

@admin.register(SellerPayout)
class SellerPayoutAdmin(ModelAdmin):
    compressed_fields   = True
    list_fullwidth      = True
    list_filter_submit  = True

    list_display = [
        'display_seller',
        'display_amounts',
        'id',
        'display_status',
        'display_transfer',
        'created_at',
    ]

    list_filter = [
        'status',
        ('created_at', RangeDateFilter),
    ]

    search_fields = [
        'seller__shop_name',
        'seller__user__email',
        'stripe_transfer_id',
        'stripe_account_id',
    ]

    readonly_fields = [
        'gross_amount',
        'platform_fee_amount',
        'seller_amount',
        'stripe_transfer_id',
        'stripe_payout_id',
        'created_at',
        'updated_at',
    ]

    fieldsets = (
        ('Seller', {
            'fields': ('seller', 'stripe_account_id'),
        }),
        ('Order & Payment', {
            'fields': ('payment', 'order'),
        }),
        ('Amounts', {
            'fields': (
                'gross_amount',
                'platform_fee_percent', 'platform_fee_amount',
                'seller_amount',
            ),
        }),
        ('Stripe Transfer', {
            'fields': ('stripe_transfer_id', 'stripe_payout_id'),
        }),
        ('Status', {
            'fields': ('status', 'failure_reason'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
        }),
    )

    @display(description='Seller')
    def display_seller(self, obj):
        return format_html(
            '<span style="font-weight:500">{}</span><br>'
            '<small style="color:#888">{}</small>',
            obj.seller.shop_name,
            obj.seller.user.email,
        )

    @display(description='Amounts')
    def display_amounts(self, obj):
        return format_html(
            '<span style="font-weight:600;color:#10b981">{}</span>'
            '<br><small style="color:#888">Fee: {} ({}%)</small>',
            obj.seller_amount,
            obj.platform_fee_amount,
            obj.platform_fee_percent,
        )

    @display(description='Status')
    def display_status(self, obj):
        colors = {
            'PENDING':    '#f59e0b',
            'PROCESSING': '#3b82f6',
            'COMPLETED':  '#10b981',
            'FAILED':     '#ef4444',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:3px 10px;border-radius:999px;font-size:11px;font-weight:600">{}</span>',
            color, obj.status
        )

    @display(description='Transfer ID')
    def display_transfer(self, obj):
        if obj.stripe_transfer_id:
            return format_html('<code style="font-size:11px">{}</code>', obj.stripe_transfer_id)
        if obj.failure_reason:
            return format_html('<span style="color:#ef4444;font-size:11px">{}</span>', obj.failure_reason[:50])
        return '—'


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(ModelAdmin):
    list_display = [
        'name', 
        'display_price', 
        'plan_type', 
        'display_trial_days', 
        'display_limits', 
        'is_active'
    ]
    list_filter = ['plan_type', 'is_active']
    search_fields = ['name', 'stripe_price_id']
    
    fieldsets = (
        ('General Information', {
            'fields': ('name', 'plan_type', 'price', 'is_active')
        }),
        ('Trial & Limits', {
            'fields': ('trial_days', 'clicks_per_day', 'price_alerts_limit')
        }),
        ('Stripe Integration', {
            'fields': ('stripe_price_id',),
            'description': 'Stripe ড্যাশবোর্ড থেকে Price ID কপি করে এখানে দিন।'
        }),
    )

    @display(description='Price', ordering='price')
    def display_price(self, obj):
        if obj.price == 0:
            return format_html('<span style="color: #10b981; font-weight: bold;">FREE</span>')
        return f"${obj.price}"

    @display(description='Trial Period')
    def display_trial_days(self, obj):
        return f"{obj.trial_days} Days"

    @display(description='Daily Clicks / Alerts')
    def display_limits(self, obj):
        alerts = "∞" if obj.price_alerts_limit == -1 else obj.price_alerts_limit
        return format_html(
            'Clicks: <b>{}</b> | Alerts: <b>{}</b>',
            obj.clicks_per_day, alerts
        )


@admin.register(UserSubscription)
class UserSubscriptionAdmin(ModelAdmin):
    list_display = [
        'display_user', 
        'display_plan', 
        'display_status', 
        'display_time_left', 
        'expires_at'
    ]
    list_filter = ['status', 'plan']
    search_fields = ['user__email', 'stripe_subscription_id']
    readonly_fields = ['trial_started_at', 'expires_at'] # নিরাপত্তা নিশ্চিত করতে রিড-অনলি

    @display(description='User', ordering='user__email')
    def display_user(self, obj):
        return format_html(
            '<div><b>{}</b><br><small style="color: #6b7280;">{}</small></div>',
            obj.user.name, obj.user.email
        )

    @display(description='Active Plan', label=True)
    def display_plan(self, obj):
        return obj.plan.name

    @display(description='Status', label={
        'ACTIVE': 'success',
        'TRIAL': 'warning',
        'EXPIRED': 'danger',
        'CANCELLED': 'info',
    })
    def display_status(self, obj):
        return obj.status

    @display(description='Time Remaining')
    def display_time_left(self, obj):
        if not obj.is_active:
            return format_html('<span style="color: #ef4444;">Expired</span>')
        
        diff = obj.expires_at - timezone.now()
        days = diff.days
        
        if days > 0:
            color = "#10b981" if days > 3 else "#f59e0b"
            return format_html(
                '<span style="color: {}; font-weight: bold;">{} Days left</span>',
                color, days
            )
        return "Ending Today"