from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from account.models import User
# Create your models here.


class Privacy_Policy(models.Model):
    content      = models.TextField()
    created_at   = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Privacy Policy (Last Updated: {self.last_updated.strftime('%Y-%m-%d %H:%M:%S')})"
    


class Terms_Of_Service(models.Model):
    content      = models.TextField()
    created_at   = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Terms of Service (Last Updated: {self.last_updated.strftime('%Y-%m-%d %H:%M:%S')})"
    


class Cookie_Policy(models.Model):
    content      = models.TextField()
    created_at   = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cookie Policy (Last Updated: {self.last_updated.strftime('%Y-%m-%d %H:%M:%S')})"
    

class EMI_Payment_Policy(models.Model):
    content      = models.TextField()
    created_at   = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"EMI & Payment Policy (Last Updated: {self.last_updated.strftime('%Y-%m-%d %H:%M:%S')})"


class Warranty_Policy(models.Model):
    content      = models.TextField()
    created_at   = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Warranty Policy (Last Updated: {self.last_updated.strftime('%Y-%m-%d %H:%M:%S')})"


class Exchange_Policy(models.Model):
    content      = models.TextField()
    created_at   = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Exchange Policy (Last Updated: {self.last_updated.strftime('%Y-%m-%d %H:%M:%S')})"


class Delivery_Policy(models.Model):
    content      = models.TextField()
    created_at   = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Delivery Policy (Last Updated: {self.last_updated.strftime('%Y-%m-%d %H:%M:%S')})"


class PreOrder_Policy(models.Model):
    content      = models.TextField()
    created_at   = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Pre-Order Policy (Last Updated: {self.last_updated.strftime('%Y-%m-%d %H:%M:%S')})"


class Refund_Policy(models.Model):
    content      = models.TextField()
    created_at   = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Refund Policy (Last Updated: {self.last_updated.strftime('%Y-%m-%d %H:%M:%S')})"


class Return_Policy(models.Model):
    content      = models.TextField()
    created_at   = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Return Policy (Last Updated: {self.last_updated.strftime('%Y-%m-%d %H:%M:%S')})"


class Review(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='reviews')
    
    rating = models.PositiveIntegerField(validators=[
                                         MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user',)
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} - {self.rating} stars"



class ContactMessage(models.Model):
    ticket_id = models.CharField(max_length=20, unique=True, editable=False, default='')
    full_name = models.CharField(max_length=255)
    email = models.EmailField()
    subject = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.ticket_id:
            count = ContactMessage.objects.count() + 1
            self.ticket_id = f"DNX-{count:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.ticket_id} - {self.full_name} - {self.subject}"
    
