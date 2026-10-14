from django.db import models
from django.core.exceptions import ValidationError
from PIL import Image


def validate_main_banner(image):
    img = Image.open(image)
    w, h = img.size
    if w != 920 or h != 460:
        raise ValidationError(
            f"Main Banner image must be exactly 920x460 px. Your image: {w}x{h} px"
        )


def validate_side_banner(image):
    img = Image.open(image)
    w, h = img.size
    if w != 299 or h != 220:
        raise ValidationError(
            f"Side Banner image must be exactly 299x220 px. Your image: {w}x{h} px"
        )


class MainSliderBanner(models.Model):
    """
    MAIN SLIDER BANNER — max 5 active at a time

    Required image size : 920 x 460 px
    Aspect ratio        : 2:1
    Format              : JPG / PNG / WEBP

    Lower order number appears first (1 → 2 → 3 → 4 → 5).
    Uploading wrong size will raise a validation error.
    """
    title = models.CharField(
        max_length=200,
        verbose_name="Title",
        help_text="Internal label — not shown on the homepage."
    )
    image = models.ImageField(
        upload_to='banners/main/',
        verbose_name="Image  [ 920 x 460 px ]",
        validators=[validate_main_banner],
        help_text="Required: 920 x 460 px | Ratio: 2:1 | JPG / PNG / WEBP"
    )
    link_url = models.URLField(
        blank=True, null=True,
        verbose_name="Link URL",
        help_text="Clicking the banner will open this URL. Leave blank for no link."
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Order",
        help_text="Lower number appears first  (1, 2, 3, 4, 5)"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Active"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        verbose_name = "Main Slider Banner"
        verbose_name_plural = "Main Slider Banners  [ 920x460 px | max 5 ]"
        ordering = ['order', 'created_at']

    def __str__(self):
        status = 'Active' if self.is_active else 'Inactive'
        return f"[{self.order}] {self.title} — {status}"

    def clean(self):
        if self.is_active:
            # Max 5 active check
            qs = MainSliderBanner.objects.filter(is_active=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.count() >= 5:
                raise ValidationError(
                    "Maximum 5 Main Slider Banners can be active at the same time. "
                    "Deactivate one before activating a new banner."
                )

        # Duplicate order check
        qs_order = MainSliderBanner.objects.filter(order=self.order)
        if self.pk:
            qs_order = qs_order.exclude(pk=self.pk)
        if qs_order.exists():
            raise ValidationError(
                f"Order '{self.order}' is already taken by another banner. "
                f"Please use a different order number."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class SideBanner(models.Model):
    """
    SIDE BANNER — 4 fixed positions (one active per position)

    Required image size : 299 x 220 px
    Aspect ratio        : 1.36:1
    Format              : JPG / PNG / WEBP

    Positions:
      1 → Top Left
      2 → Top Right
      3 → Bottom Left
      4 → Bottom Right

    Only one active banner is allowed per position.
    Uploading wrong size will raise a validation error.
    """
    POSITION_CHOICES = [
        (1, "Position 1  →  Top Left"),
        (2, "Position 2  →  Top Right"),
        (3, "Position 3  →  Bottom Left"),
        (4, "Position 4  →  Bottom Right"),
    ]

    title = models.CharField(
        max_length=200,
        verbose_name="Title",
        help_text="Internal label — not shown on the homepage."
    )
    image = models.ImageField(
        upload_to='banners/side/',
        verbose_name="Image  [ 299 x 220 px ]",
        validators=[validate_side_banner],
        help_text="Required: 299 x 220 px | Ratio: 1.36:1 | JPG / PNG / WEBP"
    )
    position = models.PositiveSmallIntegerField(
        choices=POSITION_CHOICES,
        verbose_name="Position",
        help_text="Which slot should this banner appear in?"
    )
    link_url = models.URLField(
        blank=True, null=True,
        verbose_name="Link URL",
        help_text="Clicking the banner will open this URL. Leave blank for no link."
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Active"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        verbose_name = "Side Banner"
        verbose_name_plural = "Side Banners  [ 299x220 px | 4 Positions ]"
        ordering = ['position']

    def __str__(self):
        pos = dict(self.POSITION_CHOICES).get(self.position, f"Position {self.position}")
        status = 'Active' if self.is_active else 'Inactive'
        return f"{self.title}  |  {pos}  |  {status}"

    def clean(self):
        if self.is_active and self.position:
            qs = SideBanner.objects.filter(position=self.position, is_active=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                pos = dict(self.POSITION_CHOICES).get(self.position)
                raise ValidationError(
                    f"'{pos}' already has an active banner. "
                    f"Deactivate the existing one before activating a new banner in this position."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)