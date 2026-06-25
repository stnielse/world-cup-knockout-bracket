"""
Seed / upsert the WC 2026 team list.

Idempotent: re-running fixes a typo in a name or flag without duplicating rows.
Edit the TEAMS list below to add / remove / correct entries, then re-run:

    make shell-cmd CMD="seed_teams"
    # or directly:
    .venv/bin/python manage.py seed_teams
"""

from django.core.management.base import BaseCommand

from apps.bracket.models import Team

# PLACEHOLDER — populate with the final qualified-team roster.
# Each entry: (FIFA 3-letter code, display name, flag emoji).
# Codes follow FIFA conventions (e.g., USA, ENG, KSA), not ISO-2.
TEAMS: list[tuple[str, str, str]] = [
    ("USA", "United States", "\U0001f1fa\U0001f1f8"),
    ("CAN", "Canada", "\U0001f1e8\U0001f1e6"),
    ("MEX", "Mexico", "\U0001f1f2\U0001f1fd"),
]


class Command(BaseCommand):
    help = "Upsert the WC 2026 team list from the in-file TEAMS constant."

    def handle(self, *args, **options):
        created = updated = 0
        for code, name, flag in TEAMS:
            _, was_created = Team.objects.update_or_create(
                code=code,
                defaults={"name": name, "flag_emoji": flag},
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed complete: {created} created, {updated} updated, "
                f"{Team.objects.count()} total."
            )
        )
