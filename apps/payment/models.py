from django.db import models
from account.models import User
from store.models import SellerProduct, SellerProfile, Order


class Payment(models.Model):
    STATUS_CHOICES = [
        ('PENDING',   'Pending'),
        ('PAID',      'Paid'),
        ('FAILED',    'Failed'),
        ('REFUNDED',  'Refunded'),
        ('CANCELLED', 'Cancelled'),
    ]
    ad = models.ForeignKey('custom_ads.CustomAd', on_delete=models.SET_NULL, 
                            null=True, blank=True, related_name='payments')
    payment_type = models.CharField(max_length=20, choices=[('STORE', 'Store Product'), ('AD', 'Custom Ad')], default='STORE')
    buyer               = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    seller_product      = models.ForeignKey(SellerProduct, on_delete=models.SET_NULL, 
                            null=True, related_name='payments')
    order               = models.OneToOneField(Order, on_delete=models.SET_NULL, null=True, 
                            blank=True, related_name='payment')
    quantity            = models.PositiveIntegerField(default=1)

    # Shipping details (for store products)
    shipping_address    = models.TextField(blank=True)
    shipping_first_name = models.CharField(max_length=100, blank=True)
    shipping_last_name  = models.CharField(max_length=100, blank=True)
    shipping_address_line1 = models.CharField(max_length=255, blank=True)
    shipping_address_line2 = models.CharField(max_length=255, blank=True)  # Apt/Suite, optional
    shipping_city       = models.CharField(max_length=100, blank=True)
    shipping_state      = models.CharField(max_length=100, blank=True)
    shipping_zip_code   = models.CharField(max_length=20, blank=True)
    shipping_country    = models.CharField(max_length=100, blank=True)
    
    coupon_code         = models.CharField(max_length=50, blank=True)
    note                = models.TextField(blank=True)
    unit_price          = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount        = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount     = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    final_amount        = models.DecimalField(max_digits=10, decimal_places=2)
    balance_used        = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency            = models.CharField(max_length=10, default='usd')
    stripe_checkout_session_id = models.CharField(max_length=500, blank=True)
    stripe_payment_intent_id = models.CharField(max_length=500, blank=True)
    stripe_checkout_url = models.URLField(max_length=1000, blank=True)
    status              = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    item_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    service_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at          = models.DateTimeField(auto_now_add=True)
    updated_at          = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Payment #{self.id} - {self.buyer.email} - {self.status}"


class SellerPayout(models.Model):
    STATUS_CHOICES = [
        ('PENDING',    'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED',  'Completed'),
        ('FAILED',     'Failed'),
    ]
    seller               = models.ForeignKey(SellerProfile, on_delete=models.CASCADE, related_name='payouts')
    payment              = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name='payouts')
    order                = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name='payouts')
    gross_amount         = models.DecimalField(max_digits=10, decimal_places=2)
    platform_fee_percent = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    platform_fee_amount  = models.DecimalField(max_digits=10, decimal_places=2)
    seller_amount        = models.DecimalField(max_digits=10, decimal_places=2)
    stripe_account_id    = models.CharField(max_length=200, blank=True)
    stripe_transfer_id   = models.CharField(max_length=200, blank=True)
    stripe_payout_id     = models.CharField(max_length=200, blank=True)
    status               = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    failure_reason       = models.TextField(blank=True)
    created_at           = models.DateTimeField(auto_now_add=True)
    updated_at           = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Payout #{self.id} to {self.seller.shop_name} - {self.seller_amount}"


class SubscriptionPlan(models.Model):
    PLAN_CHOICES = [
        ('FREE', 'Free Trial'),
        ('PRO_MONTHLY', 'Dealnux PRO'),
        ('PRO_MAX_YEARLY', 'Dealnux PRO MAX'),
        ('ULTIMATE_MONTHLY', 'Dealnux ULTIMATE'),
        ('ULTIMANIA_YEARLY', 'Dealnux ULTIMANIA'),
    ]
    name = models.CharField(max_length=100)
    plan_type = models.CharField(max_length=20, choices=PLAN_CHOICES)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    trial_days = models.PositiveIntegerField(default=14, help_text="How long is the free trial?")
    duration_months = models.PositiveIntegerField(default=1)
    features = models.JSONField(default=list, blank=True)

    clicks_per_day = models.PositiveIntegerField(default=5)
    price_alerts_limit = models.IntegerField(default=5) # -1 == Unlimited
    has_ai_optimization = models.BooleanField(default=False)
    has_barcode_scanning = models.BooleanField(default=True)
    
    stripe_price_id = models.CharField(max_length=200, blank=True) 
    apple_product_id = models.CharField(max_length=200, blank=True, help_text="Apple App Store Product ID (e.g. com.dealnux.app.premium.monthly)")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} (${self.price})"


class UserSubscription(models.Model):
    STATUS_CHOICES = [
        ('TRIAL', 'Free Trial'),
        ('ACTIVE', 'Active'),
        ('EXPIRED', 'Expired'),
        ('CANCELLED', 'Cancelled'),
    ]
    user             = models.OneToOneField(User, on_delete=models.CASCADE, related_name='subscription')
    plan             = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True)
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default='TRIAL')
    trial_started_at = models.DateTimeField(auto_now_add=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    daily_click_count = models.PositiveIntegerField(default=0)
    last_click_date = models.DateField(null=True, blank=True)
    started_at       = models.DateTimeField(null=True, blank=True)
    expires_at       = models.DateTimeField(null=True, blank=True)

    # Payment gateway tracking
    payment_gateway = models.CharField(max_length=20, default='STRIPE', choices=[('STRIPE', 'Stripe'), ('APPLE', 'Apple'), ('FREE', 'Free Trial')])

    # Stripe subscription details
    stripe_subscription_id = models.CharField(max_length=200, blank=True)
    stripe_customer_id     = models.CharField(max_length=200, blank=True)

    # Apple IAP subscription details
    apple_original_transaction_id = models.CharField(max_length=200, blank=True, db_index=True)
    apple_latest_transaction_id   = models.CharField(max_length=200, blank=True)

    
    @property
    def is_active(self):
        from django.utils import timezone
        now = timezone.now()
        if self.status == 'TRIAL':
            return now <= self.trial_ends_at
        if self.status == 'ACTIVE':
            return self.expires_at is None or now <= self.expires_at
        return False
    
    @property
    def days_remaining(self):
        from django.utils import timezone
        if self.status == 'TRIAL':
            delta = self.trial_ends_at - timezone.now()
            return max(0, delta.days)
        return None


# store/models.py

class PayoutRecord(models.Model):
    seller = models.ForeignKey(SellerProfile, on_delete=models.CASCADE, related_name='payout_records')
    payout_id = models.CharField(max_length=20, unique=True) # PAY-XXXX
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=50, default="Stripe Transfer")
    status = models.CharField(max_length=20, default="Paid")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.payout_id} - {self.amount}"