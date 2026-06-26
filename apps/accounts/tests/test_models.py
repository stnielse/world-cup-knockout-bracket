import pytest
from django.db import IntegrityError

from apps.accounts.models import User


@pytest.mark.django_db
class TestUserModel:
    def test_str_returns_username(self):
        u = User.objects.create_user(
            email="alice@example.com", password="x", username="alice"
        )
        assert str(u) == "alice"

    def test_username_uniqueness_enforced(self):
        User.objects.create_user(email="one@example.com", password="x", username="dup")
        with pytest.raises(IntegrityError):
            User.objects.create_user(
                email="two@example.com", password="x", username="dup"
            )

    def test_email_uniqueness_enforced(self):
        User.objects.create_user(email="dup@example.com", password="x", username="one")
        with pytest.raises(IntegrityError):
            User.objects.create_user(
                email="dup@example.com", password="x", username="two"
            )

    def test_create_superuser_sets_flags(self):
        u = User.objects.create_superuser(
            email="root@example.com", password="x", username="root"
        )
        assert u.is_staff
        assert u.is_superuser

    def test_create_user_requires_email(self):
        with pytest.raises(ValueError):
            User.objects.create_user(email="", password="x", username="nope")
