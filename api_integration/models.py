from django.db import models
from django.utils.text import slugify
from django.core.validators import MinValueValidator, MaxValueValidator


class Platform(models.Model):
    """E-commerce platform (eBay, Amazon, etc.)"""
    
    name = models.CharField(max_length=50, unique=True)
    code = models.CharField(max_length=20, unique=True)  # ebay, amazon, aliexpress
    logo = models.ImageField(upload_to='platform_logos/', blank=True)
    api_enabled = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Category(models.Model):
    """Product categories"""
    
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='children')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.name


class Product(models.Model):
    """Main product model - normalized data across platforms"""
    
    # Basic Information
    title = models.CharField(max_length=500)
    slug = models.SlugField(max_length=500, unique=True)
    description = models.TextField(blank=True)
    
    # Category
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    
    # Identifiers
    brand = models.CharField(max_length=200, blank=True)
    model_number = models.CharField(max_length=200, blank=True)
    
    # Images
    main_image = models.URLField(max_length=1000, blank=True)
    
    # Meta
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['title']),
            models.Index(fields=['brand']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:500]
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.title
    
    def get_lowest_price(self):
        """Get lowest price across all platforms"""
        listings = self.listings.filter(is_available=True)
        if listings.exists():
            return listings.order_by('price').first().price
        return None
    
    def get_all_listings(self):
        """Get all active listings for this product"""
        return self.listings.filter(is_available=True).select_related('platform')


class ProductListing(models.Model):
    """Platform-specific product listing"""
    
    CONDITION_CHOICES = [
        ('NEW', 'New'),
        ('USED', 'Used'),
        ('REFURBISHED', 'Refurbished'),
        ('OPEN_BOX', 'Open Box'),
        ('OTHER', 'Other'),
    ]
    
    # Relations
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='listings')
    platform = models.ForeignKey(Platform, on_delete=models.CASCADE, related_name='listings')
    
    # Platform-specific ID
    external_id = models.CharField(max_length=200)  # Item ID from platform
    external_url = models.URLField(max_length=1000)  # Link to product on platform
    
    # Price
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='USD')
    original_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    # Product Details
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='NEW')
    quantity = models.IntegerField(default=0)
    
    # Seller
    seller_username = models.CharField(max_length=200, blank=True)
    seller_rating = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, 
                                       validators=[MinValueValidator(0), MaxValueValidator(100)])
    seller_feedback_count = models.IntegerField(default=0)
    
    # Location
    item_location = models.CharField(max_length=500, blank=True)
    ships_from_country = models.CharField(max_length=10, blank=True)
    
    # Shipping
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping_currency = models.CharField(max_length=10, default='USD')
    free_shipping = models.BooleanField(default=False)
    estimated_delivery_days = models.IntegerField(null=True, blank=True)
    
    # Returns
    returns_accepted = models.BooleanField(default=False)
    return_period_days = models.IntegerField(null=True, blank=True)
    
    # Availability
    is_available = models.BooleanField(default=True)
    last_checked = models.DateTimeField(auto_now=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['price']
        unique_together = ['platform', 'external_id']
        indexes = [
            models.Index(fields=['platform', 'external_id']),
            models.Index(fields=['price']),
            models.Index(fields=['is_available']),
        ]
    
    def __str__(self):
        return f"{self.product.title} on {self.platform.name} - {self.price} {self.currency}"
    
    def get_total_price(self):
        """Get total price including shipping"""
        return self.price + (self.shipping_cost if not self.free_shipping else 0)


class ProductImage(models.Model):
    """Additional product images"""
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image_url = models.URLField(max_length=1000)
    alt_text = models.CharField(max_length=500, blank=True)
    order = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['order', 'id']
    
    def __str__(self):
        return f"Image for {self.product.title}"


class ProductSpecification(models.Model):
    """Product specifications/attributes"""
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='specifications')
    name = models.CharField(max_length=200)  # e.g., "Screen Size", "Processor"
    value = models.CharField(max_length=500)  # e.g., "15.6 inch", "Intel Core i7"
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
        unique_together = ['product', 'name']
    
    def __str__(self):
        return f"{self.name}: {self.value}"


class PriceHistory(models.Model):
    """Track price changes over time"""
    
    listing = models.ForeignKey(ProductListing, on_delete=models.CASCADE, related_name='price_history')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10)
    recorded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-recorded_at']
        verbose_name_plural = 'Price Histories'
    
    def __str__(self):
        return f"{self.listing.product.title} - {self.price} {self.currency} on {self.recorded_at}"