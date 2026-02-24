from rest_framework import serializers
from .models import (
    Platform, Category, Product, ProductListing,
    ProductImage, ProductSpecification, PriceHistory
)
from rest_framework.validators import UniqueTogetherValidator
from rest_framework import serializers
from .models import CartItem

class PlatformSerializer(serializers.ModelSerializer):
    listings_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Platform
        fields = ['id', 'name', 'code', 'logo', 'api_enabled', 'listings_count', 'created_at']
    
    def get_listings_count(self, obj):
        return obj.listings.filter(is_available=True).count()


class CategorySerializer(serializers.ModelSerializer):
    products_count = serializers.SerializerMethodField()
    parent_name = serializers.CharField(source='parent.name', read_only=True, allow_null=True)
    
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'parent', 'parent_name', 'products_count', 'created_at']
    
    def get_products_count(self, obj):
        return obj.products.filter(is_active=True).count()


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image_url', 'alt_text', 'order']


class ProductSpecificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductSpecification
        fields = ['id', 'name', 'value']


class ProductListingSerializer(serializers.ModelSerializer):
    platform_name = serializers.CharField(source='platform.name', read_only=True)
    platform_code = serializers.CharField(source='platform.code', read_only=True)
    product_title = serializers.CharField(source='product.title', read_only=True)
    product_slug = serializers.CharField(source='product.slug', read_only=True)
    total_price = serializers.SerializerMethodField()
    
    class Meta:
        model = ProductListing
        fields = [
            'id', 'product', 'product_title', 'product_slug',
            'platform', 'platform_name', 'platform_code',
            'external_id', 'external_url',
            'price', 'currency', 'original_price', 'discount_percentage',
            'condition', 'quantity',
            'seller_username', 'seller_rating', 'seller_feedback_count',
            'item_location', 'ships_from_country',
            'shipping_cost', 'shipping_currency', 'free_shipping',
            'estimated_delivery_days',
            'returns_accepted', 'return_period_days',
            'is_available', 'last_checked',
            'total_price', 'created_at'
        ]
    
    def get_total_price(self, obj):
        return float(obj.get_total_price())


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    lowest_price = serializers.SerializerMethodField()
    listings_count = serializers.SerializerMethodField()
    available_on = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = [
            'id', 'title', 'slug', 'description',
            'category', 'category_name',
            'brand', 'model_number',
            'main_image',
            'lowest_price', 'listings_count', 'available_on',
            'is_active', 'created_at', 'updated_at', 'last_synced'
        ]
    
    def get_lowest_price(self, obj):
        price = obj.get_lowest_price()
        return float(price) if price else None
    
    def get_listings_count(self, obj):
        return obj.listings.filter(is_available=True).count()
    
    def get_available_on(self, obj):
        platforms = obj.listings.filter(is_available=True).values_list('platform__name', flat=True).distinct()
        return list(platforms)


class ProductDetailSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    images = ProductImageSerializer(many=True, read_only=True)
    specifications = ProductSpecificationSerializer(many=True, read_only=True)
    listings = ProductListingSerializer(many=True, read_only=True)
    lowest_price = serializers.SerializerMethodField()
    price_range = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = [
            'id', 'title', 'slug', 'description',
            'category', 'category_name',
            'brand', 'model_number',
            'main_image', 'images',
            'specifications', 'listings',
            'lowest_price', 'price_range',
            'is_active', 'created_at', 'updated_at', 'last_synced'
        ]
    
    def get_lowest_price(self, obj):
        price = obj.get_lowest_price()
        return float(price) if price else None
    
    def get_price_range(self, obj):
        listings = obj.listings.filter(is_available=True)
        if listings.exists():
            prices = [float(l.price) for l in listings]
            return {
                'min': min(prices),
                'max': max(prices),
                'avg': sum(prices) / len(prices)
            }
        return None


class PriceHistorySerializer(serializers.ModelSerializer):
    product_title = serializers.CharField(source='listing.product.title', read_only=True)
    platform_name = serializers.CharField(source='listing.platform.name', read_only=True)
    
    class Meta:
        model = PriceHistory
        fields = ['id', 'listing', 'product_title', 'platform_name', 'price', 'currency', 'recorded_at']




class CartItemSerializer(serializers.ModelSerializer):
    listing_details = ProductListingSerializer(source='selected_listing', read_only=True)
    product_title = serializers.CharField(source='product.title', read_only=True)

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'product_title', 'selected_listing', 'quantity', 'listing_details' ]
        # , 'listing_details' 
    def validate(self, attrs):
        request = self.context.get('request')
        user = request.user if request else None
        product = attrs.get('product')
        selected_listing = attrs.get('selected_listing')

        # ✅ Listing টা ওই product এর কিনা check
        if selected_listing and product:
            if selected_listing.product != product:
                raise serializers.ValidationError({
                    "selected_listing": ["This listing does not belong to the selected product."]
                })

        # ✅ Already in cart check
        if user and product:
            qs = CartItem.objects.filter(user=user, product=product)
            # PUT/PATCH এর সময় নিজেকে exclude করো
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    "product": ["This product is already in your cart."]
                })

        return attrs