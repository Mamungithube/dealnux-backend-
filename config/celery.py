import os
import sys
from pathlib import Path
from celery import Celery

BASE_DIR = Path(__file__).resolve().parent.parent
apps_dir = str(BASE_DIR / 'apps')
if apps_dir not in sys.path:
    sys.path.insert(0, apps_dir)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
app = Celery('config')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()