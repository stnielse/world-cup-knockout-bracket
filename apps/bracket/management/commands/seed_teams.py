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

# WC 2026 R32 roster, alphabetical by display name (matches Team.Meta.ordering).
# Each entry: (FIFA 3-letter code, display name, flag emoji).
# Codes follow FIFA conventions (e.g., USA, ENG, RSA), not ISO-2.
# England uses the UK flag (GB) rather than the subdivision flag for cross-
# platform render reliability.
TEAMS: list[tuple[str, str, str]] = [
    ("ALG", "Algeria", "\U0001f1e9\U0001f1ff"),
    ("ARG", "Argentina", "\U0001f1e6\U0001f1f7"),
    ("AUS", "Australia", "\U0001f1e6\U0001f1fa"),
    ("AUT", "Austria", "\U0001f1e6\U0001f1f9"),
    ("BEL", "Belgium", "\U0001f1e7\U0001f1ea"),
    ("BIH", "Bosnia & Herz.", "\U0001f1e7\U0001f1e6"),
    ("BRA", "Brazil", "\U0001f1e7\U0001f1f7"),
    ("CAN", "Canada", "\U0001f1e8\U0001f1e6"),
    ("CPV", "Cape Verde", "\U0001f1e8\U0001f1fb"),
    ("COL", "Colombia", "\U0001f1e8\U0001f1f4"),
    ("CRO", "Croatia", "\U0001f1ed\U0001f1f7"),
    ("COD", "DR Congo", "\U0001f1e8\U0001f1e9"),
    ("ECU", "Ecuador", "\U0001f1ea\U0001f1e8"),
    ("EGY", "Egypt", "\U0001f1ea\U0001f1ec"),
    ("ENG", "England", "\U0001f1ec\U0001f1e7"),
    ("FRA", "France", "\U0001f1eb\U0001f1f7"),
    ("GER", "Germany", "\U0001f1e9\U0001f1ea"),
    ("GHA", "Ghana", "\U0001f1ec\U0001f1ed"),
    ("CIV", "Ivory Coast", "\U0001f1e8\U0001f1ee"),
    ("JPN", "Japan", "\U0001f1ef\U0001f1f5"),
    ("MEX", "Mexico", "\U0001f1f2\U0001f1fd"),
    ("MAR", "Morocco", "\U0001f1f2\U0001f1e6"),
    ("NED", "Netherlands", "\U0001f1f3\U0001f1f1"),
    ("NOR", "Norway", "\U0001f1f3\U0001f1f4"),
    ("PAR", "Paraguay", "\U0001f1f5\U0001f1fe"),
    ("POR", "Portugal", "\U0001f1f5\U0001f1f9"),
    ("SEN", "Senegal", "\U0001f1f8\U0001f1f3"),
    ("RSA", "South Africa", "\U0001f1ff\U0001f1e6"),
    ("ESP", "Spain", "\U0001f1ea\U0001f1f8"),
    ("SWE", "Sweden", "\U0001f1f8\U0001f1ea"),
    ("SUI", "Switzerland", "\U0001f1e8\U0001f1ed"),
    ("USA", "USA", "\U0001f1fa\U0001f1f8"),
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
