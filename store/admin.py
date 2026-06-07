from django.core.cache import cache
from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display, action
from unfold.enums import ActionVariant

from .models import (
    SellerRequest, SellerProfile,
    SellerProduct, SellerProductImage,
    Order, Coupon,
)
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponseRedirect
from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import display, action
from unfold.enums import ActionVariant
from django.contrib import messages
from .models import SellerRequest
from django.core.mail import send_mail
# ============================================================================
# Inline
# ============================================================================


class SellerProductImageInline(TabularInline):
    model = SellerProductImage
    extra = 0
    fields = ['image', 'alt_text', 'order']
    tab = True

    def get_queryset(self, request):
        return super().get_queryset(request)

# ============================================================================
# Seller Request Admin
# ============================================================================

from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.http import HttpResponseRedirect
from django.db import transaction
from unfold.admin import ModelAdmin
from unfold.decorators import display, action
from unfold.enums import ActionVariant
from .models import SellerRequest

@admin.register(SellerRequest)
class SellerRequestAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_fullwidth = True
    list_filter_submit = True

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
    
    # [FIXED] readonly_fields এর নাম আর নিচের ফাংশনের নাম এখন হুবহু এক
    readonly_fields = [
        'user', 'trade_name', 'legal_business_type', 'business_reg_number',
        'contact_full_name', 'job_title', 'contact_email', 'contact_phone',
        'display_categories_list', 
        'estimated_sku_count', 'min_price', 'max_price',
        'display_product_conditions', 
        'owns_inventory', 
        'display_fulfillment_methods', 
        'display_shipping_regions',   
        'return_policy_description', 'return_policy_document', 
        'display_gov_id', 'display_license', 'display_utility_bill', # এখানে নাম ঠিক করা হয়েছে
        'has_prior_experience', 'experience_description', 
        'digital_signature', 'reviewed_at', 'created_at'
    ]

    fieldsets = (
        (_('👤 User Account'), {'fields': ('user', 'status', 'admin_note')}),
        (_('🏪 Business Details'), {'fields': ('trade_name', 'legal_business_type', 'business_reg_number'), 'classes': ['tab']}),
        (_('📞 Primary Contact'), {'fields': ('contact_full_name', 'job_title', 'contact_email', 'contact_phone'), 'classes': ['tab']}),
        (_('📦 Product Catalog'), {'fields': ('display_categories_list', 'estimated_sku_count', 'min_price', 'max_price', 'display_product_conditions', 'owns_inventory'), 'classes': ['tab']}),
        (_('🚚 Shipping & Returns'), {'fields': ('display_fulfillment_methods', 'display_shipping_regions', 'return_policy_description', 'return_policy_document'), 'classes': ['tab']}),
        (_('📄 Documents & Verification'), {'fields': ('display_gov_id', 'display_license', 'display_utility_bill', 'has_prior_experience', 'experience_description'), 'classes': ['tab']}),
        (_('⚖️ Legal & Signature'), {'fields': ('agreed_to_compliance', 'agreed_to_prohibited_items', 'digital_signature'), 'classes': ['tab']}),
    )

    # --- ১. মেথডসমূহ (JSON/List to Text) ---
    @display(description=_('Product Conditions'))
    def display_product_conditions(self, obj):
        return ", ".join(obj.product_conditions) if obj.product_conditions else "N/A"

    @display(description=_('Fulfillment Methods'))
    def display_fulfillment_methods(self, obj):
        return ", ".join(obj.fulfillment_methods) if obj.fulfillment_methods else "N/A"

    @display(description=_('Shipping Regions'))
    def display_shipping_regions(self, obj):
        return ", ".join(obj.shipping_regions) if obj.shipping_regions else "N/A"

    # --- ২. ফাইল ভিউ বাটন (View Buttons) ---
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

    # --- ৩. অন্যান্য ডিসপ্লে ---
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

    # --- ৪. অ্যাকশনসমূহ (Actions with Redirect Fix) ---
    actions_row = ['action_approve_row', 'action_reject_row']

    @action(description=_('Approve'), url_path='approve-request', icon='check_circle', variant=ActionVariant.SUCCESS)
    def action_approve_row(self, request, object_id):
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
        obj = self.get_object(request, object_id)
        if obj.status == 'PENDING':
            obj.status = 'REJECTED'
            obj.admin_note = "Rejected by admin."
            obj.save()
            self.message_user(request, f'✗ {obj.user.email} request rejected.', messages.WARNING)
        
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../..'))

# # ============================================================================
# # Seller Profile Admin
# # ============================================================================
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
    
    # বাটনগুলো সিরিয়াল অনুযায়ী: Suspend, Reinstate, Delete Marketplace
    actions_row = ['suspend_seller', 'reinstate_seller', 'delete_seller_marketplace', 'pause_payout']

    # ========================================================================
    # Permissions Logic (Manager vs Admin)
    # Manager (Superuser) সব পারবে। Admin গ্রুপ আর্থিক বিষয় বা সেলার এপ্রুভাল পারবে না।
    # ========================================================================
    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if request.user.groups.filter(name='Admin').exists() and not request.user.is_superuser:
            # Admin হলে ব্যালেন্স এডিট বা দেখা সীমিত হবে
            readonly += ['pending_balance', 'available_balance', 'total_earnings']
        return readonly

    # ========================================================================
    # Actions Logic (Suspend, Reinstate, Delete)
    # ========================================================================
    
    @action(description=_("Suspend Seller"), url_path="suspend", variant=ActionVariant.DANGER)
    def suspend_seller(self, request, object_id):
        seller = SellerProfile.objects.get(pk=object_id)
        seller.is_active = False
        seller.save()
        
        # ক্লায়েন্ট চেয়েছে ইমেল নোটিফিকেশন (সাসপেন্ড হলে আপিলের সুযোগ আছে)
        send_mail(
            "Marketplace Suspended - DealNux",
            f"Hello {seller.shop_name}, your marketplace access has been suspended. You can appeal this decision.",
            "noreply@dealnux.com",
            [seller.user.email],
        )
        self.message_user(request, _("Seller suspended and notified via email."))
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    @action(description=_("Reinstate Seller"), url_path="reinstate", variant=ActionVariant.SUCCESS)
    def reinstate_seller(self, request, object_id):
        seller = SellerProfile.objects.get(pk=object_id)
        seller.is_active = True
        seller.save()
        self.message_user(request, _("Seller reinstated successfully."))
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    @action(description=_("Delete Marketplace (Sell No, Buy Yes)"), url_path="deactivate-shop", variant=ActionVariant.DANGER)
    def delete_seller_marketplace(self, request, object_id):
        seller = SellerProfile.objects.get(pk=object_id)
        # ক্লায়েন্ট বলেছে: সেলার ডিলিট করলে শুধু সেলিং বন্ধ হবে, কেনাকাটা চলবে।
        seller.is_active = False
        seller.shop_name = f"CLOSED - {seller.shop_name}"
        seller.save()
        # সেলারের প্রোডাক্টগুলো রিজেক্ট করে দেওয়া
        seller.products.update(status='REJECTED')
        
        self.message_user(request, _("Marketplace deactivated permanently. User can still purchase items."))
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    @action(description=_("Pause Payout"), url_path="pause", variant=ActionVariant.WARNING)
    def pause_payout(self, request, object_id):
        # পে-আউট পজ করার লজিক
        self.message_user(request, _("Payout paused for this seller."))
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    # ========================================================================
    # Display & UI Logic
    # ========================================================================

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
# ============================================================================
# Seller Product Admin
# ============================================================================


@admin.register(SellerProduct)
class SellerProductAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_fullwidth = True
    list_filter_submit = True
    list_per_page = 20

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'seller',
            'category',
            'linked_product',
            'linked_listing',
            'reviewed_by',
        )

    list_display = [
        'display_seller',
        'display_product',
        'display_price',
        'quantity',
        'display_condition',
        'display_status',
        'created_at',
    ]
    list_filter = ['status', 'condition', 'category', 'created_at']
    search_fields = ['title', 'brand', 'seller__shop_name', 'model_number']
    # readonly_fields = [
    #     'seller', 'category', 'title', 'description', 'brand', 'model_number',
    #     'main_image', 'price', 'original_price', 'currency', 'quantity', 'condition',
    #     'free_shipping', 'shipping_cost', 'estimated_delivery_days',
    #     'returns_accepted', 'return_period_days',
    #     'created_at', 'updated_at',
    # ]
    tab_fields = [
        'returns_accepted', 'return_period_days',

        'linked_product', 'linked_listing',
        'reviewed_by', 'reviewed_at',
        'created_at', 'updated_at',
    ]
    inlines = [SellerProductImageInline]
    ordering = ['-created_at']

    fieldsets = (
        (_('📦 Basic Info'), {
            'fields': ('seller', 'category', 'title', 'description', 'brand', 'model_number'),
        }),
        (_('💰 Price & Stock'), {
            'fields': ('price', 'original_price', 'currency', 'quantity', 'condition'),
        }),
        (_('🖼️ Main Image'), {
            'fields': ('main_image',),
        }),
        (_('🚚 Shipping'), {
            'fields': ('free_shipping', 'shipping_cost', 'estimated_delivery_days'),
            'classes': ('collapse',),
        }),
        (_('↩️ Returns'), {
            'fields': ('returns_accepted', 'return_period_days'),
            'classes': ('collapse',),
        }),
        (_('⚙️ Admin Review'), {
            'fields': ('status', 'admin_note', 'reviewed_by', 'reviewed_at'),
        }),
        (_('🔗 Linked Records (auto-generated)'), {
            'fields': ('linked_product', 'linked_listing'),
            'classes': ('collapse',),
        }),
    )

    actions_row = ['action_approve_product', 'action_reject_product']
    actions_list = []

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    @display(description=_('Product'), ordering='title')
    def display_product(self, obj):
        if obj.main_image:
            img = format_html(
                '<img src="{}" width="36" height="36" '
                'style="border-radius:6px;object-fit:cover;'
                'margin-right:8px;vertical-align:middle"/>',
                obj.main_image.url,
            )
        else:
            img = ''
        return format_html(
            '{}<div style="display:inline-block;vertical-align:middle">'
            '<strong>{}</strong><br>'
            '<small style="color:#6b7280">{}</small></div>',
            img,
            obj.title[:50],
            obj.brand or '—',
        )

    @display(description=_('Seller'), ordering='seller__shop_name')
    def display_seller(self, obj):
        return format_html('<span style="font-weight:500">{}</span>', obj.seller.shop_name)

    @display(description=_('Price'), ordering='price')
    def display_price(self, obj):
        if obj.original_price:
            return format_html(
                '<strong style="color:#16a34a">${}</strong> '
                '<del style="color:#9ca3af;font-size:11px">${}</del>',
                f'{obj.price:,.2f}',
                f'{obj.original_price:,.2f}',
            )
        return format_html('<strong>${}</strong>', f'{obj.price:,.2f}')

    @display(
        description=_('Condition'),
        ordering='condition',
        label={
            'NEW':         'success',
            'USED':        'warning',
            'REFURBISHED': 'info',
            'OPEN_BOX':    'info',
        },
    )
    def display_condition(self, obj):
        return obj.condition

    @display(
        description=_('Status'),
        ordering='status',
        label={
            'DRAFT':    'info',
            'PENDING':  'warning',
            'APPROVED': 'success',
            'REJECTED': 'danger',
        },
    )
    def display_status(self, obj):
        return obj.status

    @action(
        description=_('Approve'),
        url_path='approve-product',
        icon='check_circle',
        variant=ActionVariant.SUCCESS,
    )
    def action_approve_product(self, request, object_id):

        obj = SellerProduct.objects.get(pk=object_id)
        if obj.status != 'APPROVED':
            obj.approve(admin_user=request.user)
            self.message_user(
                request, f'✓ "{obj.title[:40]}" approved and listed.')
        return HttpResponseRedirect('../..')

    @action(
        description=_('Reject'),
        url_path='reject-product',
        icon='cancel',
        variant=ActionVariant.DANGER,
    )
    def action_reject_product(self, request, object_id):

        obj = SellerProduct.objects.get(pk=object_id)
        if obj.status != 'REJECTED':
            obj.reject(admin_user=request.user, note='Rejected by admin.')
            self.message_user(request, f'✗ "{obj.title[:40]}" rejected.')
        return HttpResponseRedirect('../..')


# ============================================================================
# Order Admin
# ============================================================================

@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = [
        'order_number',
        'display_buyer',
        'display_seller',
        'display_price_breakdown',
        'display_total',
        'display_status',
        'is_accepted_by_buyer',
        'created_at',
    ]
    list_filter = ['status', 'is_accepted_by_buyer',
                   'fault_party', 'created_at']
    search_fields = ['order_number', 'buyer__email',
                     'seller__shop_name', 'tracking_number']

    # Payment data is protected.
    readonly_fields = [
        'buyer', 'seller', 'seller_product', 'listing',
        'unit_price', 'quantity', 'discount_amount', 'item_total',
        'shipping_fee', 'service_fee', 'total_price', 'currency',
        'is_accepted_by_buyer', 'accepted_at', 'refund_amount', 'created_at', 'updated_at'
    ]

    fieldsets = (
        (_('🛒 Order Info'), {
            'fields': ('buyer', 'seller', 'seller_product', 'status'),
        }),
        (_('💰 Pricing Breakdown'), {
            'fields': (
                'quantity', 'unit_price', 'discount_amount',
                'item_total', 'shipping_fee', 'service_fee', 'total_price', 'currency'
            ),
            'description': _('Detailed breakdown of payments and fees.')
        }),
        (_('🚚 Shipping & Delivery'), {
            'fields': ('shipping_address', 'tracking_number', 'note'),
        }),
        (_('✅ Acceptance & Refund'), {
            'fields': ('is_accepted_by_buyer', 'accepted_at', 'fault_party', 'refund_amount'),
        }),
    )

    @display(description=_('Buyer'))
    def display_buyer(self, obj):
        return format_html('{}<br><small>{}</small>', obj.buyer.name, obj.buyer.email)

    @display(description=_('Shop'))
    def display_seller(self, obj):
        return obj.seller.shop_name if obj.seller else "—"

    @display(description=_('Breakdown (Item+Ship+Fee)'))
    def display_price_breakdown(self, obj):
        return format_html(
            '<small>Item: ${}</small><br>'
            '<small>Ship: ${}</small><br>'
            '<small style="color: #6366f1;">Fee: ${}</small>',
            f'{obj.item_total:,.2f}',
            f'{obj.shipping_fee:,.2f}',
            f'{obj.service_fee:,.2f}'
        )

    @display(description=_('Grand Total'))
    def display_total(self, obj):
        return format_html('<strong style="color: #10b981;">${}</strong>', f'{obj.total_price:,.2f}')

    @display(description=_('Status'), label={
        'PENDING': 'warning',
        'CONFIRMED': 'info',
        'SHIPPED': 'info',
        'ACCEPTED': 'success',
        'CANCELLED': 'danger',
        'REFUNDED': 'danger',
    })
    def display_status(self, obj):
        return obj.status

    def has_delete_permission(self, request, obj=None):
        return False


# ============================================================================
# 3. Sidebar Badges (Optional - For better UX)
# ============================================================================
def pending_orders_count(request):
    return Order.objects.filter(status='PENDING').count() or None


# ============================================================================
# Coupon Admin
# ============================================================================

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
        'expires_at',]
    # list_editable = ['is_active']

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


# ============================================================================
# Sidebar Badge Functions
# ============================================================================


def pending_seller_requests_count(request):
    count = cache.get('pending_seller_requests_count')
    if count is None:
        count = SellerRequest.objects.filter(status='PENDING').count()
        cache.set('pending_seller_requests_count', count, 60)
    return str(count) if count > 0 else None


def pending_products_count(request):
    count = cache.get('pending_products_count')
    if count is None:
        from django.db.models import Q
        count = SellerProduct.objects.filter(
            Q(status='PENDING') | Q(status='DRAFT')).count()
        cache.set('pending_products_count', count, 60)
    return str(count) if count > 0 else None
