from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.core.management import call_command

from apps.bracket.models import FeedAs, Match, ScoringRule, Team


@pytest.mark.django_db
class TestSeedBracket:
    def test_creates_32_matches_first_run(self, db):
        call_command("seed_bracket")
        assert Match.objects.count() == 32

    def test_idempotent_on_second_run(self, db):
        call_command("seed_bracket")
        call_command("seed_bracket")
        assert Match.objects.count() == 32

    def test_wires_feeds_into_correctly(self, db):
        call_command("seed_bracket")
        # R32-1 and R32-2 both feed into R16-1
        r32_1 = Match.objects.get(slot="R32-1")
        r32_2 = Match.objects.get(slot="R32-2")
        r16_1 = Match.objects.get(slot="R16-1")
        assert r32_1.feeds_into_id == r16_1.id
        assert r32_1.feeds_as == FeedAs.HOME
        assert r32_2.feeds_into_id == r16_1.id
        assert r32_2.feeds_as == FeedAs.AWAY

    def test_sf_feeds_into_final(self, db):
        call_command("seed_bracket")
        sf_1 = Match.objects.get(slot="SF-1")
        sf_2 = Match.objects.get(slot="SF-2")
        final = Match.objects.get(slot="FINAL")
        assert sf_1.feeds_into_id == final.id
        assert sf_1.feeds_as == FeedAs.HOME
        assert sf_2.feeds_into_id == final.id
        assert sf_2.feeds_as == FeedAs.AWAY

    def test_third_left_unwired(self, db):
        call_command("seed_bracket")
        third = Match.objects.get(slot="THIRD")
        assert third.feeds_into_id is None

    def test_r32_1_kickoff_force_set_to_canonical(self, db):
        call_command("seed_bracket")
        r32_1 = Match.objects.get(slot="R32-1")
        expected = datetime(2026, 6, 28, 13, 0, tzinfo=ZoneInfo("America/Denver"))
        assert r32_1.kickoff_at == expected

    def test_r32_1_kickoff_resyncs_after_admin_edit(self, db):
        call_command("seed_bracket")
        r32_1 = Match.objects.get(slot="R32-1")
        r32_1.kickoff_at = datetime(2030, 1, 1, tzinfo=ZoneInfo("UTC"))
        r32_1.save(update_fields=["kickoff_at"])
        call_command("seed_bracket")
        r32_1.refresh_from_db()
        expected = datetime(2026, 6, 28, 13, 0, tzinfo=ZoneInfo("America/Denver"))
        assert r32_1.kickoff_at == expected

    def test_other_r32_kickoffs_remain_placeholder(self, db):
        call_command("seed_bracket")
        r32_2 = Match.objects.get(slot="R32-2")
        assert r32_2.kickoff_at.year == 2099


@pytest.mark.django_db
class TestSeedScoringRules:
    def test_creates_six_rows_first_run(self, db):
        call_command("seed_scoring_rules")
        assert ScoringRule.objects.count() == 6

    def test_default_point_values(self, db):
        call_command("seed_scoring_rules")
        points = dict(ScoringRule.objects.values_list("round", "points"))
        assert points == {
            "R32": 1,
            "R16": 2,
            "QF": 4,
            "SF": 8,
            "THIRD": 10,
            "FINAL": 15,
        }

    def test_idempotent_on_second_run(self, db):
        call_command("seed_scoring_rules")
        call_command("seed_scoring_rules")
        assert ScoringRule.objects.count() == 6

    def test_admin_edits_preserved_across_reseed(self, db):
        call_command("seed_scoring_rules")
        ScoringRule.objects.filter(round="R32").update(points=99)
        call_command("seed_scoring_rules")
        assert ScoringRule.objects.get(round="R32").points == 99


@pytest.mark.django_db
class TestSeedTeams:
    def test_creates_placeholder_teams(self, db):
        call_command("seed_teams")
        # Current TEAMS list contains 3 placeholder host nations
        codes = set(Team.objects.values_list("code", flat=True))
        assert {"USA", "CAN", "MEX"}.issubset(codes)

    def test_idempotent_on_second_run(self, db):
        call_command("seed_teams")
        first_count = Team.objects.count()
        call_command("seed_teams")
        assert Team.objects.count() == first_count
