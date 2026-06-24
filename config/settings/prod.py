"""Production settings. Loaded by wsgi.py/asgi.py by default."""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401, F403
from .base import SECRET_KEY, env_list

if not SECRET_KEY:
    raise ImproperlyConfigured("SECRET_KEY must be set in the environment for prod.")

DEBUG = False

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must be set in the environment for prod.")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
