from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display
from django.utils.html import format_html
from .models import MainSliderBanner, SideBanner


@admin.register(MainSliderBanner)
class MainSliderBannerAdmin(ModelAdmin):
    list_display = ['display_order', 'title', 'display_thumb', 'display_status', 'order', 'updated_at']
    list_display_links = ['title']
    list_editable = ['order']
    list_filter = ['is_active']
    search_fields = ['title']
    readonly_fields = ['display_big_preview', 'created_at', 'updated_at']
    ordering = ['order']

    list_filter_submit = True
    list_fullwidth = True

    fieldsets = (
        ('Banner Info', {
            'description': (
                '<p style="color:#e5e7eb;background:#374151;border-left:4px solid #fbbf24;'
                'padding:10px 14px;margin-bottom:8px;border-radius:0 4px 4px 0;font-size:13px;">'
                '<b style="color:#fbbf24;">Required Size:</b> 920 x 460 px &nbsp;|&nbsp; '
                'Ratio: 2:1 &nbsp;|&nbsp; JPG / PNG / WEBP<br>'
                '<b style="color:#fbbf24;">Max 5 banners</b> can be active at the same time.'
                '</p>'
            ),
            'fields': ('title', 'order', 'is_active'),
        }),
        ('Image', {
            'fields': ('image', 'display_big_preview'),
        }),
        ('System Info', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @display(description='Order', ordering='order')
    def display_order(self, obj):
        return format_html(
            '<span style="font-weight:700;font-size:15px;">#{}</span>',
            obj.order
        )

    @display(description='Preview')
    def display_thumb(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="width:120px;height:60px;object-fit:cover;'
                'border-radius:4px;border:1px solid #e5e7eb;">',
                obj.image.url
            )
        return format_html('<span style="color:#9ca3af;">No image</span>')

    @display(description='Status', label={
        True: 'success',
        False: 'danger',
    })
    def display_status(self, obj):
        return obj.is_active

    @display(description='Image Preview')
    def display_big_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-width:460px;border-radius:6px;'
                'border:1px solid #e5e7eb;display:block;">'
                '<small style="color:#9ca3af;margin-top:6px;display:block;">920 x 460 px</small>',
                obj.image.url
            )
        return format_html('<span style="color:#9ca3af;">Upload an image to preview</span>')


@admin.register(SideBanner)
class SideBannerAdmin(ModelAdmin):
    list_display = ['display_position', 'title', 'display_thumb', 'display_status', 'updated_at']
    list_display_links = ['title']
    list_filter = ['is_active', 'position']
    search_fields = ['title']
    readonly_fields = ['display_big_preview', 'created_at', 'updated_at']
    ordering = ['position']

    list_filter_submit = True
    list_fullwidth = True

    fieldsets = (
        ('Banner Info', {
            'description': (
                '<p style="color:#e5e7eb;background:#374151;border-left:4px solid #38bdf8;'
                'padding:10px 14px;margin-bottom:8px;border-radius:0 4px 4px 0;font-size:13px;">'
                '<b style="color:#38bdf8;">Required Size:</b> 299 x 220 px &nbsp;|&nbsp; '
                'Ratio: 1.36:1 &nbsp;|&nbsp; JPG / PNG / WEBP<br>'
                '<b style="color:#38bdf8;">One active banner per position.</b> '
                'Deactivate the existing one before adding a new banner to the same position.'
                '</p>'
            ),
            'fields': ('title', 'position', 'is_active'),
        }),
        ('Image', {
            'fields': ('image', 'display_big_preview'),
        }),
        ('System Info', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @display(description='Position', ordering='position')
    def display_position(self, obj):
        colors = {1: '#6366f1', 2: '#0ea5e9', 3: '#10b981', 4: '#f59e0b'}
        labels = {1: 'Top Left', 2: 'Top Right', 3: 'Bottom Left', 4: 'Bottom Right'}
        color = colors.get(obj.position, '#6b7280')
        label = labels.get(obj.position, f'Pos {obj.position}')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;'
            'border-radius:999px;font-size:12px;font-weight:600;">{}</span>',
            color, label
        )

    @display(description='Preview')
    def display_thumb(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="width:80px;height:59px;object-fit:cover;'
                'border-radius:4px;border:1px solid #e5e7eb;">',
                obj.image.url
            )
        return format_html('<span style="color:#9ca3af;">No image</span>')

    @display(description='Status', label={
        True: 'success',
        False: 'danger',
    })
    def display_status(self, obj):
        return obj.is_active

    @display(description='Image Preview')
    def display_big_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="width:299px;height:220px;object-fit:cover;'
                'border-radius:6px;border:1px solid #e5e7eb;display:block;">'
                '<small style="color:#9ca3af;margin-top:6px;display:block;">299 x 220 px</small>',
                obj.image.url
            )
        return format_html('<span style="color:#9ca3af;">Upload an image to preview</span>')