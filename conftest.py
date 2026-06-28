"""Shared pytest fixtures.

Two layers:
- `bracket` fixture: seeds the canonical 32-team roster (via seed_teams) and
  the 32-match knockout structure (via seed_bracket), then overrides
  R32-1/R32-2 with USA-vs-MEX and CAN-vs-BRA so existing tests stay stable
  against seed_bracket's canonical GER-vs-PAR / FRA-vs-SWE force-set.
  R32-1.kickoff_at is set 1 day in the future so `is_tournament_locked()`
  returns False by default; tests can override via `lock_now()`.
- helper factories `make_user`, `make_group`, `make_membership` for cheap
  per-test object creation without re-stamping the bracket structure.
"""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import User
from apps.bracket.models import Group, GroupMembership, Match, Team

FIXTURE_TEAM_CODES = ["USA", "MEX", "CAN", "BRA", "ESP", "POR", "JPN"]


@pytest.fixture
def bracket(db):
    """Seed bracket + teams + R32-1 kickoff. Returns helper namespace."""
    call_command("seed_teams")
    call_command("seed_bracket")
    call_command("seed_scoring_rules")
    teams = {code: Team.objects.get(code=code) for code in FIXTURE_TEAM_CODES}
    r32_1 = Match.objects.get(slot="R32-1")
    r32_1.home_team = teams["USA"]
    r32_1.away_team = teams["MEX"]
    r32_1.kickoff_at = timezone.now() + timedelta(days=1)
    r32_1.save()
    r32_2 = Match.objects.get(slot="R32-2")
    r32_2.home_team = teams["CAN"]
    r32_2.away_team = teams["BRA"]
    r32_2.kickoff_at = timezone.now() + timedelta(days=1, hours=3)
    r32_2.save()
    return _BracketEnv(teams=teams)


class _BracketEnv:
    def __init__(self, teams):
        self.teams = teams
        self.usa = teams["USA"]
        self.mex = teams["MEX"]
        self.can = teams["CAN"]
        self.bra = teams["BRA"]
        self.esp = teams["ESP"]
        self.por = teams["POR"]
        self.jpn = teams["JPN"]

    def match(self, slot):
        return Match.objects.get(slot=slot)

    def lock_now(self):
        """Move R32-1 kickoff to the past so is_tournament_locked() is True."""
        r32_1 = self.match("R32-1")
        r32_1.kickoff_at = timezone.now() - timedelta(hours=1)
        r32_1.save()


@pytest.fixture
def make_user(db):
    counter = {"n": 0}

    def _make(email=None, username=None, password="testpass_xyz_123"):
        counter["n"] += 1
        email = email or f"user{counter['n']}@test.com"
        username = username or f"user{counter['n']}"
        return User.objects.create_user(
            email=email, password=password, username=username
        )

    return _make


@pytest.fixture
def make_group(db, make_user):
    def _make(owner=None, name="Test Group"):
        owner = owner or make_user()
        group = Group.objects.create(name=name, owner=owner)
        GroupMembership.objects.create(group=group, user=owner)
        return group

    return _make


@pytest.fixture
def make_membership(db):
    def _make(group, user):
        return GroupMembership.objects.create(group=group, user=user)

    return _make
