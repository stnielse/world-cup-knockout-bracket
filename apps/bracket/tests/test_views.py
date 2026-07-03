import logging

import pytest

from apps.bracket.models import Match, Prediction


@pytest.mark.django_db
class TestBracketView:
    def test_member_can_view(self, bracket, client, make_user, make_group):
        owner = make_user()
        group = make_group(owner=owner)
        client.force_login(owner)
        resp = client.get(f"/groups/{group.id}/bracket/")
        assert resp.status_code == 200

    def test_non_member_404(self, bracket, client, make_user, make_group):
        owner = make_user(username="owner")
        outsider = make_user(username="outsider")
        group = make_group(owner=owner)
        client.force_login(outsider)
        resp = client.get(f"/groups/{group.id}/bracket/")
        assert resp.status_code == 404

    def test_group_view_pre_lock_redirects_to_mine(
        self, bracket, client, make_user, make_group
    ):
        owner = make_user()
        group = make_group(owner=owner)
        client.force_login(owner)
        resp = client.get(f"/groups/{group.id}/bracket/?view=group")
        assert resp.status_code == 302
        assert f"/groups/{group.id}/bracket/" in resp["Location"]


@pytest.mark.django_db
class TestLeaderboardView:
    def test_member_can_view(self, bracket, client, make_user, make_group):
        owner = make_user()
        group = make_group(owner=owner)
        client.force_login(owner)
        resp = client.get(f"/groups/{group.id}/leaderboard/")
        assert resp.status_code == 200

    def test_non_member_404(self, bracket, client, make_user, make_group):
        owner = make_user(username="owner")
        outsider = make_user(username="outsider")
        group = make_group(owner=owner)
        client.force_login(outsider)
        resp = client.get(f"/groups/{group.id}/leaderboard/")
        assert resp.status_code == 404

    def test_unauthenticated_redirects_to_login(self, bracket, client, make_group):
        group = make_group()
        resp = client.get(f"/groups/{group.id}/leaderboard/")
        assert resp.status_code == 302
        assert "/accounts/login" in resp["Location"]


@pytest.mark.django_db
class TestMatchPick:
    def _url(self, group_id, match_id):
        return f"/groups/{group_id}/bracket/match/{match_id}/pick/"

    def test_valid_pick_creates_prediction(
        self, bracket, client, make_user, make_group
    ):
        owner = make_user()
        group = make_group(owner=owner)
        client.force_login(owner)
        r32_1 = bracket.match("R32-1")
        resp = client.post(self._url(group.id, r32_1.id), {"team": bracket.usa.id})
        assert resp.status_code == 200
        assert Prediction.objects.filter(
            user=owner, group=group, match=r32_1, picked_winner=bracket.usa
        ).exists()

    def test_pick_rejected_when_locked(self, bracket, client, make_user, make_group):
        owner = make_user()
        group = make_group(owner=owner)
        bracket.lock_now()
        client.force_login(owner)
        r32_1 = bracket.match("R32-1")
        resp = client.post(self._url(group.id, r32_1.id), {"team": bracket.usa.id})
        assert resp.status_code == 400

    def test_pick_rejected_when_locked_logs_warning(
        self, bracket, client, make_user, make_group, caplog
    ):
        owner = make_user()
        group = make_group(owner=owner)
        bracket.lock_now()
        client.force_login(owner)
        r32_1 = bracket.match("R32-1")
        with caplog.at_level(logging.WARNING, logger="apps.bracket.views"):
            client.post(self._url(group.id, r32_1.id), {"team": bracket.usa.id})
        warnings = [
            r for r in caplog.records
            if r.name == "apps.bracket.views" and r.levelno == logging.WARNING
        ]
        assert warnings, "expected a WARNING from apps.bracket.views"
        assert "pick rejected" in warnings[0].getMessage()
        assert "locked=True" in warnings[0].getMessage()

    def test_pick_rejected_when_submitted(self, bracket, client, make_user, make_group):
        owner = make_user()
        group = make_group(owner=owner)
        membership = group.memberships.get(user=owner)
        membership.bracket_submitted = True
        membership.save()
        client.force_login(owner)
        r32_1 = bracket.match("R32-1")
        resp = client.post(self._url(group.id, r32_1.id), {"team": bracket.usa.id})
        assert resp.status_code == 400

    def test_pick_team_not_in_match_rejected(
        self, bracket, client, make_user, make_group
    ):
        owner = make_user()
        group = make_group(owner=owner)
        client.force_login(owner)
        r32_1 = bracket.match("R32-1")  # USA vs MEX
        # Try picking ESP, which isn't in this match
        resp = client.post(self._url(group.id, r32_1.id), {"team": bracket.esp.id})
        assert resp.status_code == 400

    def test_pick_on_match_with_no_teams_rejected(
        self, bracket, client, make_user, make_group
    ):
        owner = make_user()
        group = make_group(owner=owner)
        client.force_login(owner)
        # R16-1 has no derived teams yet because no R32 picks made
        r16_1 = bracket.match("R16-1")
        resp = client.post(self._url(group.id, r16_1.id), {"team": bracket.usa.id})
        assert resp.status_code == 400


@pytest.mark.django_db
class TestSubmitBracket:
    def _make_complete(self, bracket, owner, group):
        """Brute-force a complete bracket by picking home_team everywhere
        a derived matchup exists. Walks R32 → FINAL filling picks."""
        # R32 picks (canonical home_team always set)
        for i in range(1, 17):
            m = Match.objects.filter(slot=f"R32-{i}").first()
            if m and m.home_team:
                Prediction.objects.update_or_create(
                    user=owner,
                    group=group,
                    match=m,
                    defaults={"picked_winner": m.home_team},
                )
        # For non-R32, derived home = source's pick. Since we always picked
        # the canonical home_team in R32, derived chain is well-defined.
        from apps.bracket.services import build_user_bracket

        # Walk rounds bottom-up, picking the derived home team
        for _ in range(6):  # at most 6 round passes
            b = build_user_bracket(owner, group)
            made_any = False
            for round_data in b["rounds"]:
                for entry in round_data["matches"]:
                    if entry["pick"] is None and entry["home"]:
                        Prediction.objects.create(
                            user=owner,
                            group=group,
                            match=entry["match"],
                            picked_winner=entry["home"],
                        )
                        made_any = True
            if not made_any:
                break

    def test_submit_requires_complete_bracket(
        self, bracket, client, make_user, make_group
    ):
        owner = make_user()
        group = make_group(owner=owner)
        client.force_login(owner)
        # No picks at all
        resp = client.post(f"/groups/{group.id}/bracket/submit/")
        assert resp.status_code == 400

    def test_submit_rejected_when_locked(self, bracket, client, make_user, make_group):
        owner = make_user()
        group = make_group(owner=owner)
        bracket.lock_now()
        client.force_login(owner)
        resp = client.post(f"/groups/{group.id}/bracket/submit/")
        assert resp.status_code == 400


@pytest.mark.django_db
class TestUnsubmitBracket:
    def test_unsubmit_rejected_when_not_submitted(
        self, bracket, client, make_user, make_group
    ):
        owner = make_user()
        group = make_group(owner=owner)
        client.force_login(owner)
        resp = client.post(f"/groups/{group.id}/bracket/unsubmit/")
        assert resp.status_code == 400

    def test_unsubmit_clears_flag(self, bracket, client, make_user, make_group):
        owner = make_user()
        group = make_group(owner=owner)
        membership = group.memberships.get(user=owner)
        membership.bracket_submitted = True
        membership.save()
        client.force_login(owner)
        resp = client.post(f"/groups/{group.id}/bracket/unsubmit/")
        assert resp.status_code == 200
        membership.refresh_from_db()
        assert membership.bracket_submitted is False
