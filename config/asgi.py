import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
apps_dir = str(BASE_DIR / 'apps')
if apps_dir not in sys.path:
    sys.path.insert(0, apps_dir)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from chat_system.middleware import JWTAuthMiddlewareStack
import chat_system.routing


# Initialize Django ASGI application early to ensure AppRegistry is populated
django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddlewareStack(
        URLRouter(
            chat_system.routing.websocket_urlpatterns
        )
    ),
})