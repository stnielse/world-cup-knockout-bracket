"""Local development settings."""

from .base import *  # noqa: F401, F403
from .base import SECRET_KEY as _SECRET_KEY

DEBUG = True

SECRET_KEY = _SECRET_KEY or "django-insecure-dev-only-do-not-use-in-prod"

ALLOWED_HOSTS = ["*"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
