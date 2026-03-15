from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError


class CustomAd(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),      
        ('active', 'Active'),       
        ('paused', 'Paused'),
        ('expired', 'Expired'),     
        ('rejected', 'Rejected'),   
    ]
    
    advertiser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ads'
    )
    title       = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    image       = models.ImageField(
        upload_to='ads/', help_text="Recommended size: 1200x628px")
    target_url  = models.URLField(help_text="Valid URL required")
    target_section = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    # Budget & Priority Logic
    total_budget = models.DecimalField(max_digits=10, decimal_places=2)
    spent_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0)
    priority_weight = models.PositiveIntegerField(
        default=1,
        help_text="Higher value = higher priority (1-100)"
    )
    is_premium = models.BooleanField(
        default=False,
        help_text="Premium ads get 5x weight boost"
    )

    # Performance Tracking
    clicks      = models.PositiveIntegerField(default=0)
    impressions = models.PositiveIntegerField(default=0)

    # Validity & Approval
    start_date  = models.DateTimeField(default=timezone.now)
    end_date    = models.DateTimeField()
    is_approved = models.BooleanField(default=False)
    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    cta_text    = models.CharField(max_length=50, default="Learn More")

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'is_approved', 'start_date']),
        ]

    def __str__(self):
        return f"{self.title} - {self.advertiser.email}"

    def clean(self):
        """Custom validation"""
        if self.end_date <= self.start_date:
            raise ValidationError("End date must be after start date")
        if self.priority_weight > 100:
            raise ValidationError("Priority weight cannot exceed 100")
        if self.total_budget <= 0:
            raise ValidationError("Budget must be greater than 0")

    @property
    def ctr(self):
        """Click Through Rate calculation"""
        if self.impressions == 0:
            return 0
        return round((self.clicks / self.impressions) * 100, 2)

    @property
    def budget_remaining(self):
        return float(self.total_budget - self.spent_amount)
    
    def check_and_expire(self):
        if self.status == 'active':
            if self.budget_remaining <= 0 or self.end_date <= timezone.now():
                self.status = 'expired'
                self.save(update_fields=['status'])


class AdSetting(models.Model):
    """To control the amount of deduction per click from the admin dashboard"""
    cpc_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.50,
        help_text="per click amount to charge advertisers"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ad Setting"
        verbose_name_plural = "Ad Settings"

    def __str__(self):
        return f"Current CPC: {self.cpc_amount}"

    def save(self, *args, **kwargs):
        # This will ensure that there will only be one settings row in the database (Singleton)
        self.pk = 1
        super().save(*args, **kwargs)


class AdvertiserRequest(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='advertiser_request'
    )
    business_name    = models.CharField(max_length=255)
    business_details = models.TextField()
    website          = models.URLField(blank=True, null=True)
    applied_at       = models.DateTimeField(auto_now_add=True)
    is_reviewed      = models.BooleanField(default=False)
    reviewed_at      = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-applied_at']

    def __str__(self):
        return f"{self.business_name} - {self.user.email}"

    def approve(self):
        """Approve advertiser request"""
        self.user.ads_provided = True
        self.user.save()
        self.is_reviewed = True
        self.reviewed_at = timezone.now()
        self.save()

    def reject(self, reason=""):
        """Reject advertiser request"""
        self.is_reviewed = True
        self.reviewed_at = timezone.now()
        self.rejection_reason = reason
        self.save()


"""--------------Add AdReview model------------------"""

class AdReview(models.Model):
    """Admin review/rejection records"""
    ad = models.ForeignKey(
        CustomAd, on_delete=models.CASCADE, related_name='reviews')
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='reviewed_ads'
    )

    STATUS_CHOICES = [
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('needs_changes', 'Needs Changes')
    ]

    status      = models.CharField(max_length=20, choices=STATUS_CHOICES)
    feedback    = models.TextField()
    reviewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-reviewed_at']

    def __str__(self):
        return f"{self.ad.title} - {self.status}"


class AdDailyPerformance(models.Model):
    ad = models.ForeignKey(
        CustomAd, 
        on_delete=models.CASCADE, 
        related_name='daily_performance'
    )
    date        = models.DateField()
    impressions = models.PositiveIntegerField(default=0)
    clicks      = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('ad', 'date')
        ordering = ['date']

    def __str__(self):
        return f"{self.ad.title} - {self.date}"