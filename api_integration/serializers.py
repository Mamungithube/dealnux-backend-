from rest_framework import serializers
from twisted.test import obj
from .models import (
    Platform, Category, Product, ProductListing,
    ProductImage, ProductSpecification, PriceHistory , Favorite
)
from rest_framework.validators import UniqueTogetherValidator
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
    platform_name = serializers.CharField(source='platform.name', read_only=True)
    platform_code = serializers.CharField(source='platform.code', read_only=True)
    total_price   = serializers.SerializerMethodField()

    class Meta:
        model  = ProductListing
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
        ]

    def get_total_price(self, obj):
        return float(obj.get_total_price())


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(
        source='category.name', read_only=True, allow_null=True)
    lowest_price = serializers.SerializerMethodField()
    listings_count = serializers.SerializerMethodField()
    available_on = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'title', 'slug', 'brand',
            'category', 'category_name',
            'main_image',
            'lowest_price', 'listings_count', 'available_on',
            'is_active', 'created_at',
            # 'description', 'model_number', 'last_synced', 'updated_at',
        ]

    def get_lowest_price(self, obj):
        price = obj.get_lowest_price()
        return float(price) if price else None

    def get_listings_count(self, obj):
        return obj.listings.filter(is_available=True).count()

    def get_available_on(self, obj):
        platforms = obj.listings.filter(is_available=True).values_list(
            'platform__name', flat=True).distinct()
        return list(platforms)


class ProductDetailSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    images        = ProductImageSerializer(many=True, read_only=True)
    listings      = serializers.SerializerMethodField()
    lowest_price  = serializers.SerializerMethodField()

    class Meta:
        model  = Product
        fields = [
            'id', 'title', 'slug', 'description',
            'category', 'category_name',
            'brand', 'main_image', 'images',
            'lowest_price', 'listings',
            'is_active', 'created_at',
        ]

    def get_lowest_price(self, obj):
        price = obj.get_lowest_price()
        return float(price) if price else None

    def get_listings(self, obj):
        # প্রতিটা platform থেকে শুধু সবচেয়ে সস্তা ১টা listing
        listings = obj.listings.filter(
            is_available=True
        ).select_related('platform').order_by('platform', 'price')

        seen_platforms = set()
        unique_listings = []
        for listing in listings:
            if listing.platform_id not in seen_platforms:
                seen_platforms.add(listing.platform_id)
                unique_listings.append(listing)

        return ProductListingSerializer(unique_listings, many=True).data


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
    product_title = serializers.CharField(source='product.title', read_only=True)

    class Meta:
        model  = CartItem
        fields = ['id', 'product', 'product_title', 'quantity']

    def validate(self, attrs):
        request = self.context.get('request')
        user    = request.user if request else None
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
    product = ProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), source='product', write_only=True
    )

    class Meta:
        model = Favorite
        fields = ['id', 'product', 'product_id', 'created_at']
        read_only_fields = ['id', 'created_at']