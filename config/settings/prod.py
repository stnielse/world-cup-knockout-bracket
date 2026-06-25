"""Production settings. Loaded by wsgi.py/asgi.py by default."""

import os

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401, F403
from .base import MIDDLEWARE, SECRET_KEY, env, env_list

if not SECRET_KEY:
    raise ImproperlyConfigured("SECRET_KEY must be set in the environment for prod.")

DEBUG = False

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS")
_render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if _render_host and _render_host not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_render_host)
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "ALLOWED_HOSTS or RENDER_EXTERNAL_HOSTNAME must be set for prod."
    )

DATABASE_URL = env("DATABASE_URL")
if not DATABASE_URL:
    raise ImproperlyConfigured("DATABASE_URL must be set in the environment for prod.")
DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        ssl_require=True,
    )
}

MIDDLEWARE = list(MIDDLEWARE)
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

RESEND_API_KEY = env("RESEND_API_KEY")
if not RESEND_API_KEY:
    raise ImproperlyConfigured(
        "RESEND_API_KEY must be set in the environment for prod."
    )
EMAIL_BACKEND = "anymail.backends.resend.EmailBackend"
ANYMAIL = {"RESEND_API_KEY": RESEND_API_KEY}
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "onboarding@resend.dev")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
