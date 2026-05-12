from django.db import models
from django.utils import timezone
from account.models import User
from api_integration.models import Product, ProductListing, Platform, Category
from dealnux import settings
import string
import random
# ============================================================================
# Seller Request — You can become a Seller if the Admin approves.
# ============================================================================


class SellerRequest(models.Model):
    STATUS_CHOICES = [('PENDING', 'Pending'), ('APPROVED',
                                               'Approved'), ('REJECTED', 'Rejected')]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='seller_request')

    # --- STEP 1: Business Details ---
    trade_name = models.CharField(max_length=255, null=True, blank=True)
    legal_business_type = models.CharField(
        max_length=100, null=True, blank=True)
    business_reg_number = models.CharField(
        max_length=100, blank=True, null=True)

    # --- STEP 2: Primary Contact ---
    contact_full_name = models.CharField(max_length=255, null=True, blank=True)
    job_title = models.CharField(max_length=100, blank=True, null=True)
    contact_email = models.EmailField(null=True, blank=True)
    contact_phone = models.CharField(max_length=20, null=True, blank=True)

    # --- STEP 3: Product Catalog ---
    categories = models.ManyToManyField(
        Category, related_name='seller_requests', blank=True)
    estimated_sku_count = models.CharField(
        max_length=50, null=True, blank=True)
    min_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    product_conditions = models.JSONField(default=list, blank=True)
    owns_inventory = models.BooleanField(default=True)

    # --- STEP 4: Fulfillment & Shipping ---
    fulfillment_methods = models.JSONField(default=list, blank=True)
    shipping_regions = models.JSONField(default=list, blank=True)

    # --- STEP 5: Return Policy ---
    return_policy_description = models.TextField(null=True, blank=True)
    return_policy_document = models.FileField(
        upload_to='seller_docs/policies/', blank=True, null=True)

    # --- STEP 6 & 7: Compliance & Policy ---
    agreed_to_compliance = models.BooleanField(default=False)
    agreed_to_prohibited_items = models.BooleanField(default=False)

    # --- STEP 8: Business History & Docs ---
    has_prior_experience = models.BooleanField(default=False)
    experience_description = models.TextField(blank=True, null=True)

    government_id = models.FileField(
        upload_to='seller_docs/ids/', null=True, blank=True)
    business_license = models.FileField(
        upload_to='seller_docs/licenses/', null=True, blank=True)
    utility_bill = models.FileField(
        upload_to='seller_docs/utility/', null=True, blank=True)

    # --- STEP 10: Digital Signature ---
    digital_signature = models.CharField(max_length=255, null=True, blank=True)

    # --- Admin & Timestamps ---
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='PENDING')
    admin_note = models.TextField(blank=True, null=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.trade_name or self.user.email} Application"

    # store/models.py এর ভেতরে SellerRequest ক্লাসের approve মেথড

    def approve(self, admin_user):

        self.status = 'APPROVED'
        self.reviewed_at = timezone.now()
        self.save()

        SellerProfile.objects.update_or_create(
            user=self.user,
            defaults={
                'shop_name': self.trade_name,
                'is_active': True
            }
        )

    def reject(self, admin_user, note=''):

        from django.utils import timezone

        self.status = 'REJECTED'
        self.admin_note = note
        self.reviewed_by = admin_user
        self.reviewed_at = timezone.now()
        self.save()


# ============================================================================
# Seller Profile — Approved seller information
# ============================================================================

class SellerProfile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='seller_profile')

    # Shop Identity (it is good to keep it in use so that it can be recognized as a shop)
    shop_name = models.CharField(max_length=255)
    shop_logo = models.ImageField(
        upload_to='seller_logos/', blank=True, null=True)
    shop_description = models.TextField(blank=True)

    # Wallet system (as per dashboard screenshot and doc)
    pending_balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=0)
    available_balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=0)
    total_earnings = models.DecimalField(
        max_digits=12, decimal_places=2, default=0)

    # Stripe Connect Data Only (According to the doc)
    stripe_account_id = models.CharField(max_length=200, blank=True)
    stripe_onboarding_completed = models.BooleanField(default=False)

    # Stats (can be calculated on the fly, but keeping it here for dashboard performance)
    total_products = models.PositiveIntegerField(default=0)
    total_orders = models.PositiveIntegerField(default=0)
    seller_score = models.IntegerField(default=0)

    pending_balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=0)
    available_balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=0)
    total_withdrawn = models.DecimalField(
        max_digits=12, decimal_places=2, default=0)

    local_pickup_active = models.BooleanField(default=False)
    local_delivery_active = models.BooleanField(default=False)
    standard_shipping_active = models.BooleanField(default=True)
    order_processing_time = models.CharField(max_length=50, default="1-2 Business Days")
    preferred_couriers = models.JSONField(default=list, blank=True) # ['FedEx', 'DHL']

    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.shop_name} - Stripe: {self.stripe_account_id or 'Not Connected'}"


# ============================================================================
# Seller Product — Product added by the Seller himself
# ============================================================================

class SellerProduct(models.Model):
    """
    Product added by the seller himself.
    If admin approves, it will be linked to api_integration.Product
    and a 'local' platform ProductListing will be created.
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

    seller = models.ForeignKey(
        SellerProfile, on_delete=models.CASCADE, related_name='products')
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True)

    # Basic info
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    brand = models.CharField(max_length=200, blank=True)
    model_number = models.CharField(max_length=200, blank=True)

    # Price & stock
    price = models.DecimalField(max_digits=10, decimal_places=2)
    original_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=10, default='USD')
    quantity = models.PositiveIntegerField(default=1)
    condition = models.CharField(
        max_length=20, choices=CONDITION_CHOICES, default='NEW')

    # Images
    main_image = models.ImageField(
        upload_to='seller_products/', blank=True, null=True)

    # Shipping
    free_shipping = models.BooleanField(default=False)
    shipping_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=0)
    estimated_delivery_days = models.PositiveIntegerField(
        null=True, blank=True)

    # Returns
    returns_accepted = models.BooleanField(default=True)
    return_period_days = models.PositiveIntegerField(default=7)

    # Admin review
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    admin_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                    blank=True, related_name='reviewed_seller_products')
    reviewed_at = models.DateTimeField(null=True, blank=True)

    # Link to global Product & Listing (set after approval)
    linked_product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True,
                                       blank=True, related_name='seller_products')
    linked_listing = models.ForeignKey(ProductListing, on_delete=models.SET_NULL, null=True,
                                       blank=True, related_name='seller_product_source')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Seller Product'
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
        Admin Approval:
            1. api_integration.Product will be created/searched
            2. Productlisting will be on 'local' platform
            3. linked_product + linked_listing will be set
        """
        from django.utils.text import slugify

        self.status = 'APPROVED'
        self.reviewed_by = admin_user
        self.reviewed_at = timezone.now()

        # 'local' platform get_or_create — separate platform entry for each seller
        # so that the shop name is shown in price comparison
        local_platform, _ = Platform.objects.update_or_create(
            code=f"local-seller-{self.seller.id}",
            defaults={
                'name': self.seller.shop_name,
                'api_enabled': False,
            }
        )
        # If you change the shop name, update the platform name as well.
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

        # ProductListing
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
        self.status = 'REJECTED'
        self.admin_note = note
        self.reviewed_by = admin_user
        self.reviewed_at = timezone.now()
        self.save()


# ============================================================================
# Product Review — Buyer can review the product after purchase
# ============================================================================

class ProductReview(models.Model):
    RATING_CHOICES = [(i, i) for i in range(1, 6)]

    product = models.ForeignKey(
        SellerProduct, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_product_reviews')
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('product', 'user')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} → {self.product.title} ({self.rating}★)"


# ============================================================================
# Seller Product Image — Multiple images
# ============================================================================

class SellerProductImage(models.Model):
    product = models.ForeignKey(
        SellerProduct, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='seller_product_images/')
    alt_text = models.CharField(max_length=300, blank=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"Image for {self.product.title}"


# ============================================================================
# Order — Purchase from Seller product
# ============================================================================
class Order(models.Model):
    STATUS_CHOICES = [
        ('PENDING',    'Pending'),
        ('CONFIRMED',  'Confirmed'),
        ('SHIPPED',    'Shipped'),
        ('DELIVERED',  'Delivered'),
        ('ACCEPTED',   'Accepted by Buyer'), 
        ('CANCELLED',  'Cancelled'),
        ('REFUNDED',   'Refunded'),
    ]

    FAULT_CHOICES = [
        ('NONE',   'None'),
        ('SELLER', 'Seller at Fault'), 
        ('BUYER',  'Buyer at Fault'), 
    ]

    buyer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='orders')
    seller = models.ForeignKey(
        SellerProfile, on_delete=models.SET_NULL, null=True, related_name='orders')

    # ঐ সময়ের প্রোডাক্ট ও লিস্টিংয়ের তথ্য
    seller_product = models.ForeignKey(
        SellerProduct, on_delete=models.SET_NULL, null=True)
    listing = models.ForeignKey(
        ProductListing, on_delete=models.SET_NULL, null=True)

    # --- Pricing Breakdown (As per Client Doc) ---
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=2)  

    discount_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0) 

    item_total = models.DecimalField(
        max_digits=10, decimal_places=2, default=0) 
    shipping_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=0) 
    # Dealnux Concession Fee (5-10%)
    service_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=0)

    # Grand Total (বায়ার মোট যা পে করেছে)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    currency = models.CharField(max_length=10, default='USD')

    # --- Delivery & Logistics ---
    shipping_address = models.TextField()
    tracking_number = models.CharField(max_length=200, blank=True)
    note = models.TextField(blank=True)

    # --- Escrow & Acceptance Logic ---
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='PENDING')
    is_accepted_by_buyer = models.BooleanField(
        default=False)  # True if buyer accepts
    accepted_at = models.DateTimeField(null=True, blank=True)

    # --- Dispute & Refund Logic (As per Client Doc) ---
    fault_party = models.CharField(
        max_length=10, choices=FAULT_CHOICES, default='NONE')
    refund_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0)

    coupon = models.ForeignKey(
        'Coupon', on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    order_number = models.CharField(max_length=20, unique=True, editable=False, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order #{self.id} by {self.buyer.email}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            # Generating a 4-digit random ID starting with
            random_id = ''.join(random.choices(string.digits, k=4))
            self.order_number = f"#ORD-{random_id}"
            
            # Check to ensure uniqueness
            while Order.objects.filter(order_number=self.order_number).exists():
                random_id = ''.join(random.choices(string.digits, k=4))
                self.order_number = f"#ORD-{random_id}"

        # Payment calculation logic (Unchanged)
        if self.unit_price and self.quantity:
            subtotal = (self.unit_price * self.quantity) - self.discount_amount
            self.item_total = subtotal
            self.total_price = subtotal + self.shipping_fee + self.service_fee
        
        super().save(*args, **kwargs)


# ============================================================================
# Coupon — Seller can give coupon himself
# ============================================================================

class Coupon(models.Model):
    DISCOUNT_TYPE_CHOICES = [
        ('PERCENTAGE', 'Percentage'),
        ('FIXED',      'Fixed Amount'),
    ]

    seller = models.ForeignKey(
        SellerProfile, on_delete=models.CASCADE, related_name='coupons')
    code = models.CharField(max_length=50, unique=True)
    discount_type = models.CharField(
        max_length=20, choices=DISCOUNT_TYPE_CHOICES, default='PERCENTAGE')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    min_order_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0)
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    used_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

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

