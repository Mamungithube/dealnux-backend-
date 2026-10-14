import logging
from custom_ads.utils import send_dealnux_email
from django.contrib import admin, messages
from django.core.cache import cache
from django.http import HttpResponseRedirect
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action, display
from unfold.enums import ActionVariant

from ..models import ProductReview, SellerProduct, SellerProductImage

logger = logging.getLogger(__name__)


def pending_products_count(request):
    count = cache.get('pending_products_count')
    if count is None:
        from django.db.models import Q
        count = SellerProduct.objects.filter(
            Q(status='PENDING') | Q(status='DRAFT')).count()
        cache.set('pending_products_count', count, 60)
    return str(count) if count > 0 else None


class SellerProductImageInline(TabularInline):
    model = SellerProductImage
    extra = 0
    fields = ['image', 'alt_text', 'order']
    tab = True

    def get_queryset(self, request):
        return super().get_queryset(request)


@admin.register(SellerProduct)
class SellerProductAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_fullwidth = True
    list_filter_submit = True
    list_per_page = 20
    raw_id_fields = ('seller', 'category', 'linked_product', 'linked_listing', 'reviewed_by')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'seller',
            'category',
            'linked_product',
            'linked_listing',
            'reviewed_by',
        ).prefetch_related(
            'images' 
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
    list_filter = [
        'status', 
        'condition', 
        ('category', admin.RelatedOnlyFieldListFilter), 
        'created_at'
    ]
    search_fields = ['title', 'brand', 'seller__shop_name', 'model_number']

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

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions
    
    actions = ['delete_product_with_notification']
    actions_row = ['delete_product_row']

    @action(
        description="Delete & Notify Seller",
        url_path='delete-product',
        icon='delete',
        variant=ActionVariant.DANGER,
    )
    def delete_product_row(self, request, object_id):
        try:
            product = SellerProduct.objects.get(pk=object_id)
            seller_email = product.seller.user.email
            seller_shop = product.seller.shop_name
            product_title = product.title

            product.delete()

            send_dealnux_email(
                "Product Removed - DealNux",
                seller_email,
                "emails/product_deleted.html",
                {
                    "seller_shop": seller_shop,
                    "product_title": product_title,
                    "deleted_by": request.user.email,
                }
            )
            self.message_user(request, f"✓ '{product_title}' deleted. Seller notified.")
        except SellerProduct.DoesNotExist:
            self.message_user(request, "Product not found.", level='error')
        except Exception as e:
            self.message_user(request, f"Error deleting product: {str(e)}", level='error')

        return HttpResponseRedirect('../..')

    @admin.action(description="Delete selected products & notify sellers")
    def delete_product_with_notification(self, request, queryset):
        count = 0
        for product in queryset:
            try:
                send_dealnux_email(
                    "Product Removed - DealNux",
                    product.seller.user.email,
                    "emails/product_deleted.html",
                    {
                        "seller_shop": product.seller.shop_name,
                        "product_title": product.title,
                        "deleted_by": request.user.email,
                    }
                )
                product.delete()
                count += 1
            except Exception as e:
                self.message_user(request, f"Error deleting '{product.title}': {str(e)}", level='error')

        self.message_user(request, f"✓ {count} products deleted. Sellers notified.")

    @display(description=_('Product'), ordering='title')
    def display_product(self, obj):
        if obj.main_image:
            return format_html(
                '<img src="{}" width="36" height="36" loading="lazy" '
                'style="border-radius:6px; object-fit:cover; margin-right:8px; vertical-align:middle"/>'
                '<div style="display:inline-block; vertical-align:middle">'
                '<strong>{}</strong><br><small style="color:#6b7280">{}</small></div>',
                obj.main_image.url, obj.title[:50], obj.brand or '—'
            )
        return obj.title[:50]

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


@admin.register(ProductReview)
class ProductReviewAdmin(ModelAdmin):
    compressed_fields = True
    list_fullwidth = True
    list_filter_submit = True
    actions_row = ['delete_review_row']
    list_display = (
        'display_product', 'display_seller', 'display_buyer', 
        'display_rating', 'short_comment', 'created_at', 'id'
    )
    list_filter = ('rating', 'created_at')
    search_fields = (
        'product__title', 'user__email', 'user__first_name',
        'user__last_name', 'comment'
    )
    raw_id_fields = ('product', 'user')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'product', 'product__seller', 'user'
        )

    @action(
        description=_("Delete"),
        url_path='delete-review',
        icon='delete',
        variant=ActionVariant.DANGER,
    )
    def delete_review_row(self, request, object_id):
        try:
            review = self.get_object(request, object_id)
            if review:
                product_title = review.product.title if review.product else "Product"
                review.delete()
                self.message_user(
                    request,
                    f"Successfully deleted review for '{product_title}'.",
                    messages.SUCCESS
                )
        except Exception as e:
            self.message_user(
                request,
                f"Error deleting review: {str(e)}",
                messages.ERROR
            )
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../..'))

    @display(description=_('Rating'))
    def display_rating(self, obj):
        return format_html(
            '<span style="font-weight: bold; color: {};">{} ★</span>',
            '#ef4444' if obj.rating <= 2 else ('#f59e0b' if obj.rating == 3 else '#10b981'),
            obj.rating
        )

    @display(description=_('Product'))
    def display_product(self, obj):
        if obj.product:
            return obj.product.title
        return "-"

    @display(description=_('Seller'))
    def display_seller(self, obj):
        if obj.product and obj.product.seller:
            return obj.product.seller.shop_name
        return "-"

    @display(description=_('Buyer'))
    def display_buyer(self, obj):
        if obj.user:
            name = f"{obj.user.first_name} {obj.user.last_name}".strip()
            return f"{name} ({obj.user.email})" if name else obj.user.email
        return "-"

    @display(description=_('Comment'))
    def short_comment(self, obj):
        if not obj.comment:
            return "-"
        return obj.comment[:60] + ("..." if len(obj.comment) > 60 else "")
