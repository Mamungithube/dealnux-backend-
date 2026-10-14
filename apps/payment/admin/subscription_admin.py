import ast
import json
import re

from account.utils.admin_permissions import AdminReadOnlyFinancialMixin, ManagerOnlyMixin
from django import forms
from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import display

from ..models import SubscriptionPlan, UserSubscription


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
