import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dealnux.settings')
app = Celery('dealnux')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


app.conf.beat_schedule = {
    'sync-fixed-categories-every-hour': {
        'task': 'api_integration.tasks.hourly_fixed_category_sync',
        'schedule': crontab(minute=0), # প্রতি ঘণ্টার শুরুতে রান হবে (১টা, ২টা...)
    },
}