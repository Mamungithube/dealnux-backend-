from django.contrib import admin
from django.utils.html import format_html
from .models import CustomAd, AdvertiserRequest,AdReview
from decimal import Decimal

@admin.register(AdvertiserRequest)
class AdvertiserRequestAdmin(admin.ModelAdmin):
    list_display = (
        'id','business_name', 'user_email', 'website', 
        'is_reviewed', 'applied_at', 'action_buttons'
    )
    list_filter = ('is_reviewed', 'applied_at')
    search_fields = ('user__email', 'business_name', 'user__Fullname')
    readonly_fields = ('applied_at', 'reviewed_at')
    actions = ['approve_requests', 'reject_requests']

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User Email'

    def action_buttons(self, obj):
        if not obj.is_reviewed:
            return format_html(
                '<a class="button" href="#">Pending Review</a>'
            )
        return format_html('<span style="color:green;">✓ Reviewed</span>')
    action_buttons.short_description = 'Status'

    @admin.action(description="✅ Approve selected requests")
    def approve_requests(self, request, queryset):
        count = 0
        for req in queryset.filter(is_reviewed=False):
            req.approve()
            count += 1
        self.message_user(request, f"{count} advertisers approved successfully.")

    @admin.action(description="❌ Reject selected requests")
    def reject_requests(self, request, queryset):
        count = queryset.update(is_reviewed=True)
        self.message_user(request, f"{count} requests rejected.")


@admin.register(CustomAd)
class CustomAdAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'title',
        'advertiser',
        'status',
        'is_approved',
        'total_budget',
        'spent_amount',
        'budget_remaining',
        'clicks',
        'impressions',
        'ctr',
        'start_date',
        'end_date',
    )

    list_filter = (
        'status',
        'is_approved',
        'is_premium',
        'start_date',
        'end_date',
    )

    search_fields = (
        'title',
        'advertiser__email',
    )

    readonly_fields = (
        'clicks',
        'impressions',
        'created_at',
        'updated_at',
    )

    fieldsets = (
        ('Ad Info', {
            'fields': (
                'advertiser',
                'title',
                'description',
                'image',
                'target_url',
                'cta_text',
            )
        }),
        ('Budget & Priority', {
            'fields': (
                'total_budget',
                'spent_amount',
                'priority_weight',
                'is_premium',
            )
        }),
        ('Status & Approval', {
            'fields': (
                'status',
                'is_approved',
                'start_date',
                'end_date',
            )
        }),
        ('Performance (Read Only)', {
            'fields': (
                'clicks',
                'impressions',
            )
        }),
        ('Meta', {
            'fields': (
                'created_at',
                'updated_at',
            )
        }),
    )

    ordering = ('-created_at',)


@admin.register(AdReview)
class AdReviewAdmin(admin.ModelAdmin):
    list_display = ('id', 'ad','reviewed_at', 'status', 'feedback')
    list_filter = ('reviewed_at', 'status')
    search_fields = ('ad__title', 'reviewer__email')
    readonly_fields = ('reviewed_at',)

    def reviewer_email(self, obj):
        return obj.reviewer.email
    reviewer_email.short_description = 'Reviewer'

    def action(self, obj):
        return obj.get_action_display()
    action.short_description = 'Action' 