from rest_framework import serializers
from django.utils import timezone
from .models import (
    SellerRequest, SellerProfile,
    SellerProduct, SellerProductImage,
    Order, Coupon,
)
from api_integration.serializers import ProductListingSerializer


# ============================================================================
# Seller Request
# ============================================================================

class SellerRequestSerializer(serializers.ModelSerializer):
    """User can submit this request to become a seller"""
    user_email = serializers.CharField(source='user.email', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = SellerRequest
        fields = [
            'id', 'user_email', 'status', 'status_display',
            'shop_name', 'shop_description', 'phone_number',
            'nid_document', 'business_document',
            'admin_note', 'created_at', 'updated_at',
        ]
        read_only_fields = ['status', 'admin_note', 'created_at', 'updated_at']

    def validate(self, attrs):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            # A user can only make one request (PENDING/APPROVED).
            existing = SellerRequest.objects.filter(
                user=request.user,
                status__in=['PENDING', 'APPROVED']
            ).first()
            if existing and not self.instance:
                raise serializers.ValidationError({
                    "seller_request": [
                        f"You already have a {existing.status.lower()} seller request."
                    ]
                })
        return attrs


class AdminSellerRequestSerializer(serializers.ModelSerializer):
    """For Admin — with approve/reject action"""
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name  = serializers.CharField(source='user.name',  read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = SellerRequest
        fields = '__all__'
        read_only_fields = ['user', 'created_at', 'updated_at']


# ============================================================================
# Seller Profile
# ============================================================================

class SellerProfileSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name  = serializers.CharField(source='user.name',  read_only=True)

    class Meta:
        model  = SellerProfile
        fields = [
            'id', 'user_email', 'user_name',
            'shop_name', 'shop_description', 'shop_logo', 'phone_number',
            'bank_name', 'bank_account_number',
            'total_products', 'total_orders', 'total_earnings',
            'is_active', 'created_at',
        ]
        read_only_fields = ['total_products', 'total_orders', 'total_earnings', 'created_at']


# ============================================================================
# Seller Product Images
# ============================================================================

class SellerProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model  = SellerProductImage
        fields = ['id', 'image', 'alt_text', 'order']


# ============================================================================
# Seller Product
# ============================================================================

class SellerProductSerializer(serializers.ModelSerializer):
    """For the seller to add/edit the product themselves"""
    seller_shop         = serializers.CharField(source='seller.shop_name', read_only=True)
    status_display      = serializers.CharField(source='get_status_display', read_only=True)
    discount_percentage = serializers.SerializerMethodField()
    images              = SellerProductImageSerializer(many=True, read_only=True)
    category_name       = serializers.CharField(source='category.name', read_only=True, allow_null=True)

    # category: pk ("3") or name ("food") will both work
    category = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    class Meta:
        model = SellerProduct
        fields = [
            'id', 'seller', 'seller_shop',
            'category', 'category_name',
            'title', 'description', 'brand', 'model_number',
            'price', 'original_price', 'currency', 'quantity', 'condition',
            'main_image', 'images',
            'free_shipping', 'shipping_cost', 'estimated_delivery_days',
            'returns_accepted', 'return_period_days',
            'status', 'status_display', 'admin_note',
            'discount_percentage',
            'linked_product', 'linked_listing',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'seller', 'status', 'admin_note',
            'linked_product', 'linked_listing',
            'created_at', 'updated_at',
        ]

    def get_discount_percentage(self, obj):
        return obj.discount_percentage

    def validate_category(self, value):
        """pk number or category name — both will be accepted"""
        from api_integration.models import Category
        if not value:
            return None
        # 1. Search by numeric string → pk
        if str(value).strip().isdigit():
            try:
                return Category.objects.get(pk=int(value))
            except Category.DoesNotExist:
                raise serializers.ValidationError(
                    f"Category with pk={value} not found."
                )
        # 2. Search by name (case-insensitive)
        cat = Category.objects.filter(name__iexact=str(value).strip()).first()
        if cat:
            return cat
        # 3. Search by slug (case-insensitive)
        cat = Category.objects.filter(slug__iexact=str(value).strip()).first()
        if cat:
            return cat
        # 4. partial name match (e.g. "Toys" → "Toys & Games")
        cat = Category.objects.filter(name__icontains=str(value).strip()).first()
        if cat:
            return cat
        raise serializers.ValidationError(
            f'Category "{value}" not found. Send pk number or exact category name.'
        )

    def validate_condition(self, value):
        """case-insensitive: 'new', 'NEW', 'New' all will accept"""
        from .models import SellerProduct as SP
        valid = {c[0] for c in SP.CONDITION_CHOICES}
        upper = value.upper() if value else ''
        if upper not in valid:
            raise serializers.ValidationError(
                f'"{value}" is not valid. Choose: {", ".join(sorted(valid))}'
            )
        return upper

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than 0.")
        return value

    def validate(self, attrs):
        original = attrs.get('original_price')
        price    = attrs.get('price')
        if original and price and original <= price:
            raise serializers.ValidationError({
                "original_price": ["Original price must be greater than sale price."]
            })
        return attrs

    def create(self, validated_data):
        return SellerProduct.objects.create(**validated_data)

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class SellerProductPublicSerializer(serializers.ModelSerializer):
    """Public API - for displaying approved products"""
    seller_shop  = serializers.CharField(source='seller.shop_name', read_only=True)
    seller_logo  = serializers.ImageField(source='seller.shop_logo', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    images       = SellerProductImageSerializer(many=True, read_only=True)
    listing_details = ProductListingSerializer(source='linked_listing', read_only=True)
    discount_percentage = serializers.SerializerMethodField()

    class Meta:
        model = SellerProduct
        fields = [
            'id', 'seller_shop', 'seller_logo', 'category', 'category_name',
            'title', 'description', 'brand', 'model_number',
            'price', 'original_price', 'currency', 'quantity', 'condition',
            'main_image', 'images',
            'free_shipping', 'shipping_cost', 'estimated_delivery_days',
            'returns_accepted', 'return_period_days',
            'discount_percentage', 'listing_details',
            'created_at',
        ]

    def get_discount_percentage(self, obj):
        return obj.discount_percentage


# ============================================================================
# Admin Product Review
# ============================================================================

class AdminSellerProductSerializer(serializers.ModelSerializer):
    seller_shop  = serializers.CharField(source='seller.shop_name', read_only=True)
    seller_email = serializers.CharField(source='seller.user.email', read_only=True)
    images       = SellerProductImageSerializer(many=True, read_only=True)
    discount_percentage = serializers.SerializerMethodField()

    class Meta:
        model  = SellerProduct
        fields = '__all__'
        read_only_fields = ['seller', 'linked_product', 'linked_listing', 'created_at', 'updated_at']

    def get_discount_percentage(self, obj):
        return obj.discount_percentage


# ============================================================================
# Order
# ============================================================================

class OrderSerializer(serializers.ModelSerializer):
    buyer_email  = serializers.CharField(source='buyer.email',  read_only=True)
    seller_shop  = serializers.CharField(source='seller.shop_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    seller_product = SellerProductPublicSerializer(read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'buyer_email', 'seller_shop',
            'seller_product', 'listing',
            'quantity', 'unit_price', 'total_price', 'currency',
            'shipping_address', 'status', 'status_display',
            'tracking_number', 'note',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'buyer_email', 'seller_shop', 'unit_price', 'total_price',
            'status', 'tracking_number', 'created_at', 'updated_at',
        ]

    def validate(self, attrs):
        seller_product = attrs.get('seller_product')
        quantity       = attrs.get('quantity', 1)

        if seller_product:
            if seller_product.status != 'APPROVED':
                raise serializers.ValidationError({
                    "seller_product": ["This product is not available for purchase."]
                })
            if seller_product.quantity < quantity:
                raise serializers.ValidationError({
                    "quantity": [f"Only {seller_product.quantity} items available."]
                })
        return attrs


class OrderCreateSerializer(serializers.ModelSerializer):
    """For buyer to place an order"""

    class Meta:
        model = Order
        fields = ['seller_product', 'quantity', 'shipping_address', 'note']

    def validate(self, attrs):
        seller_product = attrs.get('seller_product')
        quantity       = attrs.get('quantity', 1)

        if seller_product.status != 'APPROVED':
            raise serializers.ValidationError({
                "seller_product": ["This product is not available."]
            })
        if seller_product.quantity < quantity:
            raise serializers.ValidationError({
                "quantity": [f"Only {seller_product.quantity} items available."]
            })
        return attrs

    def create(self, validated_data):
        seller_product = validated_data['seller_product']
        request        = self.context['request']

        order = Order.objects.create(
            buyer           = request.user,
            seller          = seller_product.seller,
            seller_product  = seller_product,
            listing         = seller_product.linked_listing,
            quantity        = validated_data.get('quantity', 1),
            unit_price      = seller_product.price,
            total_price     = seller_product.price * validated_data.get('quantity', 1),
            currency        = seller_product.currency,
            shipping_address = validated_data.get('shipping_address', ''),
            note            = validated_data.get('note', ''),
        )

        # Reduce stock
        seller_product.quantity -= order.quantity
        seller_product.save(update_fields=['quantity'])

        # Seller stats
        seller = seller_product.seller
        seller.total_orders += 1
        seller.total_earnings += order.total_price
        seller.save(update_fields=['total_orders', 'total_earnings'])

        return order


# ============================================================================
# Coupon
# ============================================================================

class CouponSerializer(serializers.ModelSerializer):
    seller_shop  = serializers.CharField(source='seller.shop_name', read_only=True)
    is_valid     = serializers.BooleanField(read_only=True)

    class Meta:
        model = Coupon
        fields = [
            'id', 'seller_shop', 'code',
            'discount_type', 'discount_value', 'min_order_amount',
            'max_uses', 'used_count', 'is_active', 'expires_at',
            'is_valid', 'created_at',
        ]
        read_only_fields = ['seller', 'used_count', 'created_at']

    def validate_code(self, value):
        return value.upper().strip()


class CouponValidateSerializer(serializers.Serializer):
    """When buyer applies a coupon"""
    code         = serializers.CharField(max_length=50)
    order_amount = serializers.DecimalField(max_digits=10, decimal_places=2)

    def validate(self, attrs):
        code = attrs['code'].upper().strip()
        try:
            coupon = Coupon.objects.get(code=code)
        except Coupon.DoesNotExist:
            raise serializers.ValidationError({"code": ["Invalid coupon code."]})

        if not coupon.is_valid:
            raise serializers.ValidationError({"code": ["This coupon is expired or inactive."]})

        if attrs['order_amount'] < coupon.min_order_amount:
            raise serializers.ValidationError({
                "code": [f"Minimum order amount is {coupon.min_order_amount} {coupon.seller.shop_name}."]
            })

        attrs['coupon'] = coupon
        return attrs