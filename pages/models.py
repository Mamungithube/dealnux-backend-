from django.db import models


class PressCoverage(models.Model):
    source_name = models.CharField(max_length=255)
    source_logo = models.ImageField(upload_to='press/logos/', blank=True, null=True)
    published_date = models.DateField()
    excerpt = models.TextField()
    article_url = models.URLField()
    is_featured = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-published_date']

    def __str__(self):
        return f"{self.source_name} - {self.published_date}"