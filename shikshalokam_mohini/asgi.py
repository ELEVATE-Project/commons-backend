"""
ASGI config for shikshalokam_mohini project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shikshalokam_mohini.settings')

django_asgi_app = get_asgi_application()

# Import AFTER Django initialization
import django
django.setup()  # Extra insurance that Django is fully set up
import chatbot.routing

from channels.sessions import CookieMiddleware, SessionMiddleware
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator


application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(
                CookieMiddleware(SessionMiddleware(URLRouter(chatbot.routing.websocket_urlpatterns)))
            )
        ),
    }
)
