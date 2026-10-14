from django.contrib import admin, messages
from django.db import transaction
from django.http import HttpResponseRedirect
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import action, display
from unfold.enums import ActionVariant

from ..models import Dispute, Order
from ..services import process_order_refund


def pending_orders_count(request):
    return Order.objects.filter(status='PENDING').count() or None


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = [
        'order_number',
        'display_buyer',
        'display_seller',
        'display_price_breakdown',
        'display_total',
        'display_status',
        'is_accepted_by_buyer',
        'created_at',
    ]
    list_filter = ['status', 'is_accepted_by_buyer',
                   'fault_party', 'created_at']
    search_fields = ['order_number', 'buyer__email',
                     'seller__shop_name', 'tracking_number']

    readonly_fields = [
        'buyer', 'seller', 'seller_product', 'listing',
        'unit_price', 'quantity', 'discount_amount', 'item_total',
        'shipping_fee', 'service_fee', 'total_price', 'currency',
        'is_accepted_by_buyer', 'accepted_at', 'refund_amount', 'created_at', 'updated_at'
    ]

    fieldsets = (
        (_('🛒 Order Info'), {
            'fields': ('buyer', 'seller', 'seller_product', 'status'),
        }),
        (_('💰 Pricing Breakdown'), {
            'fields': (
                'quantity', 'unit_price', 'discount_amount',
                'item_total', 'shipping_fee', 'service_fee', 'total_price', 'currency'
            ),
            'description': _('Detailed breakdown of payments and fees.')
        }),
        (_('🚚 Shipping & Delivery'), {
            'fields': ('shipping_address', 'tracking_number', 'note'),
        }),
        (_('✅ Acceptance & Refund'), {
            'fields': ('is_accepted_by_buyer', 'accepted_at', 'fault_party', 'refund_amount'),
        }),
    )

    @display(description=_('Buyer'))
    def display_buyer(self, obj):
        return format_html('{}<br><small>{}</small>', obj.buyer.name, obj.buyer.email)

    @display(description=_('Shop'))
    def display_seller(self, obj):
        return obj.seller.shop_name if obj.seller else "—"

    @display(description=_('Breakdown (Item+Ship+Fee)'))
    def display_price_breakdown(self, obj):
        return format_html(
            '<small>Item: ${}</small><br>'
            '<small>Ship: ${}</small><br>'
            '<small style="color: #6366f1;">Fee: ${}</small>',
            f'{obj.item_total:,.2f}',
            f'{obj.shipping_fee:,.2f}',
            f'{obj.service_fee:,.2f}'
        )

    @display(description=_('Grand Total'))
    def display_total(self, obj):
        return format_html('<strong style="color: #10b981;">${}</strong>', f'{obj.total_price:,.2f}')

    @display(description=_('Status'), label={
        'PENDING': 'warning',
        'CONFIRMED': 'info',
        'SHIPPED': 'info',
        'ACCEPTED': 'success',
        'CANCELLED': 'danger',
        'REFUNDED': 'danger',
    })
    def display_status(self, obj):
        return obj.status

    def has_delete_permission(self, request, obj=None):
        return False

    actions = ['refund_seller_fault', 'refund_buyer_fault']

    @action(description=_("Refund Selected - Seller Fault"), permissions=["change"])
    def refund_seller_fault(self, request, queryset):
        success_count = 0
        for order in queryset:
            if order.status in ['PENDING', 'ACCEPTED', 'PROCESSING', 'SHIPPED', 'DELIVERED', 'DISPUTED']:
                try:
                    process_order_refund(order, 'SELLER')
                    success_count += 1
                except Exception as e:
                    self.message_user(request, f"Error refunding order #{order.order_number}: {str(e)}", messages.ERROR)
            else:
                self.message_user(request, f"Order #{order.order_number} cannot be refunded (status: {order.status})", messages.WARNING)
        if success_count > 0:
            self.message_user(request, f"Successfully processed {success_count} refunds with SELLER fault.", messages.SUCCESS)

    @action(description=_("Refund Selected - Buyer Fault"), permissions=["change"])
    def refund_buyer_fault(self, request, queryset):
        success_count = 0
        for order in queryset:
            if order.status in ['PENDING', 'ACCEPTED', 'PROCESSING', 'SHIPPED', 'DELIVERED', 'DISPUTED']:
                try:
                    process_order_refund(order, 'BUYER')
                    success_count += 1
                except Exception as e:
                    self.message_user(request, f"Error refunding order #{order.order_number}: {str(e)}", messages.ERROR)
            else:
                self.message_user(request, f"Order #{order.order_number} cannot be refunded (status: {order.status})", messages.WARNING)
        if success_count > 0:
            self.message_user(request, f"Successfully processed {success_count} refunds with BUYER fault.", messages.SUCCESS)


@admin.register(Dispute)
class DisputeAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = [
        'display_order',
        'id',
        'reason',
        'status',
        'created_at',
    ]
    list_filter = ['status', 'created_at']
    search_fields = ['order__order_number', 'reason', 'description']
    readonly_fields = ['order', 'reason', 'description', 'evidence_image', 'created_at']

    fieldsets = (
        (_('⚖️ Dispute Details'), {
            'fields': ('order', 'status', 'admin_note'),
        }),
        (_('📄 Description & Evidence'), {
            'fields': ('reason', 'description', 'evidence_image', 'created_at'),
        }),
    )

    actions = ['resolve_seller_fault', 'resolve_buyer_fault', 'reject_disputes']
    actions_row = ['resolve_seller_fault_row', 'resolve_buyer_fault_row', 'reject_dispute_row']
    actions_detail = ['resolve_seller_fault_row', 'resolve_buyer_fault_row', 'reject_dispute_row']

    @action(description=_("Resolve Selected - Seller Fault"), permissions=["change"])
    def resolve_seller_fault(self, request, queryset):
        success_count = 0
        for dispute in queryset:
            if dispute.status == 'OPEN':
                try:
                    with transaction.atomic():
                        dispute.status = 'RESOLVED'
                        dispute.save()
                        process_order_refund(dispute.order, 'SELLER')
                        success_count += 1
                except Exception as e:
                    self.message_user(request, f"Error resolving dispute #{dispute.id}: {str(e)}", messages.ERROR)
            else:
                self.message_user(request, f"Dispute #{dispute.id} is already {dispute.status}.", messages.WARNING)
        if success_count > 0:
            self.message_user(request, f"Successfully resolved {success_count} disputes with SELLER fault.", messages.SUCCESS)

    @action(description=_("Resolve Selected - Buyer Fault"), permissions=["change"])
    def resolve_buyer_fault(self, request, queryset):
        success_count = 0
        for dispute in queryset:
            if dispute.status == 'OPEN':
                try:
                    with transaction.atomic():
                        dispute.status = 'RESOLVED'
                        dispute.save()
                        process_order_refund(dispute.order, 'BUYER')
                        success_count += 1
                except Exception as e:
                    self.message_user(request, f"Error resolving dispute #{dispute.id}: {str(e)}", messages.ERROR)
            else:
                self.message_user(request, f"Dispute #{dispute.id} is already {dispute.status}.", messages.WARNING)
        if success_count > 0:
            self.message_user(request, f"Successfully resolved {success_count} disputes with BUYER fault.", messages.SUCCESS)

    @action(description=_("Reject Selected Disputes"), permissions=["change"])
    def reject_disputes(self, request, queryset):
        success_count = 0
        for dispute in queryset:
            if dispute.status == 'OPEN':
                try:
                    with transaction.atomic():
                        dispute.status = 'REJECTED'
                        dispute.save()
                        order = dispute.order
                        order.status = 'SHIPPED'
                        order.save()
                        success_count += 1
                except Exception as e:
                    self.message_user(request, f"Error rejecting dispute #{dispute.id}: {str(e)}", messages.ERROR)
            else:
                self.message_user(request, f"Dispute #{dispute.id} is already {dispute.status}.", messages.WARNING)
        if success_count > 0:
            self.message_user(request, f"Successfully rejected {success_count} disputes (orders set back to SHIPPED).", messages.SUCCESS)

    @action(description=_("Resolve - Seller Fault"), url_path='resolve-seller-fault', icon='gavel', variant=ActionVariant.SUCCESS)
    def resolve_seller_fault_row(self, request, object_id):
        dispute = self.get_object(request, object_id)
        if dispute.status == 'OPEN':
            try:
                with transaction.atomic():
                    dispute.status = 'RESOLVED'
                    dispute.save()
                    process_order_refund(dispute.order, 'SELLER')
                self.message_user(request, f"Dispute resolved. Refunded full amount to buyer due to seller fault.", messages.SUCCESS)
            except Exception as e:
                self.message_user(request, f"Error: {str(e)}", messages.ERROR)
        else:
            self.message_user(request, f"Dispute is already {dispute.status}.", messages.WARNING)
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../..'))

    @action(description=_("Resolve - Buyer Fault"), url_path='resolve-buyer-fault', icon='person', variant=ActionVariant.SUCCESS)
    def resolve_buyer_fault_row(self, request, object_id):
        dispute = self.get_object(request, object_id)
        if dispute.status == 'OPEN':
            try:
                with transaction.atomic():
                    dispute.status = 'RESOLVED'
                    dispute.save()
                    process_order_refund(dispute.order, 'BUYER')
                self.message_user(request, f"Dispute resolved. Refunded item total only due to buyer fault.", messages.SUCCESS)
            except Exception as e:
                self.message_user(request, f"Error: {str(e)}", messages.ERROR)
        else:
            self.message_user(request, f"Dispute is already {dispute.status}.", messages.WARNING)
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../..'))

    @action(description=_("Reject Dispute"), url_path='reject-dispute', icon='cancel', variant=ActionVariant.DANGER)
    def reject_dispute_row(self, request, object_id):
        dispute = self.get_object(request, object_id)
        if dispute.status == 'OPEN':
            try:
                with transaction.atomic():
                    dispute.status = 'REJECTED'
                    dispute.save()
                    order = dispute.order
                    order.status = 'SHIPPED'
                    order.save()
                self.message_user(request, f"Dispute rejected. Order status set back to SHIPPED.", messages.SUCCESS)
            except Exception as e:
                self.message_user(request, f"Error: {str(e)}", messages.ERROR)
        else:
            self.message_user(request, f"Dispute is already {dispute.status}.", messages.WARNING)
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../..'))

    @display(description=_('Order'))
    def display_order(self, obj):
        return obj.order.order_number
