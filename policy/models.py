from django.db import models

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