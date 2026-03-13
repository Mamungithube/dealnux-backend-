from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import (
    Platform, Category, Product, ProductListing,
    ProductImage, ProductSpecification, PriceHistory
)


@admin.register(Platform)
class PlatformAdmin(ModelAdmin):
    list_display = ['name', 'code', 'api_enabled',
                    'listings_count', 'created_at']
    list_filter = ['api_enabled', 'created_at']
    search_fields = ['name', 'code']
    readonly_fields = ['created_at', 'updated_at']

    @display(description='Active Listings')
    def listings_count(self, obj):
        count = obj.listings.filter(is_available=True).count()
        return format_html('<span style="color: green; font-weight: bold;">{}</span>', count)


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ['name', 'slug', 'parent', 'products_count', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at', 'updated_at']

    @display(description='Products')
    def products_count(self, obj):
        return obj.products.count()


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ['image_url', 'alt_text', 'order', 'image_preview']
    readonly_fields = ['image_preview']

    @display(description='Preview')
    def image_preview(self, obj):
        if obj.image_url:
            return format_html(
                '<img src="{}" style="max-height:50px; max-width:100px;" />',
                obj.image_url
            )
        return format_html('<span style="color:red;">No Image</span>')


class ProductSpecificationInline(admin.TabularInline):
    model = ProductSpecification
    extra = 1
    fields = ['name', 'value']


class ProductListingInline(admin.TabularInline):
    model = ProductListing
    extra = 0
    fields = ['platform', 'price', 'currency', 'condition', 'seller_username', 'is_available', 'external_url_link', 'view_link']
    readonly_fields = ['external_url_link', 'view_link']  # দুটোই method হিসেবে থাকতে হবে
    can_delete = False

    @display(description='URL')
    def external_url_link(self, obj):
        if obj.external_url:
            return format_html('<a href="{}" target="_blank">🔗 View</a>', obj.external_url)
        return format_html('<span style="color:red;">No URL</span>')

    @display(description='View')  # ← এই method টা add করুন
    def view_link(self, obj):
        if obj.pk:
            url = reverse('admin:api_integration_productlisting_change', args=[obj.pk])
            return format_html('<a href="{}" target="_blank">Details</a>', url)
        return '-'

@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ['image_thumb', 'title', 'category', 'brand',
                    'lowest_price_display', 'listings_count', 'is_active', 'last_synced']
    list_filter = ['is_active', 'category', 'brand', 'created_at']
    search_fields = ['title', 'brand', 'model_number', 'description']
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ['created_at', 'updated_at',
                       'last_synced', 'image_preview']
    date_hierarchy = 'created_at'

    inlines = [ProductListingInline,
               ProductImageInline, ProductSpecificationInline]

    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'slug', 'description', 'category')
        }),
        ('Product Details', {
            'fields': ('brand', 'model_number')
        }),
        ('Images', {
            'fields': ('main_image', 'image_preview')
        }),
        ('Status', {
            'fields': ('is_active', 'created_at', 'updated_at', 'last_synced')
        }),
    )

    @display(description='Image')
    def image_thumb(self, obj):
        if obj.main_image:
            return format_html('<img src="{}" style="max-height: 50px; border-radius: 5px;" />', obj.main_image)
        return format_html('<span style="color: gray;">No Image</span>')

    @display(description='Preview')
    def image_preview(self, obj):
        if obj.main_image:
            return format_html('<img src="{}" style="max-height: 200px; border-radius: 10px;" />', obj.main_image)
        return 'No image'

    @display(description='Lowest Price', ordering='listings__price')
    def lowest_price_display(self, obj):
        price = obj.get_lowest_price()
        if price:
            return format_html('<span style="color: green; font-weight: bold; font-size: 14px;">${}</span>', price)
        return format_html('<span style="color: gray;">N/A</span>')

    @display(description='Listings')
    def listings_count(self, obj):
        count = obj.listings.filter(is_available=True).count()
        if count > 0:
            return format_html('<span style="background: #4CAF50; color: white; padding: 3px 8px; border-radius: 12px;">{}</span>', count)
        return format_html('<span style="color: gray;">0</span>')

    actions = ['activate_products', 'deactivate_products', 'sync_prices']

    @admin.action(description='Activate selected products')
    def activate_products(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(
            request, f'{updated} products activated successfully.')

    @admin.action(description='Deactivate selected products')
    def deactivate_products(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(
            request, f'{updated} products deactivated successfully.')

    @admin.action(description='Sync prices from platforms')
    def sync_prices(self, request, queryset):
        # TODO: Implement price sync logic
        self.message_user(
            request, f'Price sync initiated for {queryset.count()} products.')


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
        # TODO: Implement price update logic
        self.message_user(
            request, f'Price update initiated for {queryset.count()} listings.')


@admin.register(ProductImage)
class ProductImageAdmin(ModelAdmin):
    list_display = ['product', 'image_thumbnail', 'order', 'created_at']
    list_filter = ['created_at']
    search_fields = ['product__title', 'alt_text']
    readonly_fields = ['created_at', 'image_preview']

    @display(description='Thumbnail')
    def image_thumbnail(self, obj):
        if obj.image_url:
            return format_html('<img src="{}" style="max-height: 40px;" />', obj.image_url)
        return '-'

    @display(description='Preview')
    def image_preview(self, obj):
        if obj.image_url:
            return format_html('<img src="{}" style="max-height: 300px;" />', obj.image_url)
        return 'No image'


@admin.register(ProductSpecification)
class ProductSpecificationAdmin(ModelAdmin):
    list_display = ['product', 'name', 'value', 'created_at']
    list_filter = ['name', 'created_at']
    search_fields = ['product__title', 'name', 'value']
    readonly_fields = ['created_at']


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
