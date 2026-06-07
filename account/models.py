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
    balance         = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    ads_provided    = models.BooleanField(default=False)
    is_active       = models.BooleanField(default=False)
    otp             = models.CharField(max_length=4, blank=True, null=True) 
    profile_setup_completed = models.BooleanField(default=False)

    total_lifetime_savings = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    savings_coupons = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    savings_comparison = models.DecimalField(max_digits=10, decimal_places=2, default=0)

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


class DeviceToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='fcm_tokens')
    fcm_token = models.TextField(unique=True)
    device_type = models.CharField(max_length=20, blank=True) # android, ios, web
    created_at = models.DateTimeField(auto_now_add=True)