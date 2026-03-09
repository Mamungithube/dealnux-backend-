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
    buyer                       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    seller_product              = models.ForeignKey(SellerProduct, on_delete=models.SET_NULL, null=True, related_name='payments')
    order                       = models.OneToOneField(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name='payment')
    quantity                    = models.PositiveIntegerField(default=1)
    shipping_address            = models.TextField(blank=True)
    coupon_code                 = models.CharField(max_length=50, blank=True)
    note                        = models.TextField(blank=True)
    unit_price                  = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount                = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount             = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    final_amount                = models.DecimalField(max_digits=10, decimal_places=2)
    currency                    = models.CharField(max_length=10, default='usd')
    stripe_checkout_session_id  = models.CharField(max_length=500, blank=True)
    stripe_payment_intent_id    = models.CharField(max_length=500, blank=True)
    stripe_checkout_url         = models.URLField(max_length=1000, blank=True)
    status                      = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at                  = models.DateTimeField(auto_now_add=True)
    updated_at                  = models.DateTimeField(auto_now=True)

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
    seller                  = models.ForeignKey(SellerProfile, on_delete=models.CASCADE, related_name='payouts')
    payment                 = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='payouts')
    order                   = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, related_name='payouts')
    gross_amount            = models.DecimalField(max_digits=10, decimal_places=2)
    platform_fee_percent    = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    platform_fee_amount     = models.DecimalField(max_digits=10, decimal_places=2)
    seller_amount           = models.DecimalField(max_digits=10, decimal_places=2)
    stripe_account_id       = models.CharField(max_length=200, blank=True)
    stripe_transfer_id      = models.CharField(max_length=200, blank=True)
    stripe_payout_id        = models.CharField(max_length=200, blank=True)
    status                  = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    failure_reason          = models.TextField(blank=True)
    created_at              = models.DateTimeField(auto_now_add=True)
    updated_at              = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Payout #{self.id} to {self.seller.shop_name} - {self.seller_amount}"
