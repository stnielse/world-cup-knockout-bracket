import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import UniqueConstraint
from django.utils import timezone

logger = logging.getLogger(__name__)

JOIN_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
JOIN_CODE_LEN = 6
JOIN_CODE_MAX_TRIES = 10

TOURNAMENT_LOCK_WINDOW = timedelta(minutes=5)
TOURNAMENT_LOCK_REFERENCE_SLOT = "R32-1"


def generate_join_code() -> str:
    return "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_LEN))


class Round(models.TextChoices):
    R32 = "R32", "Round of 32"
    R16 = "R16", "Round of 16"
    QF = "QF", "Quarterfinal"
    SF = "SF", "Semifinal"
    THIRD = "THIRD", "Third place"
    FINAL = "FINAL", "Final"


class FeedAs(models.TextChoices):
    HOME = "home", "home"
    AWAY = "away", "away"


class Team(models.Model):
    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=64, unique=True)
    flag_emoji = models.CharField(max_length=8, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.flag_emoji} {self.name}".strip()


class Match(models.Model):
    round = models.CharField(max_length=8, choices=Round.choices)
    slot = models.CharField(max_length=16, unique=True)
    home_team = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="home_matches",
    )
    away_team = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="away_matches",
    )
    kickoff_at = models.DateTimeField()
    winner = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="won_matches",
    )
    feeds_into = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fed_by",
    )
    feeds_as = models.CharField(
        max_length=4,
        choices=FeedAs.choices,
        blank=True,
    )

    class Meta:
        ordering = ["kickoff_at", "slot"]

    def __str__(self):
        h = self.home_team.code if self.home_team else "?"
        a = self.away_team.code if self.away_team else "?"
        return f"{self.slot}: {h} v {a}"

    def save(self, *args, **kwargs):
        old_winner_id = None
        if self.pk is not None:
            old_winner_id = (
                Match.objects.filter(pk=self.pk)
                .values_list("winner_id", flat=True)
                .first()
            )
        super().save(*args, **kwargs)
        if old_winner_id != self.winner_id:
            if self.winner_id is None:
                logger.info("winner cleared: match=%s", self.slot)
            else:
                winner_code = self.winner.code if self.winner else "?"
                logger.info("winner set: match=%s team=%s", self.slot, winner_code)
            _advance_winner(self)


def _advance_winner(match):
    """Push match.winner into downstream Match.home_team / away_team slots.

    Two paths:
    - feeds_into: winner advances to the next round's match in this match's
      `feeds_as` slot. Clearing the winner clears the downstream slot.
    - SF → THIRD: when a semifinal's winner is set/changed, the *loser* of
      that SF goes to THIRD's home_team (SF-1) or away_team (SF-2). Clearing
      the SF winner clears THIRD's slot.

    Only mutates Match rows (the canonical bracket). Never touches Prediction
    rows — each user's bracket display derives from their own picks and is
    intentionally insulated from canonical advancement.
    """
    new_winner = match.winner

    if match.feeds_into_id and match.feeds_as in (FeedAs.HOME, FeedAs.AWAY):
        downstream = Match.objects.get(pk=match.feeds_into_id)
        field = f"{match.feeds_as}_team"
        current = getattr(downstream, f"{field}_id")
        target = new_winner.pk if new_winner else None
        if current != target:
            setattr(downstream, field, new_winner)
            downstream.save(update_fields=[field])
            if new_winner is None:
                logger.info(
                    "advance unwired: slot=%s field=%s (from match=%s)",
                    downstream.slot,
                    field,
                    match.slot,
                )
            else:
                logger.info(
                    "advance wired: match=%s team=%s -> slot=%s field=%s",
                    match.slot,
                    new_winner.code,
                    downstream.slot,
                    field,
                )

    if match.round == Round.SF:
        third_field = (
            "home_team"
            if match.slot == "SF-1"
            else "away_team" if match.slot == "SF-2" else None
        )
        if third_field is not None:
            third = Match.objects.filter(slot="THIRD").first()
            if third is not None:
                loser = _determine_sf_loser(match)
                current = getattr(third, f"{third_field}_id")
                target = loser.pk if loser else None
                if current != target:
                    setattr(third, third_field, loser)
                    third.save(update_fields=[third_field])
                    if loser is None:
                        logger.info(
                            "third-place unwired: field=%s (from match=%s)",
                            third_field,
                            match.slot,
                        )
                    else:
                        logger.info(
                            "third-place wired: match=%s loser=%s -> field=%s",
                            match.slot,
                            loser.code,
                            third_field,
                        )


def _determine_sf_loser(sf_match):
    """The team in `sf_match` that didn't win. None if winner is unset,
    either side is unset, or the winner isn't one of the two sides."""
    if sf_match.winner_id is None:
        return None
    if sf_match.home_team_id is None or sf_match.away_team_id is None:
        return None
    if sf_match.winner_id == sf_match.home_team_id:
        return sf_match.away_team
    if sf_match.winner_id == sf_match.away_team_id:
        return sf_match.home_team
    return None


def tournament_lock_time():
    first = Match.objects.filter(slot=TOURNAMENT_LOCK_REFERENCE_SLOT).first()
    if first is None:
        return None
    return first.kickoff_at - TOURNAMENT_LOCK_WINDOW


def is_tournament_locked() -> bool:
    lock = tournament_lock_time()
    return lock is not None and timezone.now() >= lock


class Group(models.Model):
    name = models.CharField(max_length=64)
    join_code = models.CharField(max_length=8, unique=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_groups",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.join_code:
            for _ in range(JOIN_CODE_MAX_TRIES):
                candidate = generate_join_code()
                if not Group.objects.filter(join_code=candidate).exists():
                    self.join_code = candidate
                    break
            else:
                raise RuntimeError("Could not generate a unique join code")
        super().save(*args, **kwargs)


class GroupMembership(models.Model):
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    bracket_submitted = models.BooleanField(default=False)
    bracket_submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["group", "user"], name="unique_group_member"),
        ]
        ordering = ["joined_at"]

    def __str__(self):
        return f"{self.user} in {self.group}"


class Prediction(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="predictions",
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="predictions",
    )
    match = models.ForeignKey(
        Match,
        on_delete=models.CASCADE,
        related_name="predictions",
    )
    picked_winner = models.ForeignKey(
        Team,
        on_delete=models.PROTECT,
        related_name="predicted_in",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["user", "group", "match"],
                name="unique_user_group_match_prediction",
            ),
        ]
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.user} → {self.picked_winner} ({self.match.slot})"

    def clean(self):
        if is_tournament_locked():
            raise ValidationError(
                "The tournament bracket is locked. Picks closed 5 minutes "
                "before the first match."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ScoringRule(models.Model):
    round = models.CharField(max_length=8, choices=Round.choices, unique=True)
    points = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["round"]

    def __str__(self):
        return f"{self.get_round_display()}: {self.points} pts"
