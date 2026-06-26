import pytest

from apps.accounts.forms import EmailUserCreationForm
from apps.accounts.models import User


@pytest.mark.django_db
class TestEmailUserCreationForm:
    def _data(self, **overrides):
        base = {
            "username": "newuser",
            "email": "new@example.com",
            "password1": "complexpw_123_xyz",
            "password2": "complexpw_123_xyz",
        }
        base.update(overrides)
        return base

    def test_valid_form_creates_user(self):
        form = EmailUserCreationForm(data=self._data())
        assert form.is_valid(), form.errors
        u = form.save()
        assert u.username == "newuser"
        assert u.email == "new@example.com"

    def test_missing_username_invalid(self):
        form = EmailUserCreationForm(data=self._data(username=""))
        assert not form.is_valid()
        assert "username" in form.errors

    def test_missing_email_invalid(self):
        form = EmailUserCreationForm(data=self._data(email=""))
        assert not form.is_valid()
        assert "email" in form.errors

    def test_invalid_username_chars_rejected(self):
        form = EmailUserCreationForm(data=self._data(username="bad name!"))
        assert not form.is_valid()
        assert "username" in form.errors

    def test_duplicate_username_rejected(self):
        User.objects.create_user(
            email="first@example.com", password="x", username="taken"
        )
        form = EmailUserCreationForm(data=self._data(username="taken"))
        assert not form.is_valid()
        assert "username" in form.errors
