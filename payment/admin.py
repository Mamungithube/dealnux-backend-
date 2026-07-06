from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.db.models import Sum
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display, action
from unfold.contrib.filters.admin import RangeDateFilter
from django.contrib import messages
from django.http import HttpResponseRedirect
from .models import Payment, SellerPayout, SubscriptionPlan, UserSubscription
from account.utils.admin_permissions import ManagerOnlyMixin, AdminReadOnlyFinancialMixin
from django.utils.translation import gettext_lazy as _
from unfold.enums import ActionVariant
# ============================================================================
# Payment Admin
# ============================================================================

@admin.register(Payment)
class PaymentAdmin(AdminReadOnlyFinancialMixin, ModelAdmin):
    compressed_fields   = True
    warn_unsaved_form   = True
    list_fullwidth      = True
    list_filter_submit  = True

    def changelist_view(self, request, extra_context=None):
        # In English: Redirect Admin_Associate to dashboard with an error message instead of 403 page
        if not request.user.is_superuser and request.user.groups.filter(name='Admin_Associate').exists():
            messages.error(request, "Permission Denied: Financial records are restricted to Managers only.")
            return HttpResponseRedirect("/admin/") # Redirect to main dashboard
        return super().changelist_view(request, extra_context)
    
    def has_module_permission(self, request):
        # শুধু সুপারইউজার বা ম্যানেজার গ্রুপ পেমেন্ট দেখতে পারবে
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


# ============================================================================
# SellerPayout Admin
# ============================================================================

@admin.register(SellerPayout)
class SellerPayoutAdmin(ManagerOnlyMixin, ModelAdmin):
    
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

    def has_module_permission(self, request):
        return request.user.is_superuser or request.user.groups.filter(name='Manager').exists()
    
    def has_change_permission(self, request, obj=None):
        # এসোসিয়েট এডিট বা এপ্রুভ করতে পারবে না
        if request.user.groups.filter(name='Admin_Associate').exists():
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        # এসোসিয়েট ডিলিটও করতে পারবে না
        if request.user.groups.filter(name='Admin_Associate').exists():
            return False
        return super().has_delete_permission(request, obj)

    # --- গুরুত্বপূর্ণ: আপনার Approve/Reject একশনেও এটি চেক করতে হবে ---
    @action(description=_('Approve'), url_path='approve-request', icon='check_circle', variant=ActionVariant.SUCCESS)
    def action_approve_row(self, request, object_id):
        # যদি ইউজার এসোসিয়েট হয়, তাকে এরর মেসেজ দিন
        if request.user.groups.filter(name='Admin_Associate').exists():
            self.message_user(request, "Permission Denied: Admin Associates cannot approve sellers.", level='error')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../..'))

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
class SubscriptionPlanAdmin(ManagerOnlyMixin, ModelAdmin):
    list_display = [
        'id',
        'name',
        'display_price',
        'plan_type',
        'display_trial_days',
        'display_limits',
        'display_features',
        'is_active'
    ]
    list_filter = ['plan_type', 'is_active']
    search_fields = ['name', 'stripe_price_id']
    readonly_fields = ['stripe_price_id']

    fieldsets = (
        ('General Information', {
            'fields': ('name', 'plan_type', 'price', 'is_active')
        }),
        ('Features', {
            'fields': ('features',),
            'description': 'Add features as a JSON array, for example: ["Unlimited searches", "Priority support"]'
        }),
        ('Trial & Limits', {
            'fields': ('trial_days', 'clicks_per_day', 'price_alerts_limit')
        }),
        ('Stripe Integration', {
            'fields': ('stripe_price_id',),
            'description': 'Copy the Price ID from the Stripe dashboard and paste it here.'
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

    @display(description='Features')
    def display_features(self, obj):
        if not obj.features:
            return '—'
        return format_html('<span>{}</span>', ', '.join(obj.features[:5]))


@admin.register(UserSubscription)
class UserSubscriptionAdmin(AdminReadOnlyFinancialMixin, ModelAdmin):
    list_display = [
        'display_user', 
        'display_plan', 
        'display_status', 
        'display_time_left', 
        'expires_at'
    ]
    list_filter = ['status', 'plan']
    search_fields = ['user__email', 'stripe_subscription_id']
    readonly_fields = ['trial_started_at', 'expires_at'] 

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