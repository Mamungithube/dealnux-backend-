"""
api_integration admin package.
Registers all models for Django & Unfold admin.
"""

from .platform_admin import PlatformAdmin, CategoryAdmin
from .product_admin import (
    ProductAdmin,
    ProductImageInline,
    ProductSpecificationInline,
    ProductListingInline,
    ProductImageAdmin,
    ProductSpecificationAdmin,
)
from .listing_admin import (
    ProductListingAdmin,
    PriceHistoryInline,
    PriceHistoryAdmin,
)
from .favorite_admin import FavoriteAdmin

__all__ = [
    'PlatformAdmin',
    'CategoryAdmin',
    'ProductAdmin',
    'ProductImageInline',
    'ProductSpecificationInline',
    'ProductListingInline',
    'ProductImageAdmin',
    'ProductSpecificationAdmin',
    'ProductListingAdmin',
    'PriceHistoryInline',
    'PriceHistoryAdmin',
    'FavoriteAdmin',
]
