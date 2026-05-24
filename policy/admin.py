from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import (
    Privacy_Policy, Terms_Of_Service, Cookie_Policy, Review,
    EMI_Payment_Policy, Warranty_Policy, Exchange_Policy,
    Delivery_Policy, PreOrder_Policy, Refund_Policy, Return_Policy
)


# ==========================
# Reusable Base Policy Admin
# ==========================
class BasePolicyAdmin(ModelAdmin):
    list_display       = ('last_updated', 'created_at')
    ordering           = ('-last_updated',)
    search_fields      = ('last_updated', 'created_at')
    readonly_fields    = ('last_updated', 'created_at')
    list_filter_submit = True


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