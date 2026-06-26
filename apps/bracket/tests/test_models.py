from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from apps.bracket.models import (
    Group,
    Prediction,
    is_tournament_locked,
    tournament_lock_time,
)


@pytest.mark.django_db
class TestMatchAutoAdvancement:
    def test_winner_set_pushes_to_feeds_into_home(self, bracket):
        r32_1 = bracket.match("R32-1")
        r32_1.winner = bracket.usa
        r32_1.save()
        r16_1 = bracket.match("R16-1")
        assert r16_1.home_team_id == bracket.usa.id
        assert r16_1.away_team_id is None  # R32-2 still unsettled

    def test_winner_set_pushes_to_feeds_into_away(self, bracket):
        r32_2 = bracket.match("R32-2")
        r32_2.winner = bracket.bra
        r32_2.save()
        r16_1 = bracket.match("R16-1")
        assert r16_1.away_team_id == bracket.bra.id

    def test_clearing_winner_clears_downstream_slot(self, bracket):
        r32_1 = bracket.match("R32-1")
        r32_1.winner = bracket.usa
        r32_1.save()
        assert bracket.match("R16-1").home_team_id == bracket.usa.id

        r32_1.refresh_from_db()
        r32_1.winner = None
        r32_1.save()
        assert bracket.match("R16-1").home_team_id is None

    def test_swapping_winner_updates_downstream_slot(self, bracket):
        r32_1 = bracket.match("R32-1")
        r32_1.winner = bracket.usa
        r32_1.save()
        r32_1.refresh_from_db()
        r32_1.winner = bracket.mex
        r32_1.save()
        assert bracket.match("R16-1").home_team_id == bracket.mex.id

    def test_sf_winner_advances_to_final_and_loser_to_third(self, bracket):
        sf_1 = bracket.match("SF-1")
        sf_1.home_team = bracket.usa
        sf_1.away_team = bracket.mex
        sf_1.save()
        sf_1.winner = bracket.usa
        sf_1.save()
        assert bracket.match("FINAL").home_team_id == bracket.usa.id
        assert bracket.match("THIRD").home_team_id == bracket.mex.id

    def test_sf2_winner_loser_lands_on_third_away(self, bracket):
        sf_2 = bracket.match("SF-2")
        sf_2.home_team = bracket.can
        sf_2.away_team = bracket.bra
        sf_2.save()
        sf_2.winner = bracket.bra
        sf_2.save()
        assert bracket.match("FINAL").away_team_id == bracket.bra.id
        assert bracket.match("THIRD").away_team_id == bracket.can.id

    def test_sf_winner_correction_recascades_third(self, bracket):
        sf_1 = bracket.match("SF-1")
        sf_1.home_team = bracket.usa
        sf_1.away_team = bracket.mex
        sf_1.winner = bracket.usa
        sf_1.save()
        assert bracket.match("THIRD").home_team_id == bracket.mex.id

        sf_1.refresh_from_db()
        sf_1.winner = bracket.mex
        sf_1.save()
        assert bracket.match("THIRD").home_team_id == bracket.usa.id
        assert bracket.match("FINAL").home_team_id == bracket.mex.id

    def test_save_with_no_winner_change_is_noop_for_downstream(self, bracket):
        r32_1 = bracket.match("R32-1")
        r32_1.winner = bracket.usa
        r32_1.save()
        # Re-save with no winner change — should not error or change downstream
        r32_1.refresh_from_db()
        r32_1.save()
        assert bracket.match("R16-1").home_team_id == bracket.usa.id


@pytest.mark.django_db
class TestPredictionLockEnforcement:
    def test_save_allowed_pre_lock(self, bracket, make_user, make_group):
        owner = make_user()
        group = make_group(owner=owner)
        r32_1 = bracket.match("R32-1")
        # Should not raise
        Prediction.objects.create(
            user=owner, group=group, match=r32_1, picked_winner=bracket.usa
        )
        assert Prediction.objects.count() == 1

    def test_save_rejected_post_lock(self, bracket, make_user, make_group):
        owner = make_user()
        group = make_group(owner=owner)
        bracket.lock_now()
        r32_1 = bracket.match("R32-1")
        with pytest.raises(ValidationError):
            Prediction.objects.create(
                user=owner, group=group, match=r32_1, picked_winner=bracket.usa
            )


@pytest.mark.django_db
class TestTournamentLockTime:
    def test_returns_none_with_no_r32_1(self, db):
        # No bracket fixture — no Match rows exist
        assert tournament_lock_time() is None
        assert is_tournament_locked() is False

    def test_returns_kickoff_minus_5_minutes(self, bracket):
        r32_1 = bracket.match("R32-1")
        expected = r32_1.kickoff_at - timedelta(minutes=5)
        assert tournament_lock_time() == expected

    def test_locked_after_window(self, bracket):
        r32_1 = bracket.match("R32-1")
        r32_1.kickoff_at = timezone.now() + timedelta(minutes=4)  # inside 5-min window
        r32_1.save()
        assert is_tournament_locked() is True

    def test_unlocked_before_window(self, bracket):
        r32_1 = bracket.match("R32-1")
        r32_1.kickoff_at = timezone.now() + timedelta(hours=1)
        r32_1.save()
        assert is_tournament_locked() is False


@pytest.mark.django_db
class TestGroupModel:
    def test_save_generates_join_code(self, make_user):
        owner = make_user()
        g = Group.objects.create(name="Test", owner=owner)
        assert g.join_code
        assert len(g.join_code) == 6

    def test_save_preserves_explicit_join_code(self, make_user):
        owner = make_user()
        g = Group.objects.create(name="Test", owner=owner, join_code="MYCODE")
        assert g.join_code == "MYCODE"

    def test_join_codes_are_unique_across_groups(self, make_user):
        owner = make_user()
        g1 = Group.objects.create(name="One", owner=owner)
        g2 = Group.objects.create(name="Two", owner=owner)
        assert g1.join_code != g2.join_code


@pytest.mark.django_db
class TestGroupMembershipUniqueness:
    def test_duplicate_membership_rejected(
        self, make_user, make_group, make_membership
    ):
        owner = make_user()
        group = make_group(owner=owner)
        # owner is already a member from make_group; adding again should fail
        with pytest.raises(IntegrityError):
            make_membership(group=group, user=owner)
