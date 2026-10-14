import logging
from custom_ads.utils import send_dealnux_email
from django.contrib import admin, messages
from django.core.cache import cache
from django.db import transaction
from django.http import HttpResponseRedirect
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import action, display
from unfold.enums import ActionVariant

from ..models import SellerProfile, SellerRequest

logger = logging.getLogger(__name__)


def pending_seller_requests_count(request):
    count = cache.get('pending_seller_requests_count')
    if count is None:
        count = SellerRequest.objects.filter(status='PENDING').count()
        cache.set('pending_seller_requests_count', count, 60)
    return str(count) if count > 0 else None


@admin.register(SellerRequest)
class SellerRequestAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_fullwidth = True
    list_filter_submit = True

    def has_change_permission(self, request, obj=None):
        if request.user.groups.filter(name='Admin_Associate').exists():
            return False
        return super().has_change_permission(request, obj)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user').prefetch_related('categories')

    list_display = [
        'display_trade_name',
        'display_user',
        'contact_phone',
        'display_status',
        'created_at',
    ]

    list_filter = ['status', 'legal_business_type', 'created_at']
    search_fields = ['trade_name', 'user__email', 'contact_full_name']
    
    readonly_fields = [
        'user', 'trade_name', 'legal_business_type', 'business_reg_number',
        'contact_full_name', 'job_title', 'contact_email', 'contact_phone',
        'display_categories_list', 
        'estimated_sku_count', 'min_price', 'max_price',
        'display_product_conditions', 
        'owns_inventory', 
        'display_fulfillment_methods', 
        'display_shipping_regions',   
        'agree_return_policy', 
        'display_gov_id', 'display_license', 'display_utility_bill', 
        'has_prior_experience', 'experience_description', 
        'digital_signature', 'reviewed_at', 'created_at'
    ]

    fieldsets = (
        (_('👤 User Account'), {'fields': ('user', 'status', 'admin_note')}),
        (_('🏪 Business Details'), {'fields': ('trade_name', 'legal_business_type', 'business_reg_number'), 'classes': ['tab']}),
        (_('📞 Primary Contact'), {'fields': ('contact_full_name', 'job_title', 'contact_email', 'contact_phone'), 'classes': ['tab']}),
        (_('📦 Product Catalog'), {'fields': ('display_categories_list', 'estimated_sku_count', 'min_price', 'max_price', 'display_product_conditions', 'owns_inventory'), 'classes': ['tab']}),
        (_('🚚 Shipping & Returns'), {'fields': ('display_fulfillment_methods', 'display_shipping_regions', 'agree_return_policy'), 'classes': ['tab']}),
        (_('📄 Documents & Verification'), {'fields': ('display_gov_id', 'display_license', 'display_utility_bill', 'has_prior_experience', 'experience_description'), 'classes': ['tab']}),
        (_('⚖️ Legal & Signature'), {'fields': ('agreed_to_compliance', 'agreed_to_prohibited_items', 'digital_signature'), 'classes': ['tab']}),
    )

    @display(description=_('Product Conditions'))
    def display_product_conditions(self, obj):
        return ", ".join(obj.product_conditions) if obj.product_conditions else "N/A"

    @display(description=_('Fulfillment Methods'))
    def display_fulfillment_methods(self, obj):
        return ", ".join(obj.fulfillment_methods) if obj.fulfillment_methods else "N/A"

    @display(description=_('Shipping Regions'))
    def display_shipping_regions(self, obj):
        return ", ".join(obj.shipping_regions) if obj.shipping_regions else "N/A"

    @display(description="Government ID")
    def display_gov_id(self, obj):
        if obj.government_id:
            return format_html('<a href="{}" target="_blank" style="background: #2563eb; color: white; padding: 5px 15px; border-radius: 5px; text-decoration: none; font-weight: bold;">👁️ View Gov ID</a>', obj.government_id.url)
        return "No file uploaded"

    @display(description="Business License")
    def display_license(self, obj):
        if obj.business_license:
            return format_html('<a href="{}" target="_blank" style="background: #2563eb; color: white; padding: 5px 15px; border-radius: 5px; text-decoration: none; font-weight: bold;">👁️ View License</a>', obj.business_license.url)
        return "No file uploaded"

    @display(description="Utility Bill")
    def display_utility_bill(self, obj):
        if obj.utility_bill:
            return format_html('<a href="{}" target="_blank" style="background: #2563eb; color: white; padding: 5px 15px; border-radius: 5px; text-decoration: none; font-weight: bold;">👁️ View Utility Bill</a>', obj.utility_bill.url)
        return "No file uploaded"

    @display(description=_('Categories'))
    def display_categories_list(self, obj):
        if obj.pk:
            return ", ".join([c.name for c in obj.categories.all()])
        return "None"

    @display(description=_('Business Name'))
    def display_trade_name(self, obj):
        return format_html('<strong>{}</strong>', obj.trade_name or "N/A")

    @display(description=_('User'))
    def display_user(self, obj):
        return format_html('{}<br><small style="color:#6b7280">{}</small>', obj.user.name or "No Name", obj.user.email)

    @display(description=_('Status'), label={'PENDING': 'warning', 'APPROVED': 'success', 'REJECTED': 'danger'})
    def display_status(self, obj): 
        return obj.status

    actions_row = ['action_approve_row', 'action_reject_row']

    def change_view(self, request, object_id, form_url='', extra_context=None):
        if not request.user.is_superuser and request.user.groups.filter(name='Admin_Associate').exists():
            messages.warning(request, "Access Denied: You cannot modify or approve seller applications.")
            return HttpResponseRedirect("../")
        return super().change_view(request, object_id, form_url, extra_context)

    @action(description=_('Approve'), url_path='approve-request', icon='check_circle', variant=ActionVariant.SUCCESS)
    def action_approve_row(self, request, object_id):
        if not request.user.is_superuser:
            self.message_user(request, "Only managers can approve sellers.", level='error')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../..'))
 
        obj = self.get_object(request, object_id)
        if obj.status == 'PENDING':
            try:
                with transaction.atomic():
                    obj.approve(admin_user=request.user)
                self.message_user(request, f'✓ {obj.user.email} approved successfully.', messages.SUCCESS)
            except Exception as e:
                self.message_user(request, f'Error: {str(e)}', messages.ERROR)
 
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../..'))
 
    @action(description=_('Reject'), url_path='reject-request', icon='cancel', variant=ActionVariant.DANGER)
    def action_reject_row(self, request, object_id):
        if not request.user.is_superuser:
            self.message_user(request, "Only managers can reject sellers.", level='error')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../..'))
 
        obj = self.get_object(request, object_id)
        if obj.status == 'PENDING':
            obj.status = 'REJECTED'
            obj.admin_note = "Rejected by admin."
            obj.save()
            self.message_user(request, f'✗ {obj.user.email} request rejected.', messages.WARNING)
 
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../..'))


@admin.register(SellerProfile)
class SellerProfileAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = [
        'display_shop',
        'display_user',
        'display_balances',
        'total_products',
        'display_active',
        'created_at',
    ]
    
    actions_row = ['suspend_seller', 'reinstate_seller', 'delete_seller_marketplace', 'pause_payout']

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if request.user.groups.filter(name='Admin').exists() and not request.user.is_superuser:
            readonly += ['pending_balance', 'available_balance', 'total_earnings']
        return readonly

    @action(description=_("Suspend Seller"), url_path="suspend", variant=ActionVariant.DANGER)
    def suspend_seller(self, request, object_id):
        seller = SellerProfile.objects.get(pk=object_id)
        seller.is_active = False
        seller.save()
        
        try:
            send_dealnux_email(
                "Marketplace Suspended - DealNux",
                seller.user.email,
                "emails/seller_suspended.html",
                {"seller": seller, "reason": "Violation of DealNux seller policies."}
            )
        except Exception as e:
            logger.error(f"Suspend email error: {e}")
        self.message_user(request, _("Seller suspended and notified via email."))
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    @action(description=_("Reinstate Seller"), url_path="reinstate", variant=ActionVariant.SUCCESS)
    def reinstate_seller(self, request, object_id):
        seller = SellerProfile.objects.get(pk=object_id)
        seller.is_active = True
        if seller.shop_name.startswith("CLOSED - "):
            seller.shop_name = seller.shop_name.replace("CLOSED - ", "", 1)
        seller.save()

        try:
            send_dealnux_email(
                "Account Reinstated - DealNux",
                seller.user.email,
                "emails/seller_reinstated.html",
                {"seller": seller}
            )
        except Exception as e:
            logger.error(f"Reinstate email error: {e}")
        self.message_user(request, _("Seller reinstated and notified via email."))
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    @action(description=_("Delete Marketplace (Sell No, Buy Yes)"), url_path="deactivate-shop", variant=ActionVariant.DANGER)
    def delete_seller_marketplace(self, request, object_id):
        seller = SellerProfile.objects.get(pk=object_id)
        seller.is_active = False
        if not seller.shop_name.startswith("CLOSED - "):
            seller.shop_name = f"CLOSED - {seller.shop_name}"
        seller.save()

        try:
            send_dealnux_email(
                "Marketplace Account Closed - DealNux",
                seller.user.email,
                "emails/seller_deactivated.html",
                {"seller": seller}
            )
        except Exception as e:
            logger.error(f"Deactivate email error: {e}")
        self.message_user(request, _("Seller marketplace deleted and notified via email."))
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    @action(description=_("Pause Payout"), url_path="pause", variant=ActionVariant.WARNING)
    def pause_payout(self, request, object_id):
        self.message_user(request, _("Payout paused for this seller."))
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    @display(description='Risk Level', label={
        'High Risk': 'danger',
        'Medium': 'warning',
        'Healthy': 'success'
    })
    def display_risk_level(self, obj):
        if obj.seller_score < 30: return "High Risk"
        if obj.seller_score < 60: return "Medium"
        return "Healthy"

    list_filter = ['is_active', 'created_at']
    search_fields = ['shop_name', 'user__email']

    readonly_fields = [
        'user', 'shop_name', 'pending_balance', 'available_balance',
        'total_earnings', 'total_products', 'total_orders', 'created_at', 'updated_at'
    ]

    fieldsets = (
        (_('🏪 Shop Identity'), {
            'fields': ('user', 'shop_name', 'shop_description', 'shop_logo'),
        }),
        (_('💰 Wallet & Escrow'), {
            'fields': ('pending_balance', 'available_balance', 'total_earnings'),
        }),
        (_('📊 Performance Stats'), {
            'fields': ('total_products', 'total_orders', 'seller_score'),
        }),
        (_('⚙️ System Status'), {
            'fields': ('is_active',),
        }),
    )

    @display(description=_('Shop/Seller'))
    def display_shop(self, obj):
        return format_html('<strong>{}</strong>', obj.shop_name)

    @display(description=_('User Email'))
    def display_user(self, obj):
        return obj.user.email

    @display(description=_('Wallet (P / A)'))
    def display_balances(self, obj):
        return format_html(
            '<span style="color: #f59e0b; font-weight: bold;">P: ${}</span> | '
            '<span style="color: #10b981; font-weight: bold;">A: ${}</span>',
            f'{obj.pending_balance:,.2f}',
            f'{obj.available_balance:,.2f}'
        )

    @display(description=_('Status'), boolean=True)
    def display_active(self, obj):
        return obj.is_active
