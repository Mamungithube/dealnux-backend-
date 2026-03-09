from django.db import models
from django.utils import timezone
from account.models import User
from api_integration.models import Product, ProductListing, Platform, Category


# ============================================================================
# Seller Request — Admin approve করলে Seller হওয়া যাবে
# ============================================================================

class SellerRequest(models.Model):
    """
    User seller হতে চাইলে এই request পাঠাবে।
    Admin approve/reject করবে।
    """

    STATUS_CHOICES = [
        ('PENDING',  'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]

    user            = models.OneToOneField(User, on_delete=models.CASCADE, related_name='seller_request')

    # Shop info
    shop_name       = models.CharField(max_length=255)
    shop_description= models.TextField(blank=True)

    # Contact
    phone_number    = models.CharField(max_length=20)

    # Documents (optional upload)
    nid_document      = models.FileField(upload_to='seller_docs/nid/', blank=True, null=True)
    business_document = models.FileField(upload_to='seller_docs/business/', blank=True, null=True)

    # Admin action
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    admin_note      = models.TextField(blank=True)   # reject reason ইত্যাদি
    reviewed_by     = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reviewed_seller_requests'
    )
    reviewed_at     = models.DateTimeField(null=True, blank=True)

    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name        = 'Seller Request'
        verbose_name_plural = 'Seller Requests'

    def __str__(self):
        return f"{self.user.email} → {self.shop_name} [{self.status}]"

    def approve(self, admin_user):
        """Admin approve করলে SellerProfile তৈরি হবে এবং User কে seller mark করা হবে।"""
        self.status      = 'APPROVED'
        self.reviewed_by = admin_user
        self.reviewed_at = timezone.now()
        self.save()

        # SellerProfile create — bank info পরে seller নিজে profile এ যোগ করবে
        SellerProfile.objects.get_or_create(
            user=self.user,
            defaults={
                'shop_name':        self.shop_name,
                'shop_description': self.shop_description,
                'phone_number':     self.phone_number,
            }
        )

        # User model এ is_seller flag set করো
        self.user.ads_provided = True   # existing field reuse, অথবা নিচে আলাদা field যোগ করুন
        self.user.save(update_fields=['ads_provided'])

    def reject(self, admin_user, note=''):
        self.status      = 'REJECTED'
        self.admin_note  = note
        self.reviewed_by = admin_user
        self.reviewed_at = timezone.now()
        self.save()


# ============================================================================
# Seller Profile — Approved seller দের তথ্য
# ============================================================================

class SellerProfile(models.Model):
    user            = models.OneToOneField(User, on_delete=models.CASCADE, related_name='seller_profile')

    shop_name       = models.CharField(max_length=255)
    shop_description= models.TextField(blank=True)
    shop_logo       = models.ImageField(upload_to='seller_logos/', blank=True, null=True)
    phone_number    = models.CharField(max_length=20)

    # Payment
    bank_name       = models.CharField(max_length=200, blank=True)
    bank_account_number = models.CharField(max_length=100, blank=True)
    bkash_number    = models.CharField(max_length=20, blank=True)

    # Stats
    total_products  = models.PositiveIntegerField(default=0)
    total_orders    = models.PositiveIntegerField(default=0)
    total_earnings  = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    is_active       = models.BooleanField(default=True)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.shop_name} ({self.user.email})"


# ============================================================================
# Seller Product — Seller নিজে যোগ করা product
# ============================================================================

class SellerProduct(models.Model):
    """
    Seller নিজে add করা product।
    Admin approve হলে api_integration.Product এ link হবে
    এবং একটা 'local' platform ProductListing তৈরি হবে।
    """

    STATUS_CHOICES = [
        ('DRAFT',    'Draft'),
        ('PENDING',  'Pending Review'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]

    CONDITION_CHOICES = [
        ('NEW',         'New'),
        ('USED',        'Used'),
        ('REFURBISHED', 'Refurbished'),
        ('OPEN_BOX',    'Open Box'),
    ]

    seller          = models.ForeignKey(SellerProfile, on_delete=models.CASCADE, related_name='products')
    category        = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)

    # Basic info
    title           = models.CharField(max_length=500)
    description     = models.TextField(blank=True)
    brand           = models.CharField(max_length=200, blank=True)
    model_number    = models.CharField(max_length=200, blank=True)

    # Price & stock
    price           = models.DecimalField(max_digits=10, decimal_places=2)
    original_price  = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency        = models.CharField(max_length=10, default='USD')
    quantity        = models.PositiveIntegerField(default=1)
    condition       = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='NEW')

    # Images
    main_image      = models.ImageField(upload_to='seller_products/', blank=True, null=True)

    # Shipping
    free_shipping   = models.BooleanField(default=False)
    shipping_cost   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estimated_delivery_days = models.PositiveIntegerField(null=True, blank=True)

    # Returns
    returns_accepted    = models.BooleanField(default=True)
    return_period_days  = models.PositiveIntegerField(default=7)

    # Admin review
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    admin_note      = models.TextField(blank=True)
    reviewed_by     = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reviewed_seller_products'
    )
    reviewed_at     = models.DateTimeField(null=True, blank=True)

    # Link to global Product & Listing (approve হলে তৈরি হবে)
    linked_product  = models.ForeignKey(
        Product, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='seller_products'
    )
    linked_listing  = models.ForeignKey(
        ProductListing, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='seller_product_source'
    )

    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name        = 'Seller Product'
        verbose_name_plural = 'Seller Products'

    def __str__(self):
        return f"{self.title} by {self.seller.shop_name} [{self.status}]"

    @property
    def discount_percentage(self):
        if self.original_price and self.price and self.original_price > self.price:
            return round(((self.original_price - self.price) / self.original_price) * 100, 2)
        return None

    def approve(self, admin_user):
        """
        Admin approve করলে:
        1. api_integration.Product তৈরি/খোঁজা হবে
        2. 'local' Platform এ ProductListing তৈরি হবে
        3. linked_product ও linked_listing set হবে
        """
        from django.utils.text import slugify

        self.status      = 'APPROVED'
        self.reviewed_by = admin_user
        self.reviewed_at = timezone.now()

        # 'local' platform get_or_create — প্রতিটা seller এর জন্য আলাদা platform entry
        # যাতে price comparison এ shop name দেখায়
        local_platform, _ = Platform.objects.get_or_create(
            code=f"local-seller-{self.seller.id}",
            defaults={
                'name': self.seller.shop_name,   # e.g. "Rahman Store"
                'api_enabled': False,
            }
        )
        # Shop name বদলালে platform name ও update করো
        if local_platform.name != self.seller.shop_name:
            local_platform.name = self.seller.shop_name
            local_platform.save(update_fields=['name'])

        # Product তৈরি
        product, _ = Product.objects.get_or_create(
            title=self.title,
            defaults={
                'description':  self.description,
                'brand':        self.brand,
                'model_number': self.model_number,
                'main_image':   self.main_image.url if self.main_image else '',
                'category':     self.category,
            }
        )

        # ProductListing তৈরি
        listing, _ = ProductListing.objects.update_or_create(
            product=product,
            platform=local_platform,
            external_id=f"seller-{self.seller.id}-product-{self.id}",
            defaults={
                'external_url':             '',
                'price':                    self.price,
                'currency':                 self.currency,
                'original_price':           self.original_price,
                'discount_percentage':      self.discount_percentage,
                'condition':                self.condition,
                'quantity':                 self.quantity,
                'seller_username':          self.seller.shop_name,
                'seller_rating':            None,
                'item_location':            'Local',
                'shipping_cost':            self.shipping_cost,
                'free_shipping':            self.free_shipping,
                'estimated_delivery_days':  self.estimated_delivery_days,
                'returns_accepted':         self.returns_accepted,
                'return_period_days':       self.return_period_days,
                'is_available':             True,
            }
        )

        self.linked_product = product
        self.linked_listing = listing
        self.save()

        # Seller stats update
        self.seller.total_products = SellerProduct.objects.filter(
            seller=self.seller, status='APPROVED'
        ).count()
        self.seller.save(update_fields=['total_products'])

    def reject(self, admin_user, note=''):
        self.status      = 'REJECTED'
        self.admin_note  = note
        self.reviewed_by = admin_user
        self.reviewed_at = timezone.now()
        self.save()


# ============================================================================
# Seller Product Image — Multiple images
# ============================================================================

class SellerProductImage(models.Model):
    product     = models.ForeignKey(SellerProduct, on_delete=models.CASCADE, related_name='images')
    image       = models.ImageField(upload_to='seller_product_images/')
    alt_text    = models.CharField(max_length=300, blank=True)
    order       = models.PositiveIntegerField(default=0)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"Image for {self.product.title}"


# ============================================================================
# Order — Seller product থেকে purchase
# ============================================================================

class Order(models.Model):
    STATUS_CHOICES = [
        ('PENDING',    'Pending'),
        ('CONFIRMED',  'Confirmed'),
        ('SHIPPED',    'Shipped'),
        ('DELIVERED',  'Delivered'),
        ('CANCELLED',  'Cancelled'),
        ('REFUNDED',   'Refunded'),
    ]

    buyer           = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    seller          = models.ForeignKey(SellerProfile, on_delete=models.SET_NULL, null=True, related_name='orders')

    # Snapshot of listing at time of order
    seller_product  = models.ForeignKey(SellerProduct, on_delete=models.SET_NULL, null=True)
    listing         = models.ForeignKey(ProductListing, on_delete=models.SET_NULL, null=True)

    quantity        = models.PositiveIntegerField(default=1)
    unit_price      = models.DecimalField(max_digits=10, decimal_places=2)
    total_price     = models.DecimalField(max_digits=10, decimal_places=2)
    currency        = models.CharField(max_length=10, default='USD')

    # Shipping address snapshot
    shipping_address = models.TextField()

    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    tracking_number = models.CharField(max_length=200, blank=True)
    note            = models.TextField(blank=True)   # buyer note

    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order #{self.id} by {self.buyer.email}"

    def save(self, *args, **kwargs):
        # total_price auto calculate
        if self.unit_price and self.quantity:
            self.total_price = self.unit_price * self.quantity
        super().save(*args, **kwargs)


# ============================================================================
# Coupon — Seller নিজে coupon দিতে পারবে
# ============================================================================

class Coupon(models.Model):
    DISCOUNT_TYPE_CHOICES = [
        ('PERCENTAGE', 'Percentage'),
        ('FIXED',      'Fixed Amount'),
    ]

    seller          = models.ForeignKey(SellerProfile, on_delete=models.CASCADE, related_name='coupons')
    code            = models.CharField(max_length=50, unique=True)
    discount_type   = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES, default='PERCENTAGE')
    discount_value  = models.DecimalField(max_digits=10, decimal_places=2)  # % বা টাকা
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_uses        = models.PositiveIntegerField(null=True, blank=True)     # None = unlimited
    used_count      = models.PositiveIntegerField(default=0)
    is_active       = models.BooleanField(default=True)
    expires_at      = models.DateTimeField(null=True, blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.code} ({self.seller.shop_name})"

    @property
    def is_valid(self):
        if not self.is_active:
            return False
        if self.max_uses and self.used_count >= self.max_uses:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True