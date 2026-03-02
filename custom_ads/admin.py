from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display, action
from django.utils.html import format_html
from .models import CustomAd, AdvertiserRequest, AdReview , AdSetting
from decimal import Decimal


@admin.register(AdvertiserRequest)
class AdvertiserRequestAdmin(ModelAdmin):
    list_display = (
        'id', 'business_name', 'user_email', 'website',
        'is_reviewed', 'applied_at', 'action_buttons'
    )
    list_filter = ('is_reviewed', 'applied_at')
    search_fields = ('user__email', 'business_name', 'user__name')
    readonly_fields = ('applied_at', 'reviewed_at')
    actions = ['approve_requests', 'reject_requests']
    
    # Unfold specific
    list_filter_submit = True
    list_fullwidth = True

    @display(description='User Email')
    def user_email(self, obj):
        return obj.user.email

    @display(description='Status')
    def action_buttons(self, obj):
        if not obj.is_reviewed:
            return format_html(
                '<span style="background: #fef3c7; color: #92400e; padding: 4px 12px; border-radius: 6px; font-size: 12px; font-weight: 500;">Pending Review</span>'
            )
        return format_html(
            '<span style="background: #d1fae5; color: #065f46; padding: 4px 12px; border-radius: 6px; font-size: 12px; font-weight: 500;">✓ Reviewed</span>'
        )

    @action(description="✅ Approve selected requests")
    def approve_requests(self, request, queryset):
        count = 0
        for req in queryset.filter(is_reviewed=False):
            req.approve()
            count += 1
        self.message_user(request, f"{count} advertisers approved successfully.")

    @action(description="❌ Reject selected requests")
    def reject_requests(self, request, queryset):
        count = queryset.update(is_reviewed=True)
        self.message_user(request, f"{count} requests rejected.")


@admin.register(AdSetting)
class AdSettingAdmin(ModelAdmin):
    list_display = ('cpc_amount', 'updated_at')

@admin.register(CustomAd)
class CustomAdAdmin(admin.ModelAdmin):
    list_display = ['title', 'advertiser', 'status', 'is_approved', 'created_at']
    list_filter = ['status', 'is_approved']
    actions = ['approve_ads', 'reject_ads']

    def approve_ads(self, request, queryset):
        queryset.update(status='active', is_approved=True)
        self.message_user(request, f"{queryset.count()} ads approved successfully.")
    approve_ads.short_description = "Approve selected ads"

    def reject_ads(self, request, queryset):
        queryset.update(status='rejected', is_approved=False)
        self.message_user(request, f"{queryset.count()} ads rejected.")
    reject_ads.short_description = "Reject selected ads"

@admin.register(AdReview)
class AdReviewAdmin(ModelAdmin):
    list_display = ('id', 'ad', 'reviewed_at', 'status', 'feedback')
    list_filter = ('reviewed_at', 'status')
    search_fields = ('ad__title', 'reviewer__email')
    readonly_fields = ('reviewed_at',)
    
    # Unfold specific
    list_filter_submit = True

    @display(description='Reviewer')
    def reviewer_email(self, obj):
        return obj.reviewer.email

    @display(description='Action')
    def action(self, obj):
        return obj.get_action_display()