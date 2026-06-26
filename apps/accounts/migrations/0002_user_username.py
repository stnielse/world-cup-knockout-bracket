"""Add User.username — backfilled from email local-part for existing rows.

Three operations in one migration:
1. AddField nullable + unique so the column exists and we can write per-row.
2. RunPython backfill: every existing user gets a username derived from the
   local-part of their email, sanitized to UnicodeUsernameValidator's allowed
   character set, with a numeric suffix on collision.
3. AlterField NOT NULL + validator — the schema we actually want.

Splitting this way is necessary because unique=True + a single default value
breaks the constraint, and AlterField with NOT NULL on existing data would
fail without the backfill step.
"""

import re

import django.contrib.auth.validators
from django.db import migrations, models

USERNAME_OK = re.compile(r"[\w.@+\-]+")


def _safe_base(email: str) -> str:
    if not email:
        return "user"
    local = email.split("@", 1)[0]
    cleaned = "".join(USERNAME_OK.findall(local))
    return (cleaned or "user")[:100]


def backfill_usernames(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    taken: set[str] = set()
    for u in User.objects.all().order_by("pk"):
        base = _safe_base(u.email)
        candidate = base
        n = 1
        while candidate in taken:
            suffix = str(n)
            candidate = (base[: 100 - len(suffix)]) + suffix
            n += 1
        u.username = candidate
        u.save(update_fields=["username"])
        taken.add(candidate)


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="username",
            field=models.CharField(max_length=100, null=True, unique=True),
        ),
        migrations.RunPython(backfill_usernames, reverse_code=reverse_noop),
        migrations.AlterField(
            model_name="user",
            name="username",
            field=models.CharField(
                help_text="Shown to other members on the leaderboard. Letters, digits and ./@/+/-/_ only.",
                max_length=100,
                unique=True,
                validators=[django.contrib.auth.validators.UnicodeUsernameValidator()],
            ),
        ),
    ]
