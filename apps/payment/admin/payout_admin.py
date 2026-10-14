from account.utils.admin_permissions import ManagerOnlyMixin
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import RangeDateFilter
from unfold.decorators import action, display
from unfold.enums import ActionVariant

from ..models import SellerPayout


@admin.register(SellerPayout)
class SellerPayoutAdmin(ManagerOnlyMixin, ModelAdmin):
    compressed_fields   = True
    list_fullwidth      = True
    list_filter_submit  = True

    list_display = [
        'display_seller',
        'display_amounts',
        'id',
        'display_status',
        'display_transfer',
        'created_at',
    ]

    list_filter = [
        'status',
        ('created_at', RangeDateFilter),
    ]

    search_fields = [
        'seller__shop_name',
        'seller__user__email',
        'stripe_transfer_id',
        'stripe_account_id',
    ]

    readonly_fields = [
        'gross_amount',
        'platform_fee_amount',
        'seller_amount',
        'stripe_transfer_id',
        'stripe_payout_id',
        'created_at',
        'updated_at',
    ]

    fieldsets = (
        ('Seller', {
            'fields': ('seller', 'stripe_account_id'),
        }),
        ('Order & Payment', {
            'fields': ('payment', 'order'),
        }),
        ('Amounts', {
            'fields': (
                'gross_amount',
                'platform_fee_percent', 'platform_fee_amount',
                'seller_amount',
            ),
        }),
        ('Stripe Transfer', {
            'fields': ('stripe_transfer_id', 'stripe_payout_id'),
        }),
        ('Status', {
            'fields': ('status', 'failure_reason'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
        }),
    )

    def has_module_permission(self, request):
        return request.user.is_superuser or request.user.groups.filter(name='Manager').exists()
    
    def has_change_permission(self, request, obj=None):
        if request.user.groups.filter(name='Admin_Associate').exists():
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if request.user.groups.filter(name='Admin_Associate').exists():
            return False
        return super().has_delete_permission(request, obj)

    @action(description=_('Approve & Transfer'), url_path='approve-request', icon='check_circle', variant=ActionVariant.SUCCESS)
    def action_approve_row(self, request, object_id):
        if request.user.groups.filter(name='Admin_Associate').exists():
            self.message_user(request, "Permission Denied: Admin Associates cannot approve payouts.", level='error')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../..'))

        payout = self.get_object(request, object_id)
        if not payout:
            self.message_user(request, "Payout request not found.", level='error')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../..'))

        if payout.status == 'COMPLETED':
            self.message_user(request, "This payout is already completed.", level='warning')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../..'))

        seller = payout.seller
        if seller.stripe_account_id and seller.stripe_onboarding_completed:
            try:
                import stripe
                transfer = stripe.Transfer.create(
                    amount=int(payout.seller_amount * 100),
                    currency='usd',
                    destination=seller.stripe_account_id,
                    metadata={'payout_id': payout.id, 'seller_id': seller.id}
                )
                payout.stripe_transfer_id = transfer.id
                payout.status = 'COMPLETED'
                payout.save(update_fields=['stripe_transfer_id', 'status', 'updated_at'])
                self.message_user(request, f"Successfully transferred ${payout.seller_amount} via Stripe to {seller.shop_name}!", level='success')
            except Exception as e:
                payout.status = 'FAILED'
                payout.failure_reason = str(e)
                payout.save(update_fields=['status', 'failure_reason', 'updated_at'])
                self.message_user(request, f"Stripe Transfer Error: {str(e)}", level='error')
        else:
            payout.status = 'COMPLETED'
            payout.save(update_fields=['status', 'updated_at'])
            self.message_user(request, f"Approved payout of ${payout.seller_amount} for {seller.shop_name} (Manual payment / No Stripe Account).", level='info')

        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../..'))

    @action(description=_('Reject & Refund Balance'), url_path='reject-request', icon='cancel', variant=ActionVariant.DANGER)
    def action_reject_row(self, request, object_id):
        if request.user.groups.filter(name='Admin_Associate').exists():
            self.message_user(request, "Permission Denied: Admin Associates cannot reject payouts.", level='error')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../..'))

        payout = self.get_object(request, object_id)
        if not payout or payout.status in ['COMPLETED', 'FAILED']:
            self.message_user(request, "Payout cannot be rejected or is already processed.", level='warning')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../..'))

        seller = payout.seller
        seller.available_balance += payout.seller_amount
        seller.total_withdrawn -= payout.seller_amount
        seller.save(update_fields=['available_balance', 'total_withdrawn'])

        payout.status = 'FAILED'
        payout.failure_reason = 'Rejected by Admin'
        payout.save(update_fields=['status', 'failure_reason', 'updated_at'])

        self.message_user(request, f"Rejected payout request of ${payout.seller_amount}. Balance restored to seller.", level='info')
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../..'))

    @display(description='Seller')
    def display_seller(self, obj):
        return format_html(
            '<span style="font-weight:500">{}</span><br>'
            '<small style="color:#888">{}</small>',
            obj.seller.shop_name,
            obj.seller.user.email,
        )

    @display(description='Amounts')
    def display_amounts(self, obj):
        return format_html(
            '<span style="font-weight:600;color:#10b981">{}</span>'
            '<br><small style="color:#888">Fee: {} ({}%)</small>',
            obj.seller_amount,
            obj.platform_fee_amount,
            obj.platform_fee_percent,
        )

    @display(description='Status')
    def display_status(self, obj):
        colors = {
            'PENDING':    '#f59e0b',
            'PROCESSING': '#3b82f6',
            'COMPLETED':  '#10b981',
            'FAILED':     '#ef4444',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:3px 10px;border-radius:999px;font-size:11px;font-weight:600">{}</span>',
            color, obj.status
        )

    @display(description='Transfer ID')
    def display_transfer(self, obj):
        if obj.stripe_transfer_id:
            return format_html('<code style="font-size:11px">{}</code>', obj.stripe_transfer_id)
        if obj.failure_reason:
            return format_html('<span style="color:#ef4444;font-size:11px">{}</span>', obj.failure_reason[:50])
        return '—'
