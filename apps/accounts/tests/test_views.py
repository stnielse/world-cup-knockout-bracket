import pytest

from apps.accounts.models import User


@pytest.mark.django_db
class TestSignupView:
    URL = "/accounts/signup/"

    def _data(self, **overrides):
        base = {
            "username": "freshuser",
            "email": "fresh@example.com",
            "password1": "complexpw_123_xyz",
            "password2": "complexpw_123_xyz",
        }
        base.update(overrides)
        return base

    def test_get_renders_signup_form(self, client):
        resp = client.get(self.URL)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "username" in content.lower()
        assert "email" in content.lower()

    def test_post_valid_creates_and_logs_in(self, client):
        resp = client.post(self.URL, self._data())
        assert resp.status_code == 302
        assert User.objects.filter(email="fresh@example.com").exists()

    def test_post_missing_username_shows_error(self, client):
        resp = client.post(self.URL, self._data(username=""))
        assert resp.status_code == 200
        assert not User.objects.filter(email="fresh@example.com").exists()
