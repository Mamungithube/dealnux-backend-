from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display
from django.utils.html import format_html
from .models import CareerApplication


@admin.register(CareerApplication)
class CareerApplicationAdmin(ModelAdmin):
    list_display = (
        'full_name', 'email', 'phone', 'role',
        'display_status', 'display_resume', 'applied_at'
    )
    list_filter = ('status', 'role')
    search_fields = ('full_name', 'email', 'phone')
    ordering = ('-applied_at',)
    readonly_fields = ('full_name', 'email', 'phone', 'role',
                       'experience', 'why_join', 'resume',
                       'portfolio_url', 'linkedin_url', 'applied_at')
    list_filter_submit = True
    list_fullwidth = True
    actions = ['mark_accepted', 'mark_rejected', 'mark_reviewed']

    @display(description='Status')
    def display_status(self, obj):
        colors = {
            'pending': 'gray',
            'reviewed': 'blue',
            'accepted': 'green',
            'rejected': 'red',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )

    @display(description='Resume')
    def display_resume(self, obj):
        if obj.resume:
            return format_html(
                '<a href="{}" target="_blank" style="color: blue;">Download CV</a>',
                obj.resume.url
            )
        return "No CV"

    def mark_accepted(self, request, queryset):
        queryset.update(status='accepted')
    mark_accepted.short_description = "Mark as Accepted"

    def mark_rejected(self, request, queryset):
        queryset.update(status='rejected')
    mark_rejected.short_description = "Mark as Rejected"

    def mark_reviewed(self, request, queryset):
        queryset.update(status='reviewed')
    mark_reviewed.short_description = "Mark as Reviewed"