from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import display, action
from unfold.enums import ActionVariant
from .models import CustomAd, AdvertiserRequest, AdReview, AdSetting
from django.utils import timezone


def pending_advertiser_requests_count(request):
    count = AdvertiserRequest.objects.filter(is_reviewed=False).count()
    return str(count) if count > 0 else "0"

@admin.register(AdvertiserRequest)
class AdvertiserRequestAdmin(ModelAdmin):
    # ===============================
    # ⚙️ Admin Config
    # ===============================
    list_display = (
        'display_business',
        'id',
        'user_email',
        'website',
        'display_status',
        'applied_at',
        'is_reviewed',
    )

    list_filter = ('is_reviewed', 'applied_at')
    search_fields = ('user__email', 'business_name', 'user__name')

    readonly_fields = ('applied_at', 'reviewed_at')
    list_editable = ('is_reviewed',)
    list_filter_submit = True
    list_fullwidth = True
    compressed_fields = True
    warn_unsaved_form = True

    ordering = ('-applied_at',)

    # ✅ Row ভিত্তিক Action Button
    actions_row = ['action_approve_row', 'action_reject_row']

    # ===============================
    # 🎨 Display সুন্দর করা
    # ===============================
    @display(description='Business')
    def display_business(self, obj):
        return format_html(
            '<div>'
            '<strong>{}</strong><br>'
            '<small style="color:#6b7280">ID: {}</small>'
            '</div>',
            obj.business_name,
            obj.id
        )

    @display(description='User')
    def user_email(self, obj):
        return format_html(
            '<span style="color:#2563eb;font-weight:500">{}</span>',
            obj.user.email
        )

    @display(
        description='Status',
        label={
            'Pending': 'warning',
            'Approved': 'success',
            'Rejected': 'danger'
        }
    )
    def display_status(self, obj):
        if not obj.is_reviewed:
            return "Pending"
        elif obj.user.ads_provided:
            return "Approved"
        return "Rejected"

    # ===============================
    # 🚀 Row Actions
    # ===============================
    @action(
        description='Approve',
        url_path='approve-advertiser',
        icon='check_circle',
        variant=ActionVariant.SUCCESS,
    )
    def action_approve_row(self, request, object_id):
        from django.http import HttpResponseRedirect
        obj = AdvertiserRequest.objects.get(pk=object_id)
        if obj.is_reviewed:
            self.message_user(request, "Already reviewed.", level='warning')
            return HttpResponseRedirect('../..')
        obj.approve()
        self.message_user(request, f'✓ {obj.user.email} approved as advertiser.')
        return HttpResponseRedirect('../..')

    @action(
        description='Reject',
        url_path='reject-advertiser',
        icon='cancel',
        variant=ActionVariant.DANGER,
    )
    def action_reject_row(self, request, object_id):
        from django.http import HttpResponseRedirect
        obj = AdvertiserRequest.objects.get(pk=object_id)
        if obj.is_reviewed:
            self.message_user(request, "Already reviewed.", level='warning')
            return HttpResponseRedirect('../..')
        obj.reject(reason="Rejected by admin")
        self.message_user(request, f'✗ {obj.user.email} request rejected.')
        return HttpResponseRedirect('../..')
    

@admin.register(AdSetting)
class AdSettingAdmin(ModelAdmin):
    list_display = ('display_cpc', 'updated_at')
    readonly_fields = ('updated_at',)
    compressed_fields = True

    fieldsets = (
        ('💰 CPC Settings', {
            'fields': ('cpc_amount', 'updated_at'),
        }),
    )

    @display(description='💰 CPC Amount (per click)')
    def display_cpc(self, obj):
        return format_html(
            '<strong style="color:#16a34a;font-size:18px">${}</strong> &nbsp;'
            '<span style="background:#dcfce7;color:#166534;padding:3px 10px;'
            'border-radius:12px;font-size:12px;font-weight:500">per click</span>',
            obj.cpc_amount,
        )

    def has_add_permission(self, request):
        # শুধু একটাই AdSetting থাকবে
        if AdSetting.objects.exists():
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CustomAd)
class CustomAdAdmin(ModelAdmin):
    def get_queryset(self, request):
            qs = super().get_queryset(request)
            # Admin page load হলে expired ads automatically update হবে
            qs.filter(
                status='active',
                end_date__lt=timezone.now()
            ).update(status='expired')
            return qs

    list_display = (
         'title','id', 'target_section', 'advertiser_email', 'display_status',
        'is_approved', 'total_budget', 'spent_amount', 'clicks', 'impressions',
        'start_date', 'end_date',
    )
    list_filter = (
        'status', 'is_approved', 'is_premium', 'target_section',
        'start_date', 'end_date',
    )
    search_fields = ('title', 'advertiser__email', 'target_section')
    readonly_fields = ('clicks', 'impressions', 'created_at', 'updated_at', 'spent_amount')

    ordering = ('-created_at',)
    list_filter_submit = True
    list_fullwidth = True
    compressed_fields = True
    warn_unsaved_form = True
    # list_editable = ('is_approved')

    fieldsets = (
        ('📢 Ad Info', {
            'fields': (
                'advertiser', 'title', 'target_section', 'description',
                'image', 'target_url', 'cta_text',
            )
        }),
        ('💰 Budget & Priority', {
            'fields': (
                'total_budget', 'spent_amount',
                'priority_weight', 'is_premium',
            )
        }),
        ('⚙️ Status & Approval', {
            'fields': (
                'status', 'is_approved',
                'start_date', 'end_date',
            )
        }),
        ('📊 Performance (Read Only)', {
            'fields': ('clicks', 'impressions')
        }),
        ('🕐 Meta Data', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    actions = ['approve_ads', 'reject_ads']
    actions_row = ['action_approve_ad_row', 'action_reject_ad_row', 'action_pause_ad_row']

    @action(
        description='Approve',
        url_path='approve-ad',
        icon='check_circle',
        variant=ActionVariant.SUCCESS,
    )
    def action_approve_ad_row(self, request, object_id):
        from django.http import HttpResponseRedirect
        CustomAd.objects.filter(pk=object_id).update(is_approved=True, status='active')
        self.message_user(request, f'✓ Ad #{object_id} approved and activated.')
        return HttpResponseRedirect('../..')

    @action(
        description='Reject',
        url_path='reject-ad',
        icon='cancel',
        variant=ActionVariant.DANGER,
    )
    def action_reject_ad_row(self, request, object_id):
        from django.http import HttpResponseRedirect
        CustomAd.objects.filter(pk=object_id).update(is_approved=False, status='rejected')
        self.message_user(request, f'✗ Ad #{object_id} rejected.')
        return HttpResponseRedirect('../..')

    @action(
        description='Pause',
        url_path='pause-ad',
        icon='pause_circle',
        variant=ActionVariant.WARNING,
    )
    def action_pause_ad_row(self, request, object_id):
        from django.http import HttpResponseRedirect
        CustomAd.objects.filter(pk=object_id).update(status='paused')
        self.message_user(request, f'⏸ Ad #{object_id} paused.')
        return HttpResponseRedirect('../..')

    @display(description='Advertiser')
    def advertiser_email(self, obj):
        return format_html(
            '<span style="color:#2563eb;font-weight:500">{}</span>',
            obj.advertiser.email
        )

    @display(
        description='Status',
        ordering='status',
        label={
            'pending':  'warning',
            'active':   'success',
            'paused':   'info',
            'rejected': 'danger',
            'expired':  'danger',
        },
    )
    def display_status(self, obj):
        return obj.status

    @action(description="✅ Approve and Activate selected ads", variant=ActionVariant.SUCCESS)
    def approve_ads(self, request, queryset):
        count = queryset.update(is_approved=True, status='active')
        self.message_user(request, f"{count} ads approved and activated.")

    @action(description="❌ Reject selected ads", variant=ActionVariant.DANGER)
    def reject_ads(self, request, queryset):
        count = queryset.update(is_approved=False, status='rejected')
        self.message_user(request, f"{count} ads rejected.")

    def save_model(self, request, obj, form, change):
        if obj.is_approved and obj.status == 'pending':
            obj.status = 'active'
        elif not obj.is_approved and obj.status == 'active':
            obj.status = 'pending'
        super().save_model(request, obj, form, change)

@admin.register(AdReview)
class AdReviewAdmin(ModelAdmin):
    list_display = ( 'ad', 'reviewed_at', 'display_status', 'feedback','id', 'reviewer_email')
    list_filter = ('reviewed_at', 'status')
    search_fields = ('ad__title', 'reviewer__email')
    readonly_fields = ('reviewed_at',)
    list_filter_submit = True
    compressed_fields = True
    actions_row = ['action_approve_row', 'action_reject_row']

    @action(
        description='Approve',
        url_path='approve-review',
        icon='check_circle',
        variant=ActionVariant.SUCCESS,
    )
    def action_approve_row(self, request, object_id):
        from django.http import HttpResponseRedirect
        AdReview.objects.filter(pk=object_id).update(status='approved')
        self.message_user(request, f'✓ Review #{object_id} approved.')
        return HttpResponseRedirect('../..')

    @action(
        description='Reject',
        url_path='reject-review',
        icon='cancel',
        variant=ActionVariant.DANGER,
    )
    def action_reject_row(self, request, object_id):
        from django.http import HttpResponseRedirect
        AdReview.objects.filter(pk=object_id).update(status='rejected')
        self.message_user(request, f'✗ Review #{object_id} rejected.')
        return HttpResponseRedirect('../..')

    @display(
        description='Status',
        ordering='status',
        label={
            'approved': 'success',
            'rejected': 'danger',
            'pending':  'warning',
        },
    )
    def display_status(self, obj):
        return obj.status

    @display(description='Reviewer')
    def reviewer_email(self, obj):
        return obj.reviewer.email