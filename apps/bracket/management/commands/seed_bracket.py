"""
Seed / upsert the 32-match knockout bracket structure.

What this command sets:
- All 32 Match rows (R32-1..R32-16, R16-1..R16-8, QF-1..QF-4, SF-1, SF-2,
  THIRD, FINAL).
- feeds_into / feeds_as on every match that advances a winner: each pair of
  sibling matches feeds into a single parent match (odd index → home, even →
  away).
- THIRD-place is intentionally left unwired. Its participants are the *losers*
  of SF-1 and SF-2, which the current model does not express. After the SFs
  are played, set THIRD's home_team / away_team manually in admin.

What this command does NOT set (leave for admin / tournament data entry):
- home_team, away_team — known after the R32 draw (~June 27).
- kickoff_at for R32-2..FINAL — known from the FIFA schedule. New rows get a
  far-future placeholder so the lock check won't fire; re-running this seed
  will not overwrite a real kickoff already entered.
- winner — set as matches are played.

Exception: R32-1 kickoff IS code-managed. Because R32-1.kickoff_at drives the
global tournament lock (kickoff - 5 min), it must be reproducible across local
/ staging / prod and immune to a stray admin edit. The seed force-sets it to
R32_1_KICKOFF on every run.

Idempotent: re-running this command does not duplicate matches and does not
clobber tournament data. It will re-wire feeds_into / feeds_as if the topology
in this file changes.

Run:
    .venv/bin/python manage.py seed_bracket
"""

import itertools
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand

from apps.bracket.models import FeedAs, Match, Round

# Far-future placeholder so the tournament global lock never fires until a
# real kickoff is entered. Year 2099 is deliberately absurd — easy to
# spot in admin if you forgot to fill one in.
PLACEHOLDER_KICKOFF = datetime(2099, 12, 31, tzinfo=UTC)

# R32-1 is the WC26 opener: Sunday 2026-06-28 13:00 America/Denver (Mountain).
# This drives tournament_lock_time() = kickoff - 5 min.
R32_1_KICKOFF = datetime(2026, 6, 28, 13, 0, tzinfo=ZoneInfo("America/Denver"))


# All 32 slots in tournament order. Slot names are the canonical identifiers
# (Match.slot is unique).
SLOTS: list[tuple[str, str]] = [
    *[(f"R32-{i}", Round.R32) for i in range(1, 17)],
    *[(f"R16-{i}", Round.R16) for i in range(1, 9)],
    *[(f"QF-{i}", Round.QF) for i in range(1, 5)],
    ("SF-1", Round.SF),
    ("SF-2", Round.SF),
    ("THIRD", Round.THIRD),
    ("FINAL", Round.FINAL),
]


def _pair_feeds(
    from_prefix: str, count: int, into_prefix: str
) -> list[tuple[str, str, str]]:
    """Match N feeds into match ceil(N/2) of the next round; odd→home, even→away."""
    out: list[tuple[str, str, str]] = []
    for i in range(1, count + 1):
        parent_idx = (i + 1) // 2
        side = FeedAs.HOME if i % 2 == 1 else FeedAs.AWAY
        out.append((f"{from_prefix}-{i}", f"{into_prefix}-{parent_idx}", side))
    return out


# (from_slot, into_slot, feeds_as). THIRD intentionally absent.
WIRING: list[tuple[str, str, str]] = list(
    itertools.chain(
        _pair_feeds("R32", 16, "R16"),
        _pair_feeds("R16", 8, "QF"),
        _pair_feeds("QF", 4, "SF"),
        [
            ("SF-1", "FINAL", FeedAs.HOME),
            ("SF-2", "FINAL", FeedAs.AWAY),
        ],
    )
)


class Command(BaseCommand):
    help = "Upsert the 32-match knockout bracket and wire the advancement tree."

    def handle(self, *args, **options):
        created = 0
        round_synced = 0
        matches: dict[str, Match] = {}

        for slot, round_code in SLOTS:
            match, was_created = Match.objects.get_or_create(
                slot=slot,
                defaults={
                    "round": round_code,
                    "kickoff_at": PLACEHOLDER_KICKOFF,
                },
            )
            if was_created:
                created += 1
            elif match.round != round_code:
                match.round = round_code
                match.save(update_fields=["round"])
                round_synced += 1
            matches[slot] = match

        rewired = 0
        for from_slot, into_slot, feeds_as in WIRING:
            m = matches[from_slot]
            target = matches[into_slot]
            if m.feeds_into_id != target.id or m.feeds_as != feeds_as:
                m.feeds_into = target
                m.feeds_as = feeds_as
                m.save(update_fields=["feeds_into", "feeds_as"])
                rewired += 1

        r32_1 = matches["R32-1"]
        kickoff_synced = 0
        if r32_1.kickoff_at != R32_1_KICKOFF:
            r32_1.kickoff_at = R32_1_KICKOFF
            r32_1.save(update_fields=["kickoff_at"])
            kickoff_synced = 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Bracket seed: {created} created, {round_synced} round-synced, "
                f"{rewired} (re)wired, {kickoff_synced} kickoff-synced, "
                f"{Match.objects.count()} total matches."
            )
        )
