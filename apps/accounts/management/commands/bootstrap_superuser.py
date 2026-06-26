import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create a superuser from env vars if one doesn't exist (idempotent)."

    def handle(self, *args, **kwargs):
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        if not email or not password:
            self.stdout.write("DJANGO_SUPERUSER_EMAIL/PASSWORD not set; skipping.")
            return
        User = get_user_model()
        if User.objects.filter(email=email).exists():
            self.stdout.write(f"Superuser {email} already exists; skipping.")
            return
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME") or email.split("@")[0][:100]
        User.objects.create_superuser(
            email=email, password=password, username=username
        )
        self.stdout.write(f"Created superuser {email} (username={username}).")
