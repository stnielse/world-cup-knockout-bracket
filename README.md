# A Free 2026 World Cup Knockout Bracket Game

> [!IMPORTANT]
> This service has zero association with FIFA.

A small Django app for running private-group bracket pools over the 32-team knockout stage of the 2026 FIFA World Cup. Users sign up, create or join a group by 6-character code, and lock in a winner for every match from the Round of 32 through the Final (plus the Third-Place playoff). Points accrue per round as real-world winners are entered by an admin.

Live for the tournament window: **2026-06-28 → 2026-07-19**.

## Design

**One tournament, many private groups.** There's a single canonical `Match` graph shared across the whole site — the 32 knockout fixtures, wired by `feeds_into` / `feeds_as` so setting a winner cascades that team into the correct slot of the next round. Each user's picks live per-`(user, group, match)` in `Prediction`, so the same person can be in multiple pools with independent brackets.

**Two views of the bracket, deliberately different:**
- *My bracket* — each match's teams are derived from the user's own upstream picks, not from canonical advancement. Your bracket stays frozen on your predicted future even after real results start filling in the true bracket. R32 is the exception; those matchups come from the FIFA draw and are admin-seeded.
- *Group bracket* — canonical teams and winners, plus every group member's pick per match. Hidden until the tournament lock so members can't copy each other.

**Lock behavior.** Picks close 5 minutes before R32-1 kickoff (2026-06-28 13:00 America/Denver, so lock is 12:55 MT). Once locked, no `Prediction` can be created or edited; the group view unhides. Users can also self-submit their bracket earlier to freeze it before the global lock.

**Pick reconciliation.** When someone changes an earlier-round pick, downstream picks that are no longer valid (e.g. you picked France to win the SF but just changed your QF pick so France isn't in the SF anymore) are deleted in dependency order by `reconcile_user_picks`. R32 picks are never auto-cleared.

**Scoring** is computed on the fly from `Prediction` × `Match.winner` × `ScoringRule` (points-per-round). No materialized standings table — the 32-match × small-pool math is cheap and lets an admin winner edit show up on the next leaderboard render immediately.

**Time zones.** DB stores UTC (`USE_TZ=True`). Server-rendered pages default to Mountain (`TIME_ZONE=America/Denver`). `static/js/tz.js` relocalizes `<time datetime>` elements to the viewer's browser tz on page load, so kickoffs read local without a per-user preference.

## Architecture

Django 5.2 monolith, server-rendered HTML with HTMX for interactive pick swaps. No SPA, no build step.

```
apps/
├── accounts/    Custom User (email is USERNAME_FIELD, username is display name),
│                signup, Django-auth login/logout/password-reset,
│                bootstrap_superuser management command.
└── bracket/     Team, Match, Group, GroupMembership, Prediction, ScoringRule.
                 services.py — view-model builders + pick reconciliation.
                 seed_teams / seed_bracket / seed_scoring_rules commands.
config/
├── settings/
│   ├── base.py  Shared config, custom env() / env_bool() / env_list() helpers.
│   ├── dev.py   DEBUG=True, insecure SECRET_KEY fallback, console email backend.
│   └── prod.py  Whitenoise, Resend email via django-anymail, HSTS, SSL cookies,
│                dj-database-url from DATABASE_URL. Fails loud on missing config.
└── urls.py
templates/       Django templates. base.html wires HTMX + tz.js. Bracket partials
                 (_user_bracket.html, _group_bracket.html, _match_card.html) are
                 the HTMX swap targets.
static/
├── css/style.css
└── js/tz.js     Relocalizes <time datetime> to the browser's tz.
```

**Data model shape.** `Match.feeds_into` + `Match.feeds_as` ("home"/"away") form the bracket tree. Overriding `Match.save` triggers `_advance_winner`, which pushes `winner` into the downstream match's home or away slot and, for semifinals, wires the loser into `THIRD`. `Prediction` is per (user, group, match) with a unique constraint; `Prediction.clean()` blocks new/edited picks once `is_tournament_locked()` is true. `Group.save` generates a 6-char join code from a Crockford-ish alphabet (no ambiguous glyphs) with a uniqueness retry loop.

**Deploy.** Render free tier, `render.yaml` in the repo. Build runs collectstatic → migrate → `bootstrap_superuser` → `seed_bracket` → `seed_scoring_rules`, so a fresh environment comes up fully wired. Startup is `gunicorn config.wsgi:application`; `config/wsgi.py` defaults `DJANGO_SETTINGS_MODULE=config.settings.prod`. Postgres via `DATABASE_URL`, outbound email via Resend, static assets via Whitenoise's manifest storage.

## Local development

Prereqs: Python 3.12, a virtualenv at `.venv/`. SQLite is fine for dev — that's the default in `base.py`.

**First-time setup:**
```bash
python3.12 -m venv .venv
cp .env.example .env       # fill in SECRET_KEY (optional in dev), leave the rest blank
make install
make migrate
.venv/bin/python manage.py seed_teams
.venv/bin/python manage.py seed_bracket
.venv/bin/python manage.py seed_scoring_rules
make createsuperuser
```

**Day-to-day:**
```bash
make run       # runserver on :8000, DJANGO_SETTINGS_MODULE=config.settings.dev via manage.py
make test      # full pytest suite
make test bracket                   # everything in apps/bracket/tests/
make test bracket:test_services     # single file
make test bracket:test_services:test_reconcile_clears_orphan_r16  # -k on the test name
make lint      # flake8 apps config manage.py
make format    # black
make check     # manage.py check
```

**Admin flow during a real tournament.** Log in at `/admin/`, edit a `Match` row, set `winner` to the actual winning team, save. `_advance_winner` pushes that team into the downstream slot. For semifinals, the loser is auto-wired into `THIRD`. Leaderboards recompute on next render.

**Settings selection.** `manage.py` and `pytest.ini` both point at `config.settings.dev`; `config/wsgi.py` and `config/asgi.py` default to `config.settings.prod`. Override with `DJANGO_SETTINGS_MODULE` if needed.

**Password-reset in dev.** `dev.py` uses Django's console email backend, so the reset email prints to the terminal instead of being sent — copy the link from there. In prod, Resend delivers via `django-anymail`.
