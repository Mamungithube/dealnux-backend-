from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display
from django.utils.html import format_html
from django.urls import reverse

from ..models import ProductListing, PriceHistory


class PriceHistoryInline(admin.TabularInline):
    model = PriceHistory
    extra = 0
    fields = ['price', 'currency', 'recorded_at']
    readonly_fields = ['price', 'currency', 'recorded_at']
    can_delete = False
    ordering = ['-recorded_at']

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ProductListing)
class ProductListingAdmin(ModelAdmin):
    list_display = ['product_title', 'external_url_link', 'platform', 'price_display',
                    'condition', 'seller_info', 'quantity', 'is_available', 'last_checked']
    list_filter = ['platform', 'condition', 'is_available',
                   'returns_accepted', 'free_shipping', 'created_at']
    search_fields = ['product__title', 'external_id', 'seller_username']
    readonly_fields = ['created_at', 'updated_at',
                       'last_checked', 'total_price_display', 'external_link']
    date_hierarchy = 'created_at'

    inlines = [PriceHistoryInline]

    fieldsets = (
        ('Product & Platform', {
            'fields': ('product', 'platform', 'external_id', 'external_url', 'external_link')
        }),
        ('Pricing', {
            'fields': ('price', 'currency', 'original_price', 'discount_percentage', 'total_price_display')
        }),
        ('Product Details', {
            'fields': ('condition', 'quantity')
        }),
        ('Seller Information', {
            'fields': ('seller_username', 'seller_rating', 'seller_feedback_count')
        }),
        ('Location & Shipping', {
            'fields': ('item_location', 'ships_from_country', 'shipping_cost', 'shipping_currency', 'free_shipping', 'estimated_delivery_days')
        }),
        ('Returns', {
            'fields': ('returns_accepted', 'return_period_days')
        }),
        ('Status', {
            'fields': ('is_available', 'last_checked', 'created_at', 'updated_at')
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'product',
            'platform',
        )
    
    @display(description='External URL')
    def external_url_link(self, obj):
        if obj.external_url:
            return format_html(
                '<a href="{}" target="_blank">🔗 View</a>',
                obj.external_url
            )
        return format_html('<span style="color:gray;">No URL</span>')

    @display(description='Product')
    def product_title(self, obj):
        url = reverse('admin:api_integration_product_change',
                      args=[obj.product.pk])
        return format_html('<a href="{}">{}</a>', url, obj.product.title[:60])

    @display(description='Price', ordering='price')
    def price_display(self, obj):
        html = f'<div style="font-weight: bold; color: #2196F3;">{obj.price} {obj.currency}</div>'
        if obj.original_price:
            html += f'<div style="text-decoration: line-through; color: gray; font-size: 11px;">{obj.original_price} {obj.currency}</div>'
        if obj.discount_percentage:
            html += f'<div style="color: #4CAF50; font-size: 11px;">-{obj.discount_percentage}% OFF</div>'
        return format_html(html)

    @display(description='Total Price')
    def total_price_display(self, obj):
        total = obj.get_total_price()
        return format_html('<span style="font-size: 16px; color: #FF5722; font-weight: bold;">${:.2f}</span>', total)

    @display(description='Seller')
    def seller_info(self, obj):
        html = f'<div>{obj.seller_username}</div>'
        if obj.seller_rating:
            html += f'<div style="color: #FFC107; font-size: 11px;">⭐ {obj.seller_rating}% ({obj.seller_feedback_count})</div>'
        return format_html(html)

    @display(description='External Link')
    def external_link(self, obj):
        if obj.external_url:
            return format_html('<a href="{}" target="_blank" style="color: #2196F3;">🔗 View on {}</a>',
                               obj.external_url, obj.platform.name)
        return '-'

    actions = ['mark_available', 'mark_unavailable', 'update_prices']

    @admin.action(description='Mark as available')
    def mark_available(self, request, queryset):
        updated = queryset.update(is_available=True)
        self.message_user(request, f'{updated} listings marked as available.')

    @admin.action(description='Mark as unavailable')
    def mark_unavailable(self, request, queryset):
        updated = queryset.update(is_available=False)
        self.message_user(
            request, f'{updated} listings marked as unavailable.')

    @admin.action(description='Update prices from API')
    def update_prices(self, request, queryset):
        self.message_user(
            request, f'Price update initiated for {queryset.count()} listings.')


@admin.register(PriceHistory)
class PriceHistoryAdmin(ModelAdmin):
    list_display = ['listing_info', 'price_display', 'recorded_at']
    list_filter = ['currency', 'recorded_at']
    search_fields = ['listing__product__title']
    readonly_fields = ['listing', 'price', 'currency', 'recorded_at']
    date_hierarchy = 'recorded_at'

    @display(description='Listing')
    def listing_info(self, obj):
        return f"{obj.listing.product.title} on {obj.listing.platform.name}"

    @display(description='Price')
    def price_display(self, obj):
        return format_html('<span style="font-weight: bold;">{} {}</span>', obj.price, obj.currency)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'listing__product',
            'listing__platform',
        )
