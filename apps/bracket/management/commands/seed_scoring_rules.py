"""
Seed / upsert per-round point values for scoring.

Defaults reward later-round correctness more heavily (rounds get harder to
predict as the bracket narrows). Values are editable in Django admin —
re-running this command does NOT overwrite a value an admin has changed; it
only creates rows that don't exist yet.

Run:
    .venv/bin/python manage.py seed_scoring_rules
"""

from django.core.management.base import BaseCommand

from apps.bracket.models import Round, ScoringRule

DEFAULT_POINTS: dict[str, int] = {
    Round.R32: 1,
    Round.R16: 2,
    Round.QF: 4,
    Round.SF: 8,
    Round.THIRD: 10,
    Round.FINAL: 15,
}


class Command(BaseCommand):
    help = "Create any missing ScoringRule rows with default point values."

    def handle(self, *args, **options):
        created = 0
        for round_code, points in DEFAULT_POINTS.items():
            _, was_created = ScoringRule.objects.get_or_create(
                round=round_code,
                defaults={"points": points},
            )
            if was_created:
                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Scoring rules: {created} created, "
                f"{ScoringRule.objects.count()} total."
            )
        )
