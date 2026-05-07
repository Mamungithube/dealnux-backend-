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


# ============================================================================
# Inline
# ============================================================================

class SellerProductImageInline(TabularInline):
    model = SellerProductImage
    extra = 0
    fields = ['image', 'alt_text', 'order']
    tab = True

    def get_queryset(self, request):  # ✅ শুধু এটুকু রাখুন
        return super().get_queryset(request)

# ============================================================================
# Seller Request Admin
# ============================================================================

@admin.register(SellerRequest)
class SellerRequestAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_fullwidth = True
    list_filter_submit = True

    # কাস্টম কুয়েরিসেট যাতে ManyToMany এবং Foreign Key ডাটা দ্রুত লোড হয়
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
    search_fields = ['trade_name', 'user__email', 'contact_full_name', 'contact_phone']
    
    # বেশিরভাগ ফিল্ড রিড-অনলি রাখা হয়েছে যাতে অ্যাডমিন ইউজারের জমা দেওয়া লিগ্যাল ডাটা পরিবর্তন না করতে পারে
    readonly_fields = [
        'user', 'trade_name', 'legal_business_type', 'business_reg_number',
        'contact_full_name', 'job_title', 'contact_email', 'contact_phone',
        'display_categories_list', 'estimated_sku_count', 'min_price', 'max_price',
        'product_conditions', 'owns_inventory', 'fulfillment_methods', 'shipping_regions',
        'return_policy_description', 'return_policy_document', 'government_id', 
        'business_license', 'utility_bill', 'has_prior_experience', 
        'experience_description', 'digital_signature', 'reviewed_at', 'created_at'
    ]

    # ১১টি ধাপ অনুযায়ী ফিল্ডসেট সাজানো
    fieldsets = (
        (_('👤 User Account'), {
            'fields': ('user', 'status', 'admin_note'),
        }),
        (_('🏪 Step 1: Business Details'), {
            'fields': ('trade_name', 'legal_business_type', 'business_reg_number'),
            'classes': ['tab'],
        }),
        (_('📞 Step 2: Primary Contact'), {
            'fields': ('contact_full_name', 'job_title', 'contact_email', 'contact_phone'),
            'classes': ['tab'],
        }),
        (_('📦 Step 3: Product Catalog'), {
            'fields': ('display_categories_list', 'estimated_sku_count', 'min_price', 'max_price', 'product_conditions', 'owns_inventory'),
            'classes': ['tab'],
        }),
        (_('🚚 Step 4 & 5: Shipping & Returns'), {
            'fields': ('fulfillment_methods', 'shipping_regions', 'return_policy_description', 'return_policy_document'),
            'classes': ['tab'],
        }),
        (_('📄 Step 8: Documents & Verification'), {
            'fields': ('government_id', 'business_license', 'utility_bill', 'has_prior_experience', 'experience_description'),
            'classes': ['tab'],
        }),
        (_('⚖️ Step 6, 7 & 10: Legal & Signature'), {
            'fields': ('agreed_to_compliance', 'agreed_to_prohibited_items', 'digital_signature'),
            'classes': ['tab'],
        }),
    )

    actions_row = ['action_approve_row', 'action_reject_row']

    @display(description=_('Business Name'), ordering='trade_name')
    def display_trade_name(self, obj):
        return format_html('<strong>{}</strong>', obj.trade_name or "N/A")

    @display(description=_('User'), ordering='user__email')
    def display_user(self, obj):
        return format_html(
            '<div>{}<br><small style="color:#6b7280">{}</small></div>',
            obj.user.name or "No Name",
            obj.user.email
        )

    @display(description=_('Status'), label={
        'PENDING': 'warning',
        'APPROVED': 'success',
        'REJECTED': 'danger',
    })
    def display_status(self, obj):
        return obj.status

    @display(description=_('Categories'))
    def display_categories_list(self, obj):
        names = ", ".join([c.name for c in obj.categories.all()])
        return names or "None"

    # --- Actions ---
    @action(
        description=_('Approve'),
        url_path='approve-request',
        icon='check_circle',
        variant=ActionVariant.SUCCESS,
    )
    def action_approve_row(self, request, object_id):
        from django.http import HttpResponseRedirect
        obj = self.get_object(request, object_id)
        if obj.status == 'PENDING':
            # views.py এ যে লজিক ছিল সেটা মডেল মেথড হিসেবে কল হবে
            from django.db import transaction
            try:
                with transaction.atomic():
                    obj.approve(admin_user=request.user)
                self.message_user(request, f'✓ {obj.user.email} approved as seller.', messages.SUCCESS)
            except Exception as e:
                self.message_user(request, f'Error: {str(e)}', messages.ERROR)
        return HttpResponseRedirect('../..')

    @action(
        description=_('Reject'),
        url_path='reject-request',
        icon='cancel',
        variant=ActionVariant.DANGER,
    )
    def action_reject_row(self, request, object_id):
        from django.http import HttpResponseRedirect
        obj = self.get_object(request, object_id)
        if obj.status == 'PENDING':
            note = request.POST.get('admin_note', 'Rejected by admin via panel.')
            obj.status = 'REJECTED'
            obj.admin_note = note
            obj.save()
            self.message_user(request, f'✗ {obj.user.email} application rejected.', messages.WARNING)
        return HttpResponseRedirect('../..')


# # ============================================================================
# # Seller Profile Admin
# # ============================================================================
# @admin.register(SellerProfile)
# class SellerProfileAdmin(ModelAdmin):
#     compressed_fields = True
#     warn_unsaved_form = True
#     list_fullwidth = True

#     def get_queryset(self, request):
#         return super().get_queryset(request).select_related('user')

#     list_display = [
#         'display_shop',
#         'display_user_email',
#         'phone_number',
#         'display_wallet_summary', # নতুন ওয়ালেট সামারি
#         'display_active',
#         'created_at',
#     ]

#     list_filter = ['is_active', 'created_at']
#     search_fields = ['shop_name', 'user__email', 'phone_number', 'legal_full_name']
    
#     # সব নতুন এবং পুরাতন ফিল্ড রিড-অনলি করা হয়েছে (ব্যালেন্স অ্যাডমিন ম্যানুয়ালি চেঞ্জ করা উচিত নয়)
#     readonly_fields = [
#         'user', 'legal_full_name', 'business_address', 
#         'shop_name', 'shop_description', 'shop_logo', 'phone_number',
#         'pending_balance', 'available_balance', 'total_withdrawn',
#         'bank_name', 'bank_account_number',
#         'total_products', 'total_orders', 'total_earnings', 
#         'is_active', 'created_at', 'updated_at',
#     ]

#     fieldsets = (
#         (_('🏪 Shop Info'), {
#             'fields': ('user', 'shop_name', 'shop_description', 'shop_logo', 'phone_number'),
#         }),
#         (_('⚖️ Legal Information'), { # নতুন সেকশন
#             'fields': ('legal_full_name', 'business_address'),
#         }),
#         (_('💰 Wallet & Balances'), { # নতুন সেকশন
#             'fields': ('pending_balance', 'available_balance', 'total_withdrawn', 'total_earnings'),
#         }),
#         (_('💳 Payout/Bank Info'), {
#             'fields': ('bank_name', 'bank_account_number'),
#             'classes': ('collapse',),
#         }),
#         (_('📊 Sales Statistics'), {
#             'fields': ('total_products', 'total_orders'),
#         }),
#         (_('⚙️ Status'), {
#             'fields': ('is_active',),
#         }),
#     )

#     def has_delete_permission(self, request, obj=None):
#         return False

#     def get_actions(self, request):
#         actions = super().get_actions(request)
#         if 'delete_selected' in actions:
#             del actions['delete_selected']
#         return actions

#     @display(description=_('Shop'), ordering='shop_name')
#     def display_shop(self, obj):
#         if obj.shop_logo:
#             img = format_html(
#                 '<img src="{}" width="28" height="28" '
#                 'style="border-radius:50%;object-fit:cover;margin-right:8px;vertical-align:middle"/>',
#                 obj.shop_logo.url,
#             )
#         else:
#             img = '🏪 '
#         return format_html('{}<strong>{}</strong>', img, obj.shop_name)

#     @display(description=_('Email'), ordering='user__email')
#     def display_user_email(self, obj):
#         return obj.user.email

#     @display(description=_('Wallet Summary')) # লিস্টে ব্যালেন্স দেখার জন্য নতুন মেথড
#     def display_wallet_summary(self, obj):
#         return format_html(
#             '<div style="font-size:11px; line-height:1.4">'
#             '<span style="color:#f59e0b">Pending: ${}</span><br>'
#             '<span style="color:#10b981">Available: ${}</span><br>'
#             '<span style="color:#6b7280">Withdrawn: ${}</span>'
#             '</div>',
#             f'{obj.pending_balance:,.2f}',
#             f'{obj.available_balance:,.2f}',
#             f'{obj.total_withdrawn:,.2f}',
#         )

#     @display(description=_('Active'), boolean=True, ordering='is_active')
#     def display_active(self, obj):
#         return obj.is_active


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
    readonly_fields = [
        'seller', 'category', 'title', 'description', 'brand', 'model_number',
        'main_image', 'price', 'original_price', 'currency', 'quantity', 'condition',
        'free_shipping', 'shipping_cost', 'estimated_delivery_days',
        'returns_accepted', 'return_period_days',
        'created_at', 'updated_at',
    ]
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
        from django.http import HttpResponseRedirect
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
        from django.http import HttpResponseRedirect
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
    compressed_fields = True
    list_fullwidth = True
    list_filter_submit = True

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'buyer', 'seller', 'seller_product', 'listing'
        )

    list_display = [
        'display_buyer',
        'display_order_id',
        'display_seller',
        'display_amount',
        'quantity',
        'display_order_status',
        'created_at',
    ]
    list_filter = ['status', 'created_at', 'currency']
    search_fields = [
        'buyer__email', 'buyer__name',
        'seller__shop_name', 'tracking_number',
        'seller_product__title',
    ]
    readonly_fields = [
        'buyer', 'seller', 'unit_price', 'seller_product', 'listing',
        'quantity', 'currency', 'shipping_address', 'tracking_number', 'note',
        'total_price', 'created_at', 'updated_at',
    ]
    ordering = ['-created_at']

    fieldsets = (
        (_('🛒 Order Info'), {
            'fields': ('buyer', 'seller', 'seller_product', 'listing'),
        }),
        (_('💰 Pricing'), {
            'fields': ('quantity', 'unit_price', 'total_price', 'currency'),
        }),
        (_('📦 Delivery'), {
            'fields': ('shipping_address', 'tracking_number', 'note'),
        }),
        (_('⚙️ Status'), {
            'fields': ('status',),
        }),
        (_('🕐 Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    actions_submit_line = ['action_mark_shipped']

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    @display(description=_('Order'), ordering='id')
    def display_order_id(self, obj):
        return format_html('<strong>#{}</strong>', obj.id)

    @display(description=_('Buyer'), ordering='buyer__email')
    def display_buyer(self, obj):
        return format_html(
            '<strong>{}</strong><br>'
            '<small style="color:#6b7280">{}</small>',
            obj.buyer.name or '—',
            obj.buyer.email,
        )

    @display(description=_('Shop'), ordering='seller__shop_name')
    def display_seller(self, obj):
        return obj.seller.shop_name if obj.seller else '—'

    @display(description=_('Total'), ordering='total_price')
    def display_amount(self, obj):
        return format_html(
            '<strong style="color:#16a34a">${} {}</strong>',
            f'{obj.total_price:,.2f}',
            obj.currency,
        )

    @display(
        description=_('Status'),
        ordering='status',
        label={
            'PENDING':   'warning',
            'CONFIRMED': 'info',
            'SHIPPED':   'info',
            'DELIVERED': 'success',
            'CANCELLED': 'danger',
            'REFUNDED':  'danger',
        },
    )
    def display_order_status(self, obj):
        return obj.status

    @action(description=_('Save & Mark as Shipped'))
    def action_mark_shipped(self, request, obj):
        if obj.status == 'CONFIRMED':
            obj.status = 'SHIPPED'
            obj.save(update_fields=['status'])
            self.message_user(request, f'Order #{obj.id} marked as shipped.')


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

from django.core.cache import cache

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
