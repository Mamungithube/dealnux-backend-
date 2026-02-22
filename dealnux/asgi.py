import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from chat_system.middleware import JWTAuthMiddlewareStack
import chat_system.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dealnux.settings')

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