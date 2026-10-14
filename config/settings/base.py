"""
Base Django settings for dealnux project.
Contains common configurations shared across development, staging, and production.
"""

import os
import sys
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

try:
    from celery.schedules import crontab
except ImportError:
    def crontab(*args, **kwargs):
        return None

try:
    from decouple import config
except ImportError:
    config = None

# Build paths inside the project
# base.py is at: config/settings/base.py -> parent.parent.parent is the root directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Add apps directory to sys.path so apps can be imported directly
APPS_DIR = BASE_DIR / 'apps'
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))

# Load .env file
load_dotenv(BASE_DIR / '.env')


def get_env_list(var_name, default=""):
    value = os.getenv(var_name, default)
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


# Secret Key
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-dealnux-default-key-change-in-production')

# Application definition
INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Local apps
    'account',
    'custom_ads',
    'policy',
    'notifications',
    'api_integration',
    'store',
    'payment',
    'blog',
    'career',
    'pages',
    'homepage',

    # Third-party apps
    'corsheaders',
    'rest_framework',
    'drf_spectacular',
]

AUTH_USER_MODEL = 'account.User'

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': os.environ.get('GOOGLE_CLIENT_ID') or os.getenv('GOOGLE_OAUTH2_CLIENT_ID', ''),
            'secret': os.environ.get('GOOGLE_CLIENT_SECRET') or os.getenv('GOOGLE_OAUTH2_CLIENT_SECRET', ''),
            'key': ''
        },
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'FETCH_USERINFO': True,
    },
    'apple': {
        'APP': {
            'client_id': os.environ.get('APPLE_CLIENT_ID'),
            'secret': os.environ.get('APPLE_PRIVATE_KEY'),
            'key': os.environ.get('APPLE_KEY_ID'),
            'certificate_key': os.environ.get('APPLE_PRIVATE_KEY')
        },
        'TEAM_ID': os.environ.get('APPLE_TEAM_ID'),
    }
}

REST_FRAMEWORK = {
    'EXCEPTION_HANDLER': 'api_integration.utils.custom_exception_handler',
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.AnonRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'user': '20/second',
        'anon': '10/second',
    },
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': None,
    "DATETIME_FORMAT": "%Y-%m-%d %H:%M:%S",
}

# ==================== Swagger / OpenAPI Documentation Settings ====================
SPECTACULAR_SETTINGS = {
    'TITLE': 'Dealnux API Engine',
    'DESCRIPTION': 'Multi-platform Price Aggregator & Secure Marketplace Architecture API Documentation',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SCHEMA_PATH_PREFIX': r'/api/v[0-9]',
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayOperationId': False,
        'filter': True,
        'docExpansion': 'none',
        'defaultModelsExpandDepth': -1,
        'tagsSorter': 'alpha',
        'operationsSorter': 'alpha',
    },
    'COMPONENT_SPLIT_REQUEST': True,
    'TAGS': [
        {'name': 'account', 'description': 'Authentication, Profiles, KYC & Seller Onboarding'},
        {'name': 'store', 'description': 'Marketplace Products, Categories, Deals & Inventory'},
        {'name': 'payment', 'description': 'Stripe Checkout, Escrow Mechanism & Seller Payouts'},
        {'name': 'ads', 'description': 'CPC Advertising Engine, Campaigns & Budgets'},
        {'name': 'fetch-products', 'description': 'Multi-platform External Sync (Amazon, eBay, Walmart, etc.)'},
        {'name': 'notifications', 'description': 'Real-time & System Notifications'},
        {'name': 'banners', 'description': 'Homepage & Promotional Banners'},
        {'name': 'blog', 'description': 'Blog Articles & News'},
        {'name': 'career', 'description': 'Job Openings & Career Applications'},
        {'name': 'pages', 'description': 'Dynamic Static & Info Pages'},
        {'name': 'policy', 'description': 'Terms of Service, Privacy & Return Policies'},
        {'name': 'Health', 'description': 'System Liveness, DB, Redis & Celery Health Checks'},
    ],
}

# ==================== JWT & Session Settings ====================
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=7),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': False,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'JTI_CLAIM': 'jti',
}

SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_SAMESITE = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 60 * 60 * 24 * 90  # 90 Days
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

CSRF_COOKIE_HTTPONLY = True

# Browser Protections
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'no-referrer-when-downgrade'

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

from config.unfold_conf import UNFOLD_CONFIG
UNFOLD = UNFOLD_CONFIG

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static_local',
]
STATIC_ROOT = os.path.join(BASE_DIR, 'static')
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Celery & Redis
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')

CELERY_BROKER_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 240

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("redis", 6379)],
        },
    },
}

CELERY_BEAT_SCHEDULE = {
    'daily-category-sync': {
        'task': 'api_integration.tasks.safe_category_sync',
        'schedule': crontab(hour=2, minute=0),
    },
    'process-scheduled-notifications': {
        'task': 'notifications.tasks.send_scheduled_notifications',
        'schedule': crontab(minute='*'),
    },
    'daily-subscription-reminders': {
        'task': 'notifications.tasks.send_subscription_reminders',
        'schedule': crontab(hour=9, minute=0),
    },
    'daily-ai-recommendations': {
        'task': 'notifications.tasks.send_daily_ai_recommendations',
        'schedule': crontab(hour=10, minute=0),
    },
    'sync-ebay': {
        'task': 'api_integration.tasks.sync_ebay_task',
        'schedule': crontab(hour=9, minute=0),
    },
    'sync-amazon': {
        'task': 'api_integration.tasks.sync_amazon_task',
        'schedule': crontab(hour=10, minute=0),
    },
    'sync-walmart': {
        'task': 'api_integration.tasks.sync_walmart_task',
        'schedule': crontab(hour=11, minute=0),
    },
    'sync-target': {
        'task': 'api_integration.tasks.sync_target_task',
        'schedule': crontab(hour=12, minute=0),
    },
    'sync-aliexpress': {
        'task': 'api_integration.tasks.sync_aliexpress_task',
        'schedule': crontab(hour=5, minute=0, day_of_week='mon,thu'),
    },
    'sync-bestbuy': {
        'task': 'api_integration.tasks.sync_bestbuy_task',
        'schedule': crontab(hour=13, minute=0),
    },
    'sync-wayfair': {
        'task': 'api_integration.tasks.sync_wayfair_task',
        'schedule': crontab(hour=14, minute=0),
    },
    'sync-sephora': {
        'task': 'api_integration.tasks.sync_sephora_task',
        'schedule': crontab(hour=3, minute=0),
    },
}

# External Services & Integrations
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@dealnux.com')
SITE_URL = os.environ.get('SITE_URL')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@dealnux.shop')

GOOGLE_OAUTH2_CLIENT_ID = os.getenv('GOOGLE_OAUTH2_CLIENT_ID')
GOOGLE_OAUTH2_CLIENT_SECRET = os.getenv('GOOGLE_OAUTH2_CLIENT_SECRET')
GOOGLE_OAUTH2_REDIRECT_URI = os.getenv('GOOGLE_OAUTH2_REDIRECT_URI')

RAPIDAPI_KEY = os.getenv('RAPIDAPI_KEY')

STRIPE_PUBLIC_KEY = os.getenv('STRIPE_PUBLIC_KEY')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
STRIPE_SUCCESS_URL = os.getenv('STRIPE_SUCCESS_URL')
STRIPE_CANCEL_URL = os.getenv('STRIPE_CANCEL_URL')
STRIPE_CONNECT_REFRESH_URL = os.getenv('STRIPE_CONNECT_REFRESH_URL')
STRIPE_CONNECT_RETURN_URL = os.getenv('STRIPE_CONNECT_RETURN_URL')
STRIPE_RETURN_URL = 'https://www.dealnux.shop/payment/success'

AI_ENGINE_URL = "http://dealnux-ai--web-1:8001"

DOCS_USERNAME = os.environ.get('DOCS_USERNAME', 'docsuser')
DOCS_PASSWORD = os.environ.get('DOCS_PASSWORD', 'changeme')

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} [{name}:{lineno}] {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'notifications': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'store': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'payment': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'custom_ads': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
