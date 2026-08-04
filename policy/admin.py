from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import (
    Privacy_Policy, Terms_Of_Service, Cookie_Policy, Review,
    EMI_Payment_Policy, Warranty_Policy, Exchange_Policy,
    Delivery_Policy, PreOrder_Policy, Refund_Policy, Return_Policy, About_Us,
    Seller_Policy, Buyer_Protection_Policy, Prohibited_Products_Policy,
    Intellectual_Property_Policy, Community_Guidelines
)


from django.forms import Textarea
from django.db import models


# ==========================
# Reusable Base Policy Admin
# ==========================
class BasePolicyAdmin(ModelAdmin):
    list_display       = ('get_policy_name', 'get_content_preview', 'last_updated', 'created_at')
    ordering           = ('-last_updated',)
    readonly_fields    = ('last_updated', 'created_at')
    
    fieldsets = (
        ("📄 Policy Document Content", {
            "fields": ("content",),
            "description": "Write or edit the official policy text below. HTML tags (such as <h2>, <p>, <ul>, <li>, <strong>) are supported for formatting."
        }),
        ("🕒 History & Timestamps", {
            "fields": ("created_at", "last_updated"),
            "classes": ("collapse",),
        }),
    )

    formfield_overrides = {
        models.TextField: {
            'widget': Textarea(attrs={
                'rows': 22,
                'cols': 90,
                'style': 'font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; font-size: 15px; line-height: 1.65; border-radius: 10px; padding: 16px; width: 100%; min-height: 400px;',
                'placeholder': 'Write or paste your policy content here...\n\nExample HTML structure:\n<h2>1. Overview</h2>\n<p>Welcome to DealNux...</p>\n\n<h2>2. Terms</h2>\n<ul>\n  <li>Point A</li>\n  <li>Point B</li>\n</ul>'
            })
        }
    }

    @admin.display(description="Policy Name")
    def get_policy_name(self, obj):
        return obj._meta.verbose_name.title()

    @admin.display(description="Content Preview")
    def get_content_preview(self, obj):
        if not obj.content:
            return "Empty"
        text = obj.content.replace('\n', ' ')
        return text[:80] + ('...' if len(text) > 80 else '')


@admin.register(Privacy_Policy)
class PrivacyPolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(Terms_Of_Service)
class TermsOfServiceAdmin(BasePolicyAdmin):
    pass


@admin.register(Cookie_Policy)
class CookiePolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(EMI_Payment_Policy)
class EMIPaymentPolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(Warranty_Policy)
class WarrantyPolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(Exchange_Policy)
class ExchangePolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(Delivery_Policy)
class DeliveryPolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(PreOrder_Policy)
class PreOrderPolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(Refund_Policy)
class RefundPolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(Return_Policy)
class ReturnPolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(Seller_Policy)
class SellerPolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(Buyer_Protection_Policy)
class BuyerProtectionPolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(Prohibited_Products_Policy)
class ProhibitedProductsPolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(Intellectual_Property_Policy)
class IntellectualPropertyPolicyAdmin(BasePolicyAdmin):
    pass


@admin.register(Community_Guidelines)
class CommunityGuidelinesAdmin(BasePolicyAdmin):
    pass


@admin.register(About_Us)
class AboutUsAdmin(BasePolicyAdmin):
    pass

@admin.register(Review)
class ReviewAdmin(ModelAdmin):
    list_display       = ('user', 'rating', 'comment', 'created_at')
    ordering           = ('-created_at',)
    search_fields      = ('user__email', 'rating', 'created_at')
    list_filter        = ('rating', 'created_at')
    readonly_fields    = ('user', 'rating', 'comment', 'created_at')
    list_filter_submit = True

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions