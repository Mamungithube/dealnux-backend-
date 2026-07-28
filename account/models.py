from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils import timezone
from datetime import timedelta 
import uuid

# Create your models here.

def get_expiry():
    return timezone.now() + timedelta(days=365)


"""---------Custom User Manager---------"""
class UserManager(BaseUserManager):
    def create_user(self, email,password = None , **extra_fields):
        if not email:
            raise ValueError('The Email must be provided')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password = None , **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)
    

"""---------Custom User Model---------"""
class User(AbstractUser):
    username        = None
    email           = models.EmailField(unique=True)
    name            = models.CharField(max_length=255)
    first_name      = models.CharField(max_length=100, blank=True) 
    last_name       = models.CharField(max_length=100, blank=True)
    address         = models.TextField(blank=True, null=True)
    referral_code   = models.CharField(max_length=12, unique=True, blank=True, null=True)
    has_claimed_referral = models.BooleanField(default=False)
    referred_by     = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='referrals')
    has_referral_reward_awarded = models.BooleanField(default=False)
    balance         = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    ads_provided    = models.BooleanField(default=False)
    is_active       = models.BooleanField(default=False)
    otp             = models.CharField(max_length=4, blank=True, null=True) 
    profile_setup_completed = models.BooleanField(default=False)

    total_lifetime_savings = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    savings_coupons = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    savings_comparison = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    agreed_to_terms = models.BooleanField(default=False)
    agreed_to_privacy = models.BooleanField(default=False)

    cookie_consent = models.BooleanField(default=False)
    cookie_consent_date = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.name or self.email
    
    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = uuid.uuid4().hex[:8].upper()
            while User.objects.filter(referral_code=self.referral_code).exists():
                self.referral_code = uuid.uuid4().hex[:8].upper()
        super().save(*args, **kwargs)

"""----------------------Profile Model----------------------------------"""

class Profile(models.Model):
    user            = models.OneToOneField(User, on_delete=models.CASCADE)
    
    address          = models.CharField(max_length=255, blank=True)   
    address_2        = models.CharField(max_length=255, blank=True)  
    city             = models.CharField(max_length=100, blank=True)
    state            = models.CharField(max_length=100, blank=True)
    zip_code         = models.CharField(max_length=20, blank=True)
    country          = models.CharField(max_length=100, blank=True)

    interests       = models.TextField(default=list, blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)


class SiteSettings(models.Model):
    referral_reward_amount = models.DecimalField(
        max_digits=100000000,
        decimal_places=2,
        default=10.00,
        verbose_name="Referral Reward Amount ($)",
        help_text="Amount in USD added to the referrer's account balance when a referred user subscribes and completes their first purchase."
    )

    class Meta:
        verbose_name = 'Referral Reward Settings'
        verbose_name_plural = 'Referral Reward Settings'

    def save(self, *args, **kwargs):
        self.pk = 1 
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj