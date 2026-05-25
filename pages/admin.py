from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display
from django.utils.html import format_html
from .models import PressCoverage


@admin.register(PressCoverage)
class PressCoverageAdmin(ModelAdmin):
    list_display = (
        'source_name', 'display_logo', 'published_date',
        'display_featured', 'created_at'
    )
    list_filter = ('is_featured',)
    search_fields = ('source_name', 'excerpt')
    readonly_fields = ('created_at', 'display_logo')
    list_filter_submit = True
    list_fullwidth = True

    @display(description='Logo')
    def display_logo(self, obj):
        if obj.source_logo:
            return format_html(
                '<img src="{}" style="width: 40px; height: 40px; '
                'object-fit: contain; border-radius: 4px;" />',
                obj.source_logo.url
            )
        return format_html('<span style="color: gray;">No Logo</span>')

    @display(description='Featured')
    def display_featured(self, obj):
        if obj.is_featured:
            return format_html(
                '<span style="color: green; font-weight: bold;">✔ Featured</span>'
            )
        return format_html(
            '<span style="color: gray;">Not Featured</span>'
        )