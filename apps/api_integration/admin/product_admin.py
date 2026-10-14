from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count, Min, Q

from ..models import Product, ProductImage, ProductSpecification, ProductListing


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
    readonly_fields = ['external_url_link', 'view_link']  
    can_delete = False

    @display(description='URL')
    def external_url_link(self, obj):
        if obj.external_url:
            return format_html('<a href="{}" target="_blank">🔗 View</a>', obj.external_url)
        return format_html('<span style="color:red;">No URL</span>')

    @display(description='View') 
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
    readonly_fields = ['created_at', 'updated_at', 'last_synced', 'image_preview']
    date_hierarchy = 'created_at'
    list_per_page = 20 
    inlines = [ProductListingInline, ProductImageInline, ProductSpecificationInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'category',
        ).annotate(
            _listings_count=Count(
                'listings',
                filter=Q(listings__is_available=True),
                distinct=True
            ),
            _lowest_price=Min('listings__price'),
        )

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
            return format_html(
                '<img src="{}" style="max-height: 50px; border-radius: 5px;" />',
                obj.main_image
            )
        return format_html('<span style="color: gray;">No Image</span>')

    @display(description='Preview')
    def image_preview(self, obj):
        if obj.main_image:
            return format_html(
                '<img src="{}" style="max-height: 200px; border-radius: 10px;" />',
                obj.main_image
            )
        return 'No image'

    @display(description='Lowest Price', ordering='_lowest_price')
    def lowest_price_display(self, obj):
        price = obj._lowest_price  
        if price:
            return format_html(
                '<span style="color: green; font-weight: bold; font-size: 14px;">${}</span>',
                price
            )
        return format_html('<span style="color: gray;">N/A</span>')

    @display(description='Listings')
    def listings_count(self, obj):
        count = obj._listings_count 
        if count > 0:
            return format_html(
                '<span style="background: #4CAF50; color: white; padding: 3px 8px; border-radius: 12px;">{}</span>',
                count
            )
        return format_html('<span style="color: gray;">0</span>')

    actions = ['activate_products', 'deactivate_products', 'sync_prices']

    @admin.action(description='Activate selected products')
    def activate_products(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} products activated successfully.')

    @admin.action(description='Deactivate selected products')
    def deactivate_products(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} products deactivated successfully.')

    @admin.action(description='Sync prices from platforms')
    def sync_prices(self, request, queryset):
        self.message_user(request, f'Price sync initiated for {queryset.count()} products.')


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
