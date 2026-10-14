"""
Settings package initialization.
Automatically selects development or production settings based on the DJANGO_ENV environment variable.
Defaults to 'development'.
"""

import os

ENVIRONMENT = os.getenv('DJANGO_ENV', os.getenv('ENVIRONMENT', 'development')).lower().strip()

if ENVIRONMENT in ('production', 'prod'):
    from .production import *
else:
    from .development import *
