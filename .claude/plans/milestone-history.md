# Milestone History

Append-only log of completed phases / milestones. Design and intent live in
`initial-architecture.md` (or future phase-specific plan files); this file is
just "what got shipped, when, and any deviations from the plan worth flagging."

---

## Phase 0 — Project skeleton ✅ 2026-06-23

**Done**
- Python upgraded 3.8.8 → 3.12.13 (Homebrew). venv recreated; existing pinned
  deps reinstalled cleanly.
- Django 5.2.15 LTS installed (chose LTS over 6.0.6 for stability).
  Transitive pins added: `asgiref==3.11.1`, `sqlparse==0.5.5`.
- `django-admin startproject config .` scaffolded the project. The
  auto-generated `config/settings.py` was deleted and replaced with a split:
  `config/settings/base.py` (shared), `dev.py` (DEBUG=True, SQLite, fallback
  SECRET_KEY, console email), `prod.py` (DEBUG=False, hard-fails on missing
  SECRET_KEY/ALLOWED_HOSTS, HSTS + secure cookies).
- `manage.py` defaults to `config.settings.dev`; `wsgi.py`/`asgi.py` default
  to `config.settings.prod`.
- `python-dotenv` wired in `base.py` so `.env` is auto-loaded when present.
- Custom `User` model in `apps.accounts` with email as `USERNAME_FIELD`;
  custom `UserManager`. Migration `0001_initial` generated.
- Admin registered for `User` with email-friendly fieldsets.
- Makefile targets: `install`, `run`, `migrate`, `makemigrations`, `shell`,
  `createsuperuser`, `test`, `lint`, `format`, `check`.
- `.python-version` pinned to `3.12`.
- `.env.example` rewritten with `SECRET_KEY`, `ALLOWED_HOSTS`,
  `RESEND_API_KEY` (commented out — not needed until Phase 2).

**Smoke test**
- `make migrate` applied 19 migrations cleanly (incl. `accounts.0001_initial`
  before `admin.0001_initial`, confirming the custom-User dependency was
  ordered correctly).
- Runserver on `127.0.0.1:8765` returned `HTTP 302 → /admin/login/?next=/admin/`
  for `/admin/` — healthy admin response for unauthenticated request.
- `make lint` clean, `make check` clean.

**Deviations from `initial-architecture.md`**
- Plan said `django==5.1.x`; actual install was `5.2.15` (LTS). Steven
  selected this after seeing all options. Plan file has been updated to
  reflect.
- Old `Makefile` target `pyshell` (which called `ipython`) was removed —
  `ipython` was never in `requirements.txt` so the target would have broken
  on the new venv. Replaced by `make shell` (Django shell). Adding `ipython`
  back would require a separate dependency approval.

**Removed / abandoned**
- `API_FOOTBALL_KEY` from `.env.example` (api-football.com free tier doesn't
  cover this WC). The variable was removed from the example template; user's
  own `.env` not touched.

**Untouched (per working contract)**
- `.env` — never read, edited, or inspected.
