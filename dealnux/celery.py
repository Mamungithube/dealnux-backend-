import os
from celery import Celery

# Django সেটিংস সেট করা
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dealnux.settings')

app = Celery('dealnux')

# namespace='CELERY' মানে settings.py-তে যা CELERY_ দিয়ে শুরু হবে তা সে পড়বে
app.config_from_object('django.conf:settings', namespace='CELERY')

# সব অ্যাপের tasks.py অটো লোড করবে
app.autodiscover_tasks()