from decimal import Decimal

from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.files.images import get_image_dimensions

class CustomAd(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),      
        ('active', 'Active'),       
        ('paused', 'Paused'),
        ('expired', 'Expired'),     
        ('rejected', 'Rejected'),   
    ]
    
    advertiser      = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='ads')
    title           = models.CharField(max_length=255)
    description     = models.TextField(blank=True, default="")
    image           = models.ImageField(
        upload_to='ads/', 
        help_text="Ideal size: 1280x720px (16:9), Max 10MB. Formats: JPG, PNG, GIF"
    )
    target_url      = models.URLField(help_text="Valid URL required")
    target_section  = models.CharField(max_length=100, blank=True, null=True)

    # Budget & Priority Logic
    total_budget    = models.DecimalField(max_digits=10, decimal_places=2)
    spent_amount    = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    priority_weight = models.PositiveIntegerField(default=1,help_text="Higher value = higher priority (1-100)"
    )
    is_premium      = models.BooleanField(default=False,help_text="Premium ads get 5x weight boost")

    # Performance Tracking
    clicks          = models.PositiveIntegerField(default=0)
    impressions     = models.PositiveIntegerField(default=0)

    # Validity & Approval
    start_date      = models.DateTimeField(default=timezone.now)
    end_date        = models.DateTimeField()
    is_approved     = models.BooleanField(default=False)
    status          = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    cta_text        = models.CharField(max_length=50, default="Learn More")

    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'is_approved', 'start_date']),
        ]

    def __str__(self):
        return f"{self.title} - {self.advertiser.email}"

    def clean(self):
        """Custom validation for dates, budget, and image"""
        super().clean()

        # 1. Date and budget validation (previous ones)
        if self.end_date <= self.start_date:
            raise ValidationError("End date must be after start date")
        if self.priority_weight > 100:
            raise ValidationError("Priority weight cannot exceed 100")
        if self.total_budget <= 0:
            raise ValidationError("Budget must be greater than 0")

        # ২. image validation (YouTube Thumbnail Size & Security)
        if self.image:
            # File size check (2 MB = 2 * 1024 * 1024 bytes)
            if self.image.size > 2 * 1024 * 1024:
                raise ValidationError("Image size must be less than 2MB.")

            # ডাইমেনশন চেক (Width & Height)
            width, height = get_image_dimensions(self.image)
            
            if width < 640:
                raise ValidationError("Image width must be at least 640 pixels.")
            
            # 1280x720 and 16:9 aspect ratio check
            if width != 1280 or height != 720:
                # You can choose to only show a warning or strictly block it
                raise ValidationError(f"Image size must be 1280x720 pixels. Your image size {width}x{height}")

            # File format check (for security)
            extension = self.image.name.split('.')[-1].lower()
            if extension not in ['jpg', 'jpeg', 'png', 'gif']:
                raise ValidationError("Upload only JPG, PNG, or GIF formats.")

    @property
    def ctr(self):
        """Click Through Rate calculation"""
        if self.impressions == 0:
            return 0
        return round((self.clicks / self.impressions) * 100, 2)

    @property
    def budget_remaining(self):
        return float(self.total_budget - self.spent_amount)

    def save(self, *args, **kwargs):
    # Check before saving.
        if self.status == 'active':
            if self.end_date <= timezone.now() or self.spent_amount >= self.total_budget:
                self.status = 'expired'
        super().save(*args, **kwargs)


class AdSetting(models.Model):
    """To control the amount of deduction per click from the admin dashboard"""
    cpc_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.01'),
        help_text="per click amount to charge advertisers"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ad Setting"
        verbose_name_plural = "Ad Settings"

    def __str__(self):
        return f"Current CPC: {self.cpc_amount}"

    def save(self, *args, **kwargs):
        if self.status == 'active':
            if self.end_date <= timezone.now() or self.spent_amount >= self.total_budget:
                self.status = 'expired'
        if not self.id:
            self.full_clean()

        super().save(*args, **kwargs)


class AdvertiserRequest(models.Model):
    user             = models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='advertiser_request')
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