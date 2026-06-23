from decimal import Decimal

from rest_framework import serializers
from .models import (
    ProductReview, SellerRequest, SellerProfile,
    SellerProduct, SellerProductImage,
    Order, Coupon,
)
from api_integration.serializers import ProductListingSerializer
from api_integration.models import Category
import json
from django.db import transaction 

# ============================================================================
# Seller Request
# ============================================================================

class SellerRequestSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    agreed_to_seller_agreement = serializers.BooleanField(required=True)
    agreed_to_terms = serializers.BooleanField(required=True)
    agreed_to_privacy = serializers.BooleanField(required=True)
    
    # To receive a list of category names from the frontend
    category_names = serializers.ListField(
        child=serializers.CharField(),
        write_only=True,
        required=True
    )
    
    # To show category names in the response
    display_categories = serializers.SerializerMethodField()

    class Meta:
        model = SellerRequest
        fields = [
            'id', 'user_email', 'status', 'status_display',
            
            # Step 1: Business Details
            'trade_name', 'legal_business_type', 'business_reg_number',
            
            # Step 2: Primary Contact
            'contact_full_name', 'job_title', 'contact_email', 'contact_phone',
            
            # Step 3: Product Catalog
            'category_names', 'display_categories', # নামের ফিল্ডগুলো
            'estimated_sku_count', 'min_price', 'max_price', 
            'product_conditions', 'owns_inventory',
            
            # Step 4: Fulfillment & Shipping
            'fulfillment_methods', 'shipping_regions',
            
            # Step 5: Return Policy
            'return_policy_description', 'return_policy_document',
            
            # Step 6 & 7: Compliance & Policy
            'agreed_to_compliance', 'agreed_to_prohibited_items',
            
            # Step 8: Business History & Docs
            'has_prior_experience', 'experience_description',
            'government_id', 'business_license', 'utility_bill',
            
            # Step 10: Signature
            'digital_signature',

            #agrement
            'agreed_to_seller_agreement', 'agreed_to_terms', 'agreed_to_privacy',
            
            # Admin Info
            'admin_note', 'created_at', 'updated_at'
        ]
        read_only_fields = ['status', 'admin_note', 'created_at', 'updated_at']

    def get_display_categories(self, obj):
        # Returns a list of category names from the database.
        return obj.categories.values_list('name', flat=True)

    def validate(self, attrs):
        request = self.context.get('request')
        user = request.user if request else None
        
        if user:
            existing = SellerRequest.objects.filter(
                user=user, 
                status__in=['PENDING', 'APPROVED']
            ).exists()
            if existing and not self.instance:
                raise serializers.ValidationError(
                    {"detail": "You already have an active or pending seller application."}
                )
    def validate(self, attrs):
        # Custom validation for US Compliance
        if not attrs.get('agreed_to_seller_agreement'):
            raise serializers.ValidationError("You must agree to the Seller Agreement.")
        if not attrs.get('agreed_to_terms'):
            raise serializers.ValidationError("You must agree to the Terms & Conditions.")
        if not attrs.get('agreed_to_privacy'):
            raise serializers.ValidationError("You must agree to the Privacy Policy.")
        
        # Converting category names to objects
    def validate(self, attrs):
        request = self.context.get('request')
        user = request.user if request else None
        
        if user:
            existing = SellerRequest.objects.filter(
                user=user, 
                status__in=['PENDING', 'APPROVED']
            ).exists()
            if existing and not self.instance:
                raise serializers.ValidationError(
                    {"detail": "You already have an active or pending seller application."}
                )

        category_names = attrs.get('category_names', [])
        
        if isinstance(category_names, list) and len(category_names) == 1:
            raw_val = category_names[0]
            if isinstance(raw_val, str) and raw_val.startswith('['):
                try:
                    category_names = json.loads(raw_val)
                except:
                    pass

        if category_names:
            categories = Category.objects.filter(name__in=category_names)
            if categories.count() == 0:
                raise serializers.ValidationError({"category_names": "No matching categories found."})

            attrs['category_objects'] = categories
            
        return attrs

    def create(self, validated_data):
        category_objects = validated_data.pop('category_objects', [])
        if 'category_names' in validated_data:
            validated_data.pop('category_names')

        seller_request = SellerRequest.objects.create(**validated_data)

        if category_objects:
            seller_request.categories.set(category_objects)
            
        return seller_request

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
    class Meta:
        model = SellerProfile
        fields = '__all__'

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
    rating       = serializers.SerializerMethodField() 
    review_count = serializers.SerializerMethodField() 

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
            'discount_percentage', 'rating', 'review_count',
            'linked_product', 'linked_listing',
            'created_at', 'updated_at',

        ]
        read_only_fields = [
            'seller', 'status', 'admin_note',
            'linked_product', 'linked_listing',
            'created_at', 'updated_at',
        ]


    def get_rating(self, obj):
        from django.db.models import Avg
        result = obj.reviews.aggregate(avg=Avg('rating'))
        return round(result['avg'] or 0, 1)

    def get_review_count(self, obj):
        return obj.reviews.count()

    def get_discount_percentage(self, obj):
        return obj.discount_percentage

    def validate_category(self, value):
        """pk number or category name — both will be accepted"""
        from api_integration.models import Category
        if not value:
            return None
        # Search by numeric string → pk
        if str(value).strip().isdigit():
            try:
                return Category.objects.get(pk=int(value))
            except Category.DoesNotExist:
                raise serializers.ValidationError(
                    f"Category with pk={value} not found."
                )
        # Search by name (case-insensitive)
        cat = Category.objects.filter(name__iexact=str(value).strip()).first()
        if cat:
            return cat
        # Search by slug (case-insensitive)
        cat = Category.objects.filter(slug__iexact=str(value).strip()).first()
        if cat:
            return cat
        # partial name match (e.g. "Toys" → "Toys & Games")
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
    """Public API --> for displaying approved products"""
    seller_shop  = serializers.CharField(source='seller.shop_name', read_only=True)
    seller_logo  = serializers.ImageField(source='seller.shop_logo', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    images       = SellerProductImageSerializer(many=True, read_only=True)
    listing_details = ProductListingSerializer(source='linked_listing', read_only=True)
    discount_percentage = serializers.SerializerMethodField()
    rating       = serializers.SerializerMethodField()  
    review_count = serializers.SerializerMethodField()

    is_favorited = serializers.SerializerMethodField()
    is_in_cart   = serializers.SerializerMethodField()

    class Meta:
        model = SellerProduct
        fields = [
            'id', 'seller_shop', 'seller_logo', 'category', 'category_name',
            'title', 'description', 'brand', 'model_number',
              'price',  'original_price', 'currency', 'quantity', 'condition',
            'main_image', 'images',
            'free_shipping', 'shipping_cost', 'estimated_delivery_days',
            'returns_accepted', 'return_period_days',
            'discount_percentage', 'listing_details','rating', 'review_count', 
            'is_favorited', 'is_in_cart',
            'created_at',
        ]

    def _get_user(self):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return request.user
        return None

    def _get_linked_product(self, obj):
        """SellerProduct → linked_listing → product"""
        listing = getattr(obj, 'linked_listing', None)
        if listing:
            return getattr(listing, 'product', None)
        return None

    def get_discount_percentage(self, obj):
        return obj.discount_percentage
    
    def get_rating(self, obj):
        from django.db.models import Avg
        result = obj.reviews.aggregate(avg=Avg('rating'))
        return round(result['avg'] or 0, 1)

    def get_review_count(self, obj):
        return obj.reviews.count()
    
    def get_is_favorited(self, obj):
        user = self._get_user()
        if not user:
            return False  # Guest user
        
        from api_integration.models import Favorite
        product = self._get_linked_product(obj)
        if not product:
            return False
        return Favorite.objects.filter(user=user, product=product).exists()

    def get_is_in_cart(self, obj):
        user = self._get_user()
        if not user:
            return False  # Guest user
        
        from api_integration.models import CartItem
        product = self._get_linked_product(obj)
        if not product:
            return False
        return CartItem.objects.filter(user=user, product=product).exists()

# ============================================================================
# Admin Product Review
# ============================================================================

class SellerProductReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.Fullname', read_only=True)

    class Meta:
        model = ProductReview
        fields = ['id', 'user_name', 'rating', 'comment', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


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
    buyer_email = serializers.CharField(source='buyer.email', read_only=True)
    seller_shop = serializers.CharField(source='seller.shop_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    seller_product = SellerProductPublicSerializer(read_only=True)
    coupon_code = serializers.CharField(source='coupon.code', read_only=True, allow_null=True)

    class Meta:
        model = Order
        fields = [
            'id', 'buyer_email', 'seller_shop',
            'seller_product', 'listing',
            'quantity', 'unit_price', 'discount_amount', 
            'item_total', 'shipping_fee', 'service_fee', 'total_price', 
            'coupon_code', 'currency',
            'shipping_address', 'status', 'status_display',
            'tracking_number','courier_name', 'note','order_number',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'buyer_email', 'seller_shop', 'unit_price', 'total_price',
            'discount_amount', 'final_price', 'item_total',
            'status', 'tracking_number', 'created_at', 'updated_at',
        ]

class OrderItemSerializer(serializers.Serializer):
    """Input format for each product"""
    seller_product = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    coupon_code = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")

class OrderCreateSerializer(serializers.Serializer):
    """Input format for creating an order (without the Note field)"""
    items = OrderItemSerializer(many=True)
    shipping_address = serializers.CharField(max_length=500)

    def validate(self, attrs):
        item_list = attrs.get('items', [])
        if not item_list:
            raise serializers.ValidationError({"items": ["At least one item is required."]})

        validated_data_list = []
        for item in item_list:
            # Product existence and approval check
            try:
                product = SellerProduct.objects.get(id=item['seller_product'], status='APPROVED')
            except SellerProduct.DoesNotExist:
                raise serializers.ValidationError({"seller_product": [f"Product ID {item['seller_product']} not found."]})

            # stock check
            if product.quantity < item['quantity']:
                raise serializers.ValidationError({"quantity": [f"Insufficient stock for {product.title}."]})

            # coupon validation (if provided)
            coupon = None
            c_code = item.get('coupon_code')
            if c_code:
                try:
                    coupon = Coupon.objects.get(code=c_code.upper().strip(), seller=product.seller)
                    if not coupon.is_valid:
                        raise serializers.ValidationError({"coupon_code": [f"Coupon {c_code} is invalid."]})
                except Coupon.DoesNotExist:
                    raise serializers.ValidationError({"coupon_code": [f"Invalid coupon for {product.seller.shop_name}."]})

            validated_data_list.append({
                'product': product,
                'quantity': item['quantity'],
                'coupon': coupon
            })
        
        attrs['validated_items'] = validated_data_list
        return attrs

    def create(self, validated_data):
        from decimal import Decimal
        request = self.context['request']
        items = validated_data['validated_items']
        address = validated_data['shipping_address']

        first_order = None

        with transaction.atomic():
            for entry in items:
                product = entry['product']
                qty = entry['quantity']
                coupon = entry['coupon']

                # calculate prices
                total_base = product.price * qty
                discount = Decimal('0')
                if coupon:
                    if coupon.discount_type == 'PERCENTAGE':
                        discount = (total_base * coupon.discount_value) / 100
                    else:
                        discount = min(coupon.discount_value, total_base)
                    coupon.used_count += 1
                    coupon.save()

                item_total = total_base - discount
                shipping = product.shipping_cost if not product.free_shipping else Decimal('0')
                service_fee = (item_total + shipping) * Decimal('0.08')
                total_price = item_total + shipping + service_fee

                # create order
                order = Order.objects.create(
                    buyer=request.user,
                    seller=product.seller,
                    seller_product=product,
                    listing=product.linked_listing,
                    quantity=qty,
                    unit_price=product.price,
                    discount_amount=discount,
                    item_total=item_total,
                    shipping_fee=shipping,
                    service_fee=service_fee,
                    total_price=total_price,
                    coupon=coupon,
                    currency=product.currency,
                    shipping_address=address,
                    status='PENDING'
                )

                
                product.quantity -= qty
                product.save()

                seller_prof = product.seller
                seller_prof.pending_balance += (item_total + shipping)
                seller_prof.total_orders += 1
                seller_prof.save()

                if not first_order:
                    first_order = order

        return first_order

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


# store/serializers.py

class CouponValidateSerializer(serializers.Serializer):
    """Input format for validating multiple items with a coupon"""
    items = serializers.ListField(child=serializers.DictField(), required=True)
    coupon_code = serializers.CharField(max_length=50, required=True)

    def validate(self, attrs):
        items_data = attrs.get('items', [])
        code = attrs.get('coupon_code', '').upper().strip()
        
        total_discount = Decimal('0')
        total_original = Decimal('0')
        seller_name = ""

        for item in items_data:
            p_id = item.get('seller_product')
            qty = int(item.get('quantity', 1))

            try:
                product = SellerProduct.objects.get(id=p_id, status='APPROVED')
                seller_name = product.seller.shop_name
                
                # copon validation
                coupon = Coupon.objects.get(code=code, seller=product.seller)
                
                item_subtotal = product.price * qty
                total_original += item_subtotal

                if coupon.is_valid and item_subtotal >= coupon.min_order_amount:
                    if coupon.discount_type == 'PERCENTAGE':
                        total_discount += (item_subtotal * coupon.discount_value) / 100
                    else:
                        total_discount += min(coupon.discount_value, item_subtotal)
            except (SellerProduct.DoesNotExist, Coupon.DoesNotExist):
                continue 

        attrs['total_discount'] = total_discount
        attrs['total_original'] = total_original
        attrs['seller_shop'] = seller_name
        attrs['code'] = code
        return attrs