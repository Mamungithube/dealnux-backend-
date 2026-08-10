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
from django import forms
import json
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

    # --- Action to approve and send money via Stripe ---
    @action(description=_('Approve & Transfer'), url_path='approve-request', icon='check_circle', variant=ActionVariant.SUCCESS)
    def action_approve_row(self, request, object_id):
        if request.user.groups.filter(name='Admin_Associate').exists():
            self.message_user(request, "Permission Denied: Admin Associates cannot approve payouts.", level='error')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../..'))

        payout = self.get_object(request, object_id)
        if not payout:
            self.message_user(request, "Payout request not found.", level='error')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../..'))

        if payout.status == 'COMPLETED':
            self.message_user(request, "This payout is already completed.", level='warning')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../..'))

        seller = payout.seller
        if seller.stripe_account_id and seller.stripe_onboarding_completed:
            try:
                import stripe
                transfer = stripe.Transfer.create(
                    amount=int(payout.seller_amount * 100),
                    currency='usd',
                    destination=seller.stripe_account_id,
                    metadata={'payout_id': payout.id, 'seller_id': seller.id}
                )
                payout.stripe_transfer_id = transfer.id
                payout.status = 'COMPLETED'
                payout.save(update_fields=['stripe_transfer_id', 'status', 'updated_at'])
                self.message_user(request, f"Successfully transferred ${payout.seller_amount} via Stripe to {seller.shop_name}!", level='success')
            except Exception as e:
                payout.status = 'FAILED'
                payout.failure_reason = str(e)
                payout.save(update_fields=['status', 'failure_reason', 'updated_at'])
                self.message_user(request, f"Stripe Transfer Error: {str(e)}", level='error')
        else:
            payout.status = 'COMPLETED'
            payout.save(update_fields=['status', 'updated_at'])
            self.message_user(request, f"Approved payout of ${payout.seller_amount} for {seller.shop_name} (Manual payment / No Stripe Account).", level='info')

        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../..'))

    @action(description=_('Reject & Refund Balance'), url_path='reject-request', icon='cancel', variant=ActionVariant.DANGER)
    def action_reject_row(self, request, object_id):
        if request.user.groups.filter(name='Admin_Associate').exists():
            self.message_user(request, "Permission Denied: Admin Associates cannot reject payouts.", level='error')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../..'))

        payout = self.get_object(request, object_id)
        if not payout or payout.status in ['COMPLETED', 'FAILED']:
            self.message_user(request, "Payout cannot be rejected or is already processed.", level='warning')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../..'))

        seller = payout.seller
        seller.available_balance += payout.seller_amount
        seller.total_withdrawn -= payout.seller_amount
        seller.save(update_fields=['available_balance', 'total_withdrawn'])

        payout.status = 'FAILED'
        payout.failure_reason = 'Rejected by Admin'
        payout.save(update_fields=['status', 'failure_reason', 'updated_at'])

        self.message_user(request, f"Rejected payout request of ${payout.seller_amount}. Balance restored to seller.", level='info')
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


# ============================================================================
# SubscriptionPlan Form - Converts newline-separated features to/from JSON
# ============================================================================
class SubscriptionPlanForm(forms.ModelForm):
    """Custom form to handle features as newline-separated text instead of JSON."""
    features = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 6,
            'placeholder': 'Enter one feature per line:\n• Unlimited searches\n• Priority support\n• AI optimization',
            'style': 'font-family: monospace; width: 100%;'
        }),
        required=False,
        label='Features',
        help_text='Enter one feature per line (no JSON needed)'
    )

    class Meta:
        model = SubscriptionPlan
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.features:
            cleaned_list = self._flatten_features(self.instance.features)
            self.fields['features'].initial = '\n'.join(cleaned_list)

    def _flatten_features(self, data):
        if not data:
            return []
        import json, ast, re
        if isinstance(data, str):
            data = data.strip()
            if not data:
                return []
            if (data.startswith('[') and data.endswith(']')) or (data.startswith('{') and data.endswith('}')):
                try:
                    return self._flatten_features(json.loads(data))
                except Exception:
                    try:
                        return self._flatten_features(ast.literal_eval(data))
                    except Exception:
                        pass
            if '\n' in data:
                res = []
                for line in data.split('\n'):
                    res.extend(self._flatten_features(line))
                return res
            if ',' in data and ("'" in data or '"' in data):
                parts = re.findall(r"['\"]([^'\"]+)['\"]", data)
                if parts:
                    return [p.strip() for p in parts if p.strip()]
            cleaned = data.strip("'\"\\ ").strip()
            return [cleaned] if cleaned else []
        if isinstance(data, list):
            res = []
            for item in data:
                for f in self._flatten_features(item):
                    if f and f not in res:
                        res.append(f)
            return res
        return [str(data).strip()]

    def clean_features(self):
        features_text = self.cleaned_data.get('features', '')
        if not features_text.strip():
            return []
        return self._flatten_features(features_text)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(ManagerOnlyMixin, ModelAdmin):
    form = SubscriptionPlanForm
    list_display = [
        'name',
        'plan_type',
        'id',
        'display_price',
        'display_trial_days',
        'display_limits',
        'display_features',
        'is_active'
    ]
    list_filter = ['plan_type', 'is_active']
    search_fields = ['name', 'stripe_price_id', 'apple_product_id']
    readonly_fields = []

    fieldsets = (
        ('General Information', {
            'fields': ('name', 'plan_type', 'price', 'is_active')
        }),
        ('Features List', {
            'fields': ('features',),
            'description': 'Enter one feature per line (e.g. "40 major retailer clicks/day"). Simple text only, no JSON syntax required.'
        }),
        ('Trial & Limits', {
            'fields': ('trial_days', 'clicks_per_day', 'price_alerts_limit')
        }),
        ('Stripe & Apple Integrations', {
            'fields': ('stripe_price_id', 'apple_product_id'),
            'description': 'Stripe Price ID for Web/Android, and Apple Product ID for iOS In-App Purchase (Restricted to Superusers).'
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        # Lock Product & Price IDs for non-superusers to prevent accidental modification
        if not request.user.is_superuser:
            readonly.extend(['apple_product_id', 'stripe_price_id', 'plan_type'])
        return readonly

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
        if not obj.features or not isinstance(obj.features, list):
            return '—'
        items = [str(x).strip() for x in obj.features if str(x).strip()]
        if not items:
            return '—'
        preview = ' • '.join(items[:3])
        count = len(items)
        if count > 3:
            preview += f' (+{count - 3} more)'
        return format_html('<span style="color: #4b5563;">{}</span>', preview)


@admin.register(UserSubscription)
class UserSubscriptionAdmin(AdminReadOnlyFinancialMixin, ModelAdmin):
    list_display = [
        'display_user', 
        'display_plan', 
        'payment_gateway',
        'display_status', 
        'display_time_left', 
        'expires_at'
    ]
    list_filter = ['status', 'payment_gateway', 'plan']
    search_fields = ['user__email', 'stripe_subscription_id', 'apple_original_transaction_id', 'apple_latest_transaction_id']
    readonly_fields = ['trial_started_at', 'expires_at', 'apple_original_transaction_id', 'apple_latest_transaction_id'] 

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