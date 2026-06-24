# World Cup Knockout Bracket — Initial Architecture Plan

## Context

You're building a small, group-based bracket pool app for the 2026 FIFA World Cup
knockout stage. Users sign up, create or join a group via a share code, make
predictions for each match (which auto-populate later-round slots in that user's
*predicted* bracket), see picks lock 1h before kickoff, and watch a per-group
leaderboard update as results come in. You're the sole admin and will manually
maintain match data (api-football.com free tier doesn't cover this WC).

**Hard constraint**: today is 2026-06-23. Round of 32 starts **June 28** — five
days to a usable v1. Tournament ends **July 19** (~4 weeks of useful life).
This drives every choice toward "fastest path to ship, in tools you already
know, on infrastructure with a free window long enough to cover the run".

---

## Recommended stack (with rationale — pending your approval)

### Framework: Django 5.x + HTMX
- **Why Django**: you're a Django native. The app is a textbook Django shape —
  auth, ORM, admin panel for manual match management, server-rendered pages.
  Picking anything else burns runway on a learning curve for a 4-week app.
- **Why HTMX instead of React/DRF**: the "modern feel" you want (live
  leaderboard updates, in-place pick updates, no full-page reloads) is
  achievable with HTMX's `hx-get`/`hx-post`/`hx-swap` against normal Django
  views returning HTML fragments. Avoids an entire second codebase, a build
  pipeline, and a JSON API surface. ~1 day saved at minimum.
- **Alternative considered**: Django + DRF + React/Next.js — rejected as
  over-budget for the timeline and pool size.

### Database: PostgreSQL (SQLite for local dev)
- **Why Postgres in prod**: it's what your host will give you for free, it's
  what you know, and it handles the concurrent writes during match-time
  better than SQLite. We won't actually push SQLite's limits with a small
  pool, but Postgres is the safe default and you already know it.
- **Why SQLite locally**: zero-config, file-based, fine for dev. Django
  switches between them via `DATABASES` config.
- **Skip Redis**: scope doesn't justify it. No background jobs that need a
  queue, no caching tier under load. Pick locking can be enforced in a model
  `clean()` / view check using `kickoff_at - now() > 1h`.

### Hosting: Render free tier
- **Why Render**:
  - Free web service (Python/Django runtime, auto-deploys from GitHub).
  - Free Postgres database for **90 days** — that exactly covers the
    tournament window with margin.
  - Custom domain support if you decide later.
  - Single dashboard, near-zero ops work.
- **Known downside**: free web service spins down after 15 min of idle and
  takes ~30s to wake on first hit. For a small group pool checked
  periodically this is annoying but tolerable. We can mitigate with a
  trivial uptime ping (cron-job.org, free) if it bothers you.
- **Alternatives considered**:
  - **Fly.io**: always-on free tier exists, but more setup complexity
    (Dockerfile, `fly.toml`, volume management for Postgres).
  - **PythonAnywhere**: free tier doesn't include Postgres.
  - **Railway/Vercel**: trial credit / Python-serverless cold start
    headaches — not worth it for a Django monolith.

### Domain: free `*.onrender.com` subdomain (e.g. `wc26-bracket.onrender.com`)
- Costs nothing, shareable as a link. Custom domain can be added later if
  you want (~$10–12/yr for a `.com`, but you said avoid spend).

### Auth: Django's built-in `auth` + email-as-username + email-based password reset
- Minimal account = email + password. No social login.
- Custom User model with `email` as `USERNAME_FIELD` (from day 1; migrating
  the user model later is painful).
- Use Django's built-in `PasswordResetView` / `PasswordResetConfirmView` —
  no need for `django-allauth`. These ship with templates we override.
- **SMTP provider — recommended: Resend** (free tier: 3,000 emails/mo,
  100/day; clean API; just an API key + `django-anymail` for the backend).
  - Alternatives: SendGrid (100/day free, more setup), Mailgun (limited free),
    Gmail SMTP (not for production, app-password fragility).
- **You'll need to**: create a Resend account, verify a sender domain or use
  their `onboarding@resend.dev` for testing, drop the API key into `.env`
  (I will *not* touch the file — I'll tell you the key name and value).

---

## Proposed data model

Names are tentative; we'll refine when implementing.

- **User** — Django default (`email` set as `USERNAME_FIELD` via a thin
  custom user model so we don't have to migrate later).
- **Team** — `code` ("USA"), `name`, `flag_emoji`.
- **Match** — `round` (enum: R32/R16/QF/SF/THIRD/FINAL), `slot` (stable
  identifier like `"R16-1"`), `home_team` / `away_team` (FK Team, nullable
  until prior round resolves), `kickoff_at`, `winner` (FK Team, nullable).
  Plus `feeds_into` (FK Match) + `feeds_as` ("home"|"away") to wire the
  bracket tree.
- **Group** — `name`, `join_code` (unique short string), `owner` (FK User),
  `created_at`.
- **GroupMembership** — `group`, `user`, `joined_at`. Unique on (group, user).
- **Prediction** — `user`, `group`, `match`, `picked_winner` (FK Team),
  `updated_at`. Unique on (user, group, match). Validation: reject save if
  `match.kickoff_at - now() < 1h`.
- **ScoringRule** — `round` (unique, one row per round), `points` (int).
  Editable in Django admin. Seeded with sane defaults (e.g.,
  R32=1, R16=2, QF=4, SF=8, THIRD=10, FINAL=15) you can override anytime.
  Scoring queries join through this table rather than hardcoding values.

Match count: 16 (R32) + 8 (R16) + 4 (QF) + 2 (SF) + 1 (3rd) + 1 (F) = **32
matches**. Tiny. Postgres + sane indexing is overkill, which means we have
plenty of headroom.

---

## Implementation phases

> Each phase ends with you reviewing before we move on. Nothing merges
> without your sign-off, per working contract.

**Phase 0 — Project skeleton (today)**
- `django-admin startproject` into the repo.
- Custom `User` model from day 1 (avoid future migration pain).
- Settings split (`settings/base.py`, `dev.py`, `prod.py`) with
  `python-dotenv` loading.
- Update `Makefile` with `runserver`, `migrate`, `lint`, `format` targets.
- Add a `.python-version` (3.12).

**Phase 1 — Core models + admin**
- All models above. Migrations. Register in Django admin so you can hand-key
  match data once R32 draw is published June 27.
- Seed script for the 32 teams (codes + flag emojis).

**Phase 2 — Auth + groups**
- Sign up / log in / log out views (function-based, with Django's auth
  forms).
- Create-group view (generates a join code).
- Join-group view (enter join code).
- "My groups" landing page.

**Phase 3 — Predictions UI**
- Bracket view per group: shows the 32-match bracket, user's own picks
  inline. Each match is a small HTMX-powered form: click a team to pick,
  POST updates the prediction, swaps the fragment.
- Server-side: derive subsequent rounds' "predicted matchups" from this
  user's earlier picks. Lock-checks on every save (`kickoff_at - now > 1h`).
- **Pick visibility (your decision)**: a user only sees other members'
  picks for a match *after* that match has locked (i.e.,
  `kickoff_at - now <= 1h`). Before that, the bracket shows other members'
  rows as "—" or "locked icon" for un-locked matches. Enforced in the
  template/view layer by gating on `match.is_locked()`.

**Phase 4 — Leaderboard + scoring**
- Compute per-user points within a group from `Prediction` × `Match.winner`.
- Leaderboard page (HTMX polling every ~30s during match windows, or a
  manual refresh button — your call).

**Phase 5 — Deploy to Render**
- `requirements.txt` updated, `gunicorn` + `whitenoise` added.
- `render.yaml` for one-click setup.
- Database migration, create superuser, smoke test.

**Phase 6 — Hardening before kickoff (June 27 buffer)**
- Lock-time enforcement test pass.
- Manually enter the R32 draw the moment FIFA publishes it.
- Invite real users.

---

## Critical files (to be created)

- `manage.py`, `config/settings/{base,dev,prod}.py`, `config/urls.py`,
  `config/wsgi.py`
- `apps/accounts/models.py` — custom User
- `apps/bracket/models.py` — Team, Match
- `apps/groups/models.py` — Group, GroupMembership, Prediction
- `apps/bracket/admin.py` — match management UI
- `templates/` — base layout, bracket view, group views, auth pages
- `Makefile` — extended with django targets
- `render.yaml` — deploy config

---

## Verification plan

- `make lint` + `make format` clean.
- `python manage.py test` covers: pick-lock enforcement, leaderboard
  scoring, join-code uniqueness.
- Manual: create two accounts in dev, create a group, swap picks, verify
  leaderboard, verify a pick is rejected when `kickoff_at` is <1h away
  (use a fixture match with kickoff "now + 30min").
- Deploy smoke test on Render: signup, create group, make a pick, see it
  persist across reload.

---

## Decisions locked in (from your answers)

1. **Stack**: Django 5 + HTMX + Postgres + Render free tier. ✓
2. **Auth**: email + password with email-based password reset; SMTP via
   Resend (recommended; final pick after you've seen the option). ✓
3. **Scoring**: `ScoringRule` model, per-round values editable in Django
   admin. Seeded with sensible defaults. ✓
4. **Pick visibility**: only after lock (1h pre-kickoff). ✓

## New dependencies I'll be asking you to approve (exact pins, per contract)

Before installing anything I will come to you with the exact version. Likely
list, so you can think about it:

- `django==5.1.x` (latest patch at install time)
- `psycopg[binary]==3.2.x` (Postgres driver)
- `python-dotenv==1.0.1` (already present)
- `gunicorn==23.x` (prod WSGI server)
- `whitenoise==6.x` (static files on Render without a CDN)
- `django-anymail[resend]==12.x` (Resend backend for Django email)
- `dj-database-url==2.x` (parse `DATABASE_URL` env var Render gives us)
- `pytest-django==4.x` + `pytest==8.x` (test runner — optional; can stick
  with `manage.py test` if you'd rather not add deps)

## What happens next, once you exit plan mode

I'll start with Phase 0: `django-admin startproject`, settings split,
custom user model, Makefile targets. I'll stop and check in after the
skeleton is in place and before installing anything beyond Django itself —
so you can see the layout and approve dependencies one at a time.
