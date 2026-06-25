from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import UniqueConstraint
from django.utils import timezone


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
    LOCK_WINDOW = timedelta(hours=1)

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

    def is_locked(self) -> bool:
        return (self.kickoff_at - timezone.now()) <= self.LOCK_WINDOW


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
        if self.match_id and self.match.is_locked():
            raise ValidationError(
                "This match is locked. Picks closed 1 hour before kickoff."
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
