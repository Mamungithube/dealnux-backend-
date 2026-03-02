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
class CustomAdAdmin(ModelAdmin):
    # ড্যাশবোর্ডে যা যা দেখাবে
    list_display = (
        'id', 'title', 'target_section', 'advertiser', 'status', 'is_approved',
        'total_budget', 'spent_amount', 'clicks', 'impressions',
        'start_date', 'end_date',
    )

    list_filter = (
        'status', 'is_approved', 'is_premium', 'target_section',
        'start_date', 'end_date',
    )

    search_fields = ('title', 'advertiser__email', 'target_section')

    # সমাধান: created_at এবং updated_at অবশ্যই readonly_fields এ থাকতে হবে
    readonly_fields = ('clicks', 'impressions', 'created_at', 'updated_at', 'spent_amount')

    fieldsets = (
        ('Ad Info', {
            'fields': (
                'advertiser', 'title', 'target_section', 'description',
                'image', 'target_url', 'cta_text',
            )
        }),
        ('Budget & Priority', {
            'fields': (
                'total_budget', 'spent_amount',
                'priority_weight', 'is_premium',
            )
        }),
        ('Status & Approval', {
            'fields': (
                'status', 'is_approved',
                'start_date', 'end_date',
            )
        }),
        ('Performance (Read Only)', {
            'fields': ('clicks', 'impressions')
        }),
        ('Meta Data', {
            'fields': ('created_at', 'updated_at'),
        }),
    )

    ordering = ('-created_at',)
    list_filter_submit = True
    list_fullwidth = True

    actions = ['approve_ads', 'reject_ads'] # অ্যাকশনগুলো এখানে যুক্ত করুন

    @action(description="✅ Approve and Activate selected ads")
    def approve_ads(self, request, queryset):
        # একসাথে অনেকগুলো অ্যাড আপডেট হবে
        count = queryset.update(is_approved=True, status='active')
        self.message_user(request, f"সফলভাবে {count}টি অ্যাড অ্যাপ্রুভ এবং একটিভ করা হয়েছে।")

    @action(description="❌ Reject selected ads")
    def reject_ads(self, request, queryset):
        count = queryset.update(is_approved=False, status='rejected')
        self.message_user(request, f"{count}টি অ্যাড রিজেক্ট করা হয়েছে।")


    def save_model(self, request, obj, form, change):
        # যদি অ্যাপ্রুভ টিক দেয়া হয় এবং স্ট্যাটাস পেন্ডিং থাকে
        if obj.is_approved and obj.status == 'pending':
            obj.status = 'active'
        
        # যদি অ্যাপ্রুভ টিক তুলে দেয়া হয় এবং স্ট্যাটাস একটিভ থাকে
        elif not obj.is_approved and obj.status == 'active':
            obj.status = 'pending'
            
        super().save_model(request, obj, form, change)

    list_editable = ('status', 'is_approved')

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