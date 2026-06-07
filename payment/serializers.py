from rest_framework import serializers
from .models import Payment, SellerPayout, SubscriptionPlan
from store.models import SellerProduct, Coupon
from decimal import Decimal


# ============================================================================
# Shipping Address (reusable)
# ============================================================================

class ShippingAddressSerializer(serializers.Serializer):
    first_name    = serializers.CharField(max_length=100)
    last_name     = serializers.CharField(max_length=100)
    address_line1 = serializers.CharField(max_length=255)
    address_line2 = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    city          = serializers.CharField(max_length=100)
    state         = serializers.CharField(max_length=100)
    zip_code      = serializers.CharField(max_length=20)
    country       = serializers.CharField(max_length=100)

# ============================================================================
# Checkout
# ============================================================================

class CheckoutSerializer(serializers.Serializer):
    """Buyer → To create a Stripe Checkout Session"""
    seller_product   = serializers.PrimaryKeyRelatedField(
        queryset=SellerProduct.objects.filter(status='APPROVED')
    )
    quantity         = serializers.IntegerField(min_value=1, default=1)
    shipping_address = ShippingAddressSerializer() 
    coupon_code      = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')
    note             = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')

    def validate(self, attrs):
        product  = attrs['seller_product']
        quantity = attrs['quantity']

        if product.quantity < quantity:
            raise serializers.ValidationError({
                'quantity': f'Only {product.quantity} items available.'
            })

        coupon_code = attrs.get('coupon_code', '').strip().upper()
        if coupon_code:
            try:
                coupon = Coupon.objects.get(code=coupon_code, seller=product.seller)
                if not coupon.is_valid:
                    raise serializers.ValidationError({'coupon_code': 'Coupon is expired or invalid.'})
                attrs['coupon'] = coupon
            except Coupon.DoesNotExist:
                raise serializers.ValidationError({'coupon_code': f'Coupon "{coupon_code}" not found.'})

        attrs['coupon_code'] = coupon_code
        return attrs



# ============================================================================
# Payment
# ============================================================================

class PaymentSerializer(serializers.ModelSerializer):
    """Buyer's payment history"""
    product_title   = serializers.CharField(source='seller_product.title', read_only=True, allow_null=True)
    shop_name       = serializers.CharField(source='seller_product.seller.shop_name', read_only=True, allow_null=True)
    order_status    = serializers.CharField(source='order.status', read_only=True, allow_null=True)
    status_display  = serializers.CharField(source='get_status_display', read_only=True)
    shipping_address = serializers.SerializerMethodField()  

    class Meta:
        model  = Payment
        fields = [
            'id',
            'product_title', 'shop_name',
            'quantity',
            'unit_price', 'total_amount', 'discount_amount', 'final_amount', 'currency',
            'coupon_code',
            'status', 'status_display',
            'order_id', 'order_status',
            'stripe_checkout_url',
            'shipping_address', 'note',  
            'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_shipping_address(self, obj):
        return {
            'first_name':    obj.shipping_first_name,
            'last_name':     obj.shipping_last_name,
            'address_line1': obj.shipping_address_line1,
            'address_line2': obj.shipping_address_line2,
            'city':          obj.shipping_city,
            'state':         obj.shipping_state,
            'zip_code':      obj.shipping_zip_code,
            'country':       obj.shipping_country,
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.status != 'PENDING':
            data['stripe_checkout_url'] = None
        return data


class PaymentDetailSerializer(PaymentSerializer):
    """Single payment detail — with stripe ids (admin/buyer himself)"""
    class Meta(PaymentSerializer.Meta):
        fields = PaymentSerializer.Meta.fields + [
            'stripe_checkout_session_id',
            'stripe_payment_intent_id',
        ]



# ============================================================================
# Seller Payout
# ============================================================================

class SellerPayoutSerializer(serializers.ModelSerializer):
    """Seller's payout history"""
    shop_name       = serializers.CharField(source='seller.shop_name', read_only=True)
    order_id        = serializers.IntegerField(source='order.id', read_only=True, allow_null=True)
    status_display  = serializers.CharField(source='get_status_display', read_only=True)
    currency        = serializers.CharField(source='payment.currency', read_only=True)

    class Meta:
        model  = SellerPayout
        fields = [
            'id',
            'shop_name', 'order_id',
            'gross_amount', 'platform_fee_percent', 'platform_fee_amount', 'seller_amount',
            'currency',
            'status', 'status_display',
            'stripe_account_id', 'stripe_transfer_id',
            'failure_reason',
            'created_at',
        ]
        read_only_fields = fields


# ============================================================================
# Stripe Connect
# ============================================================================

class StripeConnectStatusSerializer(serializers.Serializer):
    """Seller Stripe account status"""
    connected           = serializers.BooleanField()
    verified            = serializers.BooleanField()
    charges_enabled     = serializers.BooleanField(required=False)
    payouts_enabled     = serializers.BooleanField(required=False)
    stripe_account_id   = serializers.CharField(required=False, allow_blank=True)
    onboarding_url      = serializers.URLField(required=False, allow_null=True)
    message             = serializers.CharField(required=False, allow_blank=True)


# ============================================================================
# Admin Serializers
# ============================================================================

class AdminPaymentSerializer(serializers.ModelSerializer):
    """Admin — To view all payments"""
    buyer_email     = serializers.EmailField(source='buyer.email', read_only=True)
    product_title   = serializers.CharField(source='seller_product.title', read_only=True, allow_null=True)
    shop_name       = serializers.CharField(source='seller_product.seller.shop_name', read_only=True, allow_null=True)

    class Meta:
        model  = Payment
        fields = '__all__'


class AdminSellerPayoutSerializer(serializers.ModelSerializer):
    """Admin — To view all payouts"""
    shop_name   = serializers.CharField(source='seller.shop_name', read_only=True)
    buyer_email = serializers.EmailField(source='payment.buyer.email', read_only=True)

    class Meta:
        model  = SellerPayout
        fields = '__all__'

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = [
            'id', 'name', 'plan_type', 'price', 'trial_days', 
            'clicks_per_day', 'price_alerts_limit', 'has_ai_optimization', 
            'has_barcode_scanning','features'
        ]