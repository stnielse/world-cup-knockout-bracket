import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import UniqueConstraint
from django.utils import timezone

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
