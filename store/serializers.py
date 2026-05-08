from rest_framework import serializers
from .models import (
    ProductReview, SellerRequest, SellerProfile,
    SellerProduct, SellerProductImage,
    Order, Coupon,
)
from api_integration.serializers import ProductListingSerializer
from api_integration.models import Category

# ============================================================================
# Seller Request
# ============================================================================

class SellerRequestSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
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

        # Converting category names to objects
        category_names = attrs.get('category_names', [])
        if category_names:
            # Check if these names are in the database
            categories = Category.objects.filter(name__in=category_names)
            if categories.count() != len(category_names):
                found_names = categories.values_list('name', flat=True)
                missing_names = set(category_names) - set(found_names)
                raise serializers.ValidationError(
                    {"category_names": f"Categories not found: {list(missing_names)}"}
                )
            attrs['category_objects'] = categories
            
        return attrs

    def create(self, validated_data):
        # 1. Separate the ManyToMany objects (these cannot be passed directly to .create)
        category_objects = validated_data.pop('category_objects', [])
        
        # 2. Pop out category_names because it is not a field in the model.
        if 'category_names' in validated_data:
            validated_data.pop('category_names')

        # 3. Create a seller request
        # There is no need to separate user=user here because it is inside validated_data
        seller_request = SellerRequest.objects.create(**validated_data)
        
        # 4. Save the categories
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
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name  = serializers.CharField(source='user.name',  read_only=True)
    
    #To display data from the request (if needed)
    contact_phone = serializers.CharField(source='user.seller_request.contact_phone', read_only=True)

    class Meta:
        model  = SellerProfile
        fields = [
            'id', 'user_email', 'user_name',
            'shop_name', 'shop_description', 'shop_logo', 
            'contact_phone',
            'pending_balance', 'available_balance', 'total_earnings',
            'stripe_account_id', 'stripe_onboarding_completed',
            'total_products', 'total_orders', 'seller_score',
            'is_active', 'created_at',
        ]
        read_only_fields = [
            'pending_balance', 'available_balance', 'total_earnings', 
            'stripe_account_id', 'stripe_onboarding_completed',
            'total_products', 'total_orders', 'seller_score', 'created_at'
        ]


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
    """Public API -> for displaying approved products"""
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
            'tracking_number', 'note','order_number',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'buyer_email', 'seller_shop', 'unit_price', 'total_price',
            'discount_amount', 'final_price', 'item_total',
            'status', 'tracking_number', 'created_at', 'updated_at',
        ]

class OrderCreateSerializer(serializers.ModelSerializer):
    coupon_code = serializers.CharField(max_length=50, required=False, allow_blank=True)

    class Meta:
        model = Order
        fields = ['seller_product', 'quantity', 'shipping_address', 'note', 'coupon_code']

    def validate(self, attrs):
        seller_product = attrs.get('seller_product')
        quantity       = attrs.get('quantity', 1)
        coupon_code    = attrs.pop('coupon_code', None)

        # 1. Check if the product is approved (your previous code)
        if seller_product.status != 'APPROVED':
            raise serializers.ValidationError({
                "seller_product": ["This product is not available."]
            })
        
        # 2. Stock Check (Your previous code)
        if seller_product.quantity < quantity:
            raise serializers.ValidationError({
                "quantity": [f"Only {seller_product.quantity} items available."]
            })

        # 3. Coupon Validation (your previous logic)
        if coupon_code:
            try:
                # It will also check whether the coupon is from that specific seller or not.
                coupon = Coupon.objects.get(code=coupon_code.upper().strip(), seller=seller_product.seller)
            except Coupon.DoesNotExist:
                raise serializers.ValidationError({"coupon_code": ["Invalid coupon code for this seller."]})

            if not coupon.is_valid:
                raise serializers.ValidationError({"coupon_code": ["This coupon is expired or inactive."]})

            total_base = seller_product.price * quantity
            if total_base < coupon.min_order_amount:
                raise serializers.ValidationError({
                    "coupon_code": [f"Minimum order amount is {coupon.min_order_amount} USD."]
                })

            attrs['coupon'] = coupon
        else:
            attrs['coupon'] = None

        return attrs

    def create(self, validated_data):
        from decimal import Decimal
        seller_product = validated_data['seller_product']
        request        = self.context['request']
        quantity       = validated_data.get('quantity', 1)
        coupon         = validated_data.pop('coupon', None)

        # 1. Base Calculation
        unit_price = seller_product.price
        total_base = unit_price * quantity
        discount_amount = Decimal('0')

        # 2. Discount (your previous logic)
        if coupon:
            if coupon.discount_type == 'PERCENTAGE':
                discount_amount = (total_base * coupon.discount_value) / 100
            else:  # FIXED
                discount_amount = min(coupon.discount_value, total_base)

            coupon.used_count += 1
            coupon.save(update_fields=['used_count'])

        # 3. Fee Calculation (new logic)
        item_total = total_base - discount_amount
        shipping_fee = seller_product.shipping_cost if not seller_product.free_shipping else Decimal('0')
        
        # 8% service fee (on item + shipping) as per doc
        service_fee_rate = Decimal('0.08') 
        service_fee = (item_total + shipping_fee) * service_fee_rate
        
        # 4. Grand Total (what the buyer will pay)
        total_price = item_total + shipping_fee + service_fee

        # 5. Order Creation
        order = Order.objects.create(
            buyer            = request.user,
            seller           = seller_product.seller,
            seller_product   = seller_product,
            listing          = seller_product.linked_listing,
            quantity         = quantity,
            unit_price       = unit_price,
            discount_amount  = discount_amount,
            item_total       = item_total,
            shipping_fee     = shipping_fee,
            service_fee      = service_fee,
            total_price      = total_price,
            coupon           = coupon,
            currency         = seller_product.currency,
            shipping_address = validated_data.get('shipping_address', ''),
            note             = validated_data.get('note', ''),
            status           = 'PENDING'
        )

        # Stock reduction (your previous code)
        seller_product.quantity -= quantity
        seller_product.save(update_fields=['quantity'])

        # Seller stats update
        seller = seller_product.seller
        seller.total_orders += 1
        seller.save(update_fields=['total_orders'])

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


# store/serializers.py

class CouponValidateSerializer(serializers.Serializer):
    """Individual product coupon validation"""
    code              = serializers.CharField(max_length=50)
    seller_product_id = serializers.IntegerField()
    quantity          = serializers.IntegerField(min_value=1, default=1)

    def validate(self, attrs):
        code = attrs['code'].upper().strip()
        product_id = attrs['seller_product_id']
        
        # 1. Check the product
        try:
            from .models import SellerProduct
            product = SellerProduct.objects.get(id=product_id, status='APPROVED')
        except SellerProduct.DoesNotExist:
            raise serializers.ValidationError({"seller_product_id": ["Product not found or not approved."]})

        # 2. Check if the coupon is from that specific seller
        try:
            from .models import Coupon
            coupon = Coupon.objects.get(code=code, seller=product.seller)
        except Coupon.DoesNotExist:
            raise serializers.ValidationError({"code": ["This coupon is not valid for this seller's product."]})

        if not coupon.is_valid:
            raise serializers.ValidationError({"code": ["This coupon is expired or inactive."]})

        # 3. Calculate the product's total cost and check the coupon's minimum amount
        item_total = product.price * attrs['quantity']
        if item_total < coupon.min_order_amount:
            raise serializers.ValidationError({
                "code": [f"Minimum order amount for this coupon is {coupon.min_order_amount} USD."]
            })

        attrs['coupon'] = coupon
        attrs['product'] = product
        attrs['item_total'] = item_total
        return attrs