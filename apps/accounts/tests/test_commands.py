from io import StringIO

import pytest
from django.core.management import call_command

from apps.accounts.models import User


@pytest.mark.django_db
class TestBootstrapSuperuser:
    def _call(self):
        out = StringIO()
        call_command("bootstrap_superuser", stdout=out)
        return out.getvalue()

    def test_skips_when_env_vars_missing(self, monkeypatch):
        monkeypatch.delenv("DJANGO_SUPERUSER_EMAIL", raising=False)
        monkeypatch.delenv("DJANGO_SUPERUSER_PASSWORD", raising=False)
        out = self._call()
        assert "skipping" in out.lower()
        assert User.objects.count() == 0

    def test_creates_with_env_username(self, monkeypatch):
        monkeypatch.setenv("DJANGO_SUPERUSER_EMAIL", "root@test.com")
        monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "secret")
        monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "rootname")
        self._call()
        u = User.objects.get(email="root@test.com")
        assert u.username == "rootname"
        assert u.is_superuser

    def test_falls_back_to_email_prefix_when_username_unset(self, monkeypatch):
        monkeypatch.setenv("DJANGO_SUPERUSER_EMAIL", "admin@test.com")
        monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "secret")
        monkeypatch.delenv("DJANGO_SUPERUSER_USERNAME", raising=False)
        self._call()
        u = User.objects.get(email="admin@test.com")
        assert u.username == "admin"

    def test_idempotent(self, monkeypatch):
        monkeypatch.setenv("DJANGO_SUPERUSER_EMAIL", "root@test.com")
        monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "secret")
        monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "rootname")
        self._call()
        out = self._call()
        assert "already exists" in out.lower()
        assert User.objects.filter(email="root@test.com").count() == 1
