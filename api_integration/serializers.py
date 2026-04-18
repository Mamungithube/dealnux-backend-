from rest_framework import serializers
from twisted.test import obj
from .models import (
    Platform, Category, Product, ProductListing,
    ProductImage, ProductSpecification, PriceHistory, Favorite
)
from rest_framework import serializers
from .models import CartItem


class PlatformSerializer(serializers.ModelSerializer):
    listings_count = serializers.SerializerMethodField()

    class Meta:
        model = Platform
        fields = ['id', 'name', 'code', 'logo',
                  'api_enabled', 'listings_count', 'created_at']

    def get_listings_count(self, obj):
        return obj.listings.filter(is_available=True).count()


class CategorySerializer(serializers.ModelSerializer):
    products_count = serializers.SerializerMethodField()
    parent_name = serializers.CharField(
        source='parent.name', read_only=True, allow_null=True)

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'parent',
                  'parent_name', 'products_count', 'created_at']

    def get_products_count(self, obj):
        from .models import Product
        child_ids = list(obj.children.values_list('id', flat=True))
        all_ids = [obj.id] + child_ids
        return Product.objects.filter(
            category__id__in=all_ids, is_active=True
        ).count()


class CategoryChildSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug']


class CategoryTreeSerializer(serializers.ModelSerializer):
    children = CategoryChildSerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'children']


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image_url', 'alt_text', 'order']


class ProductSpecificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductSpecification
        fields = ['id', 'name', 'value']


class ProductListingSerializer(serializers.ModelSerializer):
    platform_name = serializers.CharField(
        source='platform.name', read_only=True)
    platform_code = serializers.CharField(
        source='platform.code', read_only=True)
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = ProductListing
        fields = [
            'id',
            'platform_name',
            'platform_code',
            'price',
            'currency',
            'original_price',
            'discount_percentage',
            'condition',
            'free_shipping',
            'shipping_cost',
            'total_price',
            'external_url',
            'is_available',
            'has_coupon',
            'coupon_text',
            'deal_badge',
            'is_best_seller',
        ]

    def get_total_price(self, obj):
        return float(obj.get_total_price())


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(
        source='category.name', read_only=True, allow_null=True)
    lowest_price = serializers.SerializerMethodField()
    listings_count = serializers.SerializerMethodField()
    available_on = serializers.SerializerMethodField()
    is_favorite = serializers.SerializerMethodField()
    is_cart = serializers.SerializerMethodField()

    has_coupon = serializers.SerializerMethodField()
    coupon_text = serializers.SerializerMethodField()
    deal_badge = serializers.SerializerMethodField()
    is_best_seller = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()   


    class Meta:
        model = Product
        fields = [
            'id', 'title', 'slug', 'brand',
            'category', 'category_name',
            'main_image', 'price',
            'lowest_price', 'listings_count', 'available_on',
            'is_active', 'created_at', 'is_favorite', 'is_cart',
            'has_coupon', 'coupon_text', 'deal_badge', 'is_best_seller',
            'rating', 'review_count'
            
            # 'description', 'model_number', 'last_synced', 'updated_at',
        ]

    def get_price(self, obj):                      
        best = obj.listings.filter(is_available=True).order_by('price').first()
        return float(best.price) if best else None

    def get_is_cart(self, obj):
        cart_product_ids = self.context.get('cart_product_ids', set())
        return obj.id in cart_product_ids

    def get_is_favorite(self, obj):
        favorite_ids = self.context.get('favorite_ids', set())
        return obj.id in favorite_ids

    def get_lowest_price(self, obj):
        price = obj.get_lowest_price()
        return float(price) if price else None

    def get_listings_count(self, obj):
        return obj.listings.filter(is_available=True).count()

    def get_available_on(self, obj):
        platforms = obj.listings.filter(is_available=True).values_list(
            'platform__name', flat=True).distinct()
        return list(platforms)
    
    def get_has_coupon(self, obj):
        best = obj.listings.filter(is_available=True).order_by('price').first()
        return best.has_coupon if best else False

    def get_coupon_text(self, obj):
        best = obj.listings.filter(is_available=True).order_by('price').first()
        return best.coupon_text if best else ''

    def get_deal_badge(self, obj):
        best = obj.listings.filter(is_available=True).order_by('price').first()
        return best.deal_badge if best else ''

    def get_is_best_seller(self, obj):
        best = obj.listings.filter(is_available=True).order_by('price').first()
        return best.is_best_seller if best else False


class ProductDetailSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(
        source='category.name', read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    listings      = serializers.SerializerMethodField()
    lowest_price = serializers.SerializerMethodField()
    is_favorite = serializers.SerializerMethodField()
    is_cart = serializers.SerializerMethodField()
    platform_name = serializers.SerializerMethodField()
    external_url = serializers.SerializerMethodField()
    is_available = serializers.SerializerMethodField()
    shipping_cost = serializers.SerializerMethodField()
    has_coupon = serializers.SerializerMethodField()
    coupon_text = serializers.SerializerMethodField()
    deal_badge = serializers.SerializerMethodField()
    is_best_seller = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()  
    # listing = serializers.SerializerMethodField()
    # price_analysis = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'title', 'slug', 'description',
            'category', 'category_name',
            'brand', 'main_image', 'images', 'price',
            'lowest_price', 'shipping_cost',
            'platform_name', 'external_url', 'is_available',
            'is_active', 'created_at',
            'is_favorite',
            'is_cart',
            'has_coupon',
            'coupon_text',
            'deal_badge',
            'is_best_seller',
            'listings','rating', 'review_count'
        ]

    def get_is_favorite(self, obj):
        favorite_ids = self.context.get('favorite_ids', set())
        return obj.id in favorite_ids

    def get_is_cart(self, obj):
        cart_product_ids = self.context.get('cart_product_ids', set())
        return obj.id in cart_product_ids
    
    def get_price(self, obj):                      
        best = obj.listings.filter(is_available=True).order_by('price').first()
        return float(best.price) if best else None

    def get_lowest_price(self, obj):
        price = obj.get_lowest_price()
        return float(price) if price else None

    def get_platform_name(self, obj):
        best = obj.listings.filter(is_available=True).order_by('price').first()
        return best.platform.name if best else "N/A"

    def get_external_url(self, obj):
        best = obj.listings.filter(is_available=True).order_by('price').first()
        return best.external_url if best else ""

    def get_is_available(self, obj):
        best = obj.listings.filter(is_available=True).order_by('price').first()
        return best.is_available if best else False

    def get_shipping_cost(self, obj):
        best = obj.listings.filter(is_available=True).order_by('price').first()
        return float(best.shipping_cost) if best else 0.0

    def get_has_coupon(self, obj):
        best = obj.listings.filter(is_available=True).order_by('price').first()
        return best.has_coupon if best else False


    def get_coupon_text(self, obj):
        best = obj.listings.filter(is_available=True).order_by('price').first()
        return best.coupon_text if best else ''


    def get_deal_badge(self, obj):
        best = obj.listings.filter(is_available=True).order_by('price').first()
        return best.deal_badge if best else ''


    def get_is_best_seller(self, obj):
        best = obj.listings.filter(is_available=True).order_by('price').first()
        return best.is_best_seller if best else False


    def get_listings(self, obj):
        listings = obj.listings.filter(
            is_available=True,
            price__gt=0
        ).select_related('platform').order_by('price')
        return ProductListingSerializer(listings, many=True).data

    # def get_listings(self, obj):

    #     listings = obj.listings.filter(
    #         is_available=True,
    #         price__gt=0
    #     ).select_related('platform').order_by('price')

    #     return ProductListingSerializer(listings, many=True).data

    # def get_price_analysis(self, obj):
    #     listings = obj.listings.filter(is_available=True, price__gt=0)

    #     if listings.count() < 2:
    #         price = float(listings.first().price) if listings.exists() else 0
    #         return {
    #             "lowest_price": price,
    #             "highest_price": price,
    #             "potential_savings": 0.0
    #         }

    #     prices = [float(l.price) for l in listings]
    #     low = min(prices)
    #     high = max(prices)

    #     return {
    #         "lowest_price": low,
    #         "highest_price": high,
    #         "potential_savings": round(high - low, 2)
    #     }


class PriceHistorySerializer(serializers.ModelSerializer):
    product_title = serializers.CharField(
        source='listing.product.title', read_only=True)
    platform_name = serializers.CharField(
        source='listing.platform.name', read_only=True)

    class Meta:
        model = PriceHistory
        fields = ['id', 'listing', 'product_title',
                  'platform_name', 'price', 'currency', 'recorded_at']


class CartItemSerializer(serializers.ModelSerializer):
    product_title = serializers.CharField(
        source='product.title', read_only=True)
    # product_image = serializers.URLField(
    #     source='product.main_image', read_only=True)
    listing = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'product_title',
                  'product_image', 'quantity', 'listing'] 

    def get_listing(self, obj):
        best = obj.product.listings.filter(
            is_available=True
        ).order_by('price').first()
        return ProductListingSerializer(best).data if best else None
    
    def get_product_image(self, obj):
        request = self.context.get('request')
        if obj.product_image and request:
            return request.build_absolute_uri(obj.product_image.url)
        return None

    def validate(self, attrs):
        request = self.context.get('request')
        user = request.user if request else None
        product = attrs.get('product')

        if user and product:
            qs = CartItem.objects.filter(user=user, product=product)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    "product": ["This product is already in your cart."]
                })

        return attrs


class FavoriteSerializer(serializers.ModelSerializer):
    product = serializers.SerializerMethodField()
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), source='product', write_only=True
    )

    class Meta:
        model = Favorite
        fields = ['id', 'product', 'product_id', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_product(self, obj):
        return ProductSerializer(
            obj.product,
            context=self.context
        ).data
