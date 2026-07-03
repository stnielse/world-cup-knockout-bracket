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

---

## Phase 1 — Core models + admin ✅ 2026-06-24

**Scope shipped**

Created `apps/bracket/` containing all six models (Team, Match, Group,
GroupMembership, Prediction, ScoringRule), two enums (Round, FeedAs), full
admin registrations, and two idempotent seed commands.

**Files added**
- `apps/bracket/__init__.py`
- `apps/bracket/apps.py` — `BracketConfig`, label `"bracket"`
- `apps/bracket/models.py` — 6 models + `Round` / `FeedAs` `TextChoices`
- `apps/bracket/admin.py` — 6 `ModelAdmin` classes with `list_display`,
  `list_filter`, `autocomplete_fields`, `search_fields` (autocomplete on
  `User` works because `apps/accounts/admin.py` already defines
  `search_fields`)
- `apps/bracket/migrations/__init__.py`
- `apps/bracket/migrations/0001_initial.py` (auto-generated, applied)
- `apps/bracket/management/__init__.py`
- `apps/bracket/management/commands/__init__.py`
- `apps/bracket/management/commands/seed_teams.py`
- `apps/bracket/management/commands/seed_bracket.py`

**Files modified**
- `config/settings/base.py` — added `"apps.bracket"` to `INSTALLED_APPS`

**Model design decisions (Steven approved)**
- `Match.slot` uses human-readable names (`R32-1`…`R32-16`, `R16-1`…`R16-8`,
  `QF-1`…`QF-4`, `SF-1`, `SF-2`, `THIRD`, `FINAL`) — sortable within a
  round, no decoding required.
- `Group.join_code` field reserved as `CharField(max_length=8, unique=True)`;
  generation logic (6-char uppercase alphanumeric, ambiguity-stripped) is
  Phase 2's problem.
- `Prediction.save()` calls `full_clean()` so the lock check in `.clean()`
  cannot be bypassed by direct `.save()` calls.
- `Match.is_locked()` returns `True` iff `kickoff_at - now() <= 1h`
  (`LOCK_WINDOW = timedelta(hours=1)`).
- `on_delete` policy:
  - `Group.owner` → `PROTECT` (can't delete a user who owns groups)
  - `Match.{home_team, away_team, winner}` → `PROTECT` (can't delete a team
    referenced by a match)
  - `Prediction.picked_winner` → `PROTECT` (same reasoning)
  - `GroupMembership.{group, user}` → `CASCADE` (membership only exists in
    context of both)
  - `Prediction.{user, group, match}` → `CASCADE` (prediction only exists in
    context of all three)
  - `Match.feeds_into` → `SET_NULL` (re-wireable without data loss)
- Unique constraints declared via `Meta.constraints` (Django ≥2.2 idiom),
  not `unique_together`: `unique_group_member` on `(group, user)` and
  `unique_user_group_match_prediction` on `(user, group, match)`.

**Bracket wiring (Option B for 3rd-place)**
- `seed_bracket` creates all 32 matches and wires the deterministic
  advancement tree: winners of paired sibling matches feed into a parent
  match (odd index → `home`, even → `away`).
- `THIRD` is intentionally left unwired. Its participants are the *losers*
  of `SF-1` and `SF-2`; the model has no `loser_feeds_into` field. On
  2026-07-15 after the SFs are played, set `THIRD.home_team` and
  `THIRD.away_team` manually in admin. (Considered alternatives:
  A — add `loser_feeds_into` / `loser_feeds_as` fields; C — hardcode in
  scoring logic. Both rejected as over-engineered for a single match where
  the user is the sole admin.)
- Placeholder `kickoff_at = datetime(2099, 12, 31, tzinfo=UTC)` for all new
  matches. Deliberately absurd so it's visually obvious in admin if you
  forgot to fill a real kickoff. Re-running `seed_bracket` does NOT
  overwrite an already-entered `kickoff_at` (uses `get_or_create` for the
  row, then conditionally re-syncs only the structural fields `round`,
  `feeds_into`, `feeds_as` — tournament data fields are left alone).

**Smoke tests (all green)**
- `make lint` clean
- `make check` clean
- `makemigrations bracket` produced one clean migration
- `migrate` applied `bracket.0001_initial` cleanly
- `seed_teams` first run: 3 created, 0 updated, 3 total
- `seed_teams` second run: 0 created, 3 updated, 3 total ← idempotent ✓
- `seed_bracket` first run: 32 created, 0 round-synced, 30 (re)wired,
  32 total matches
- `seed_bracket` second run: 0 created, 0 round-synced, 0 (re)wired
  ← idempotent ✓
- Wiring spot-check via `manage.py shell`:
  - R32-1 → R16-1 (home), R32-2 → R16-1 (away)
  - R32-7 → R16-4 (home)
  - R16-1 → QF-1 (home), R16-4 → QF-2 (away)
  - QF-2 → SF-1 (away)
  - SF-1 → FINAL (home), SF-2 → FINAL (away)
  - THIRD → NONE (unwired per Option B ✓)
  - FINAL → NONE (terminal ✓)
- Admin verified live by Steven at `http://127.0.0.1:8000/admin/` — all six
  bracket models visible, populated with seed data.

**Deviations from `initial-architecture.md`**
- **App layout collapsed**: plan said two apps (`apps/bracket/` for
  Team & Match, `apps/groups/` for Group / GroupMembership / Prediction).
  Actual: one app `apps/bracket/` holds all six models. Reason: tight
  coupling between the models, small scale (~6 models total), simpler
  single-app migration sequence. Plan file updated to reflect.
- **`ScoringRule` placement**: plan didn't specify which app. Placed in
  `apps/bracket/` since it's tournament data, not user/group data.
- **`seed_bracket` added**: plan only mentioned `seed_teams`. The cost of
  hand-creating 32 matches and wiring `feeds_into` / `feeds_as` in admin
  (~190 fields, easy to mis-wire silently) made a second seed command
  worth writing. Plan updated to mention it.

**Pending / deferred (NOT blockers for Phase 1 sign-off)**
- **Team data**: only 3 host nations (USA, CAN, MEX) seeded as
  placeholder. Full 32 knockout teams to be populated ~2026-06-27 once
  group stage finalizes. Steven to provide the list; I'll edit the
  `TEAMS` constant in `seed_teams.py` and re-run.
- **ScoringRule data**: no rows seeded. Will create in admin (or add a
  `seed_scoring_rules` command later) with values from the plan:
  R32=1, R16=2, QF=4, SF=8, THIRD=10, FINAL=15.
- **Match kickoff times**: all 32 matches carry the 2099-12-31
  placeholder. Will fill from FIFA's published WC 2026 knockout schedule.
- **Match teams**: R32 fills from the draw (~2026-06-27); later rounds
  fill from results.
- **`THIRD.home_team` / `THIRD.away_team`**: left null per Option B; fill
  manually 2026-07-15.
- **Auto-advancement on `Match.winner`**: when a winner is set, the team
  should auto-populate the next match's `home_team` / `away_team` per
  `feeds_into` / `feeds_as`. Deferred to a later phase (probably Phase 5
  alongside scoring).

**No new dependencies introduced.** Pure Django.

**Plan revision (alongside this entry)**
- Reordered phases in `initial-architecture.md` so Render deploy lands
  between auth (Phase 2) and predictions UI (was Phase 3, now Phase 4).
  Reason: with kickoff 2026-06-28, front-loading infra risk is more
  valuable than the original "deploy at the end" ordering.

**Untouched (per working contract)**
- `.env` — never read, edited, or inspected.

---

## Phase 2 — Auth + groups ✅ 2026-06-24

**Scope shipped**

End-to-end account lifecycle (signup → login → password reset → logout) and
group lifecycle (create with auto-generated join code → share → join).
Anonymous users land on login; authenticated users land on a "My groups"
page from which they can create or join groups. Password reset works
locally against Django's console email backend (real SMTP comes with
Phase 3 Render deploy).

**Files added**

*Python:*
- `apps/accounts/forms.py` — `EmailUserCreationForm` subclassing Django's
  `UserCreationForm` with `model = User`, `fields = ("email",)` so it picks
  up `email` as the username field automatically.
- `apps/accounts/views.py` — `signup` (FBV): validates form, creates user,
  auto-logs them in via `django.contrib.auth.login`, redirects to
  `my_groups`.
- `apps/accounts/urls.py` — `signup/` route + `include("django.contrib.auth.urls")`
  to mount login, logout, password_change, password_reset (full flow) at
  their conventional URL names.
- `apps/bracket/forms.py` — `GroupCreateForm` (ModelForm with `name` only)
  and `GroupJoinForm` (plain Form; `clean_join_code` `.strip().upper()`s
  the input then looks up the `Group` — stashes it on `self.group` so the
  view doesn't re-query).
- `apps/bracket/views.py` — `home` (redirects to `my_groups` if authed,
  else `login`), `my_groups` (lists current user's memberships), and
  `create_group` / `join_group` (both `@login_required` FBVs).
- `apps/bracket/urls.py` — `/` → home, `/groups/` → my_groups,
  `/groups/new/` → create_group, `/groups/join/` → join_group.

*Templates (all extend `base.html`):*
- `templates/base.html` — single shared layout with header, conditional
  auth nav (logout posted via inline form per Django 5's POST-only logout
  requirement), messages slot, content block.
- `templates/registration/login.html`, `logged_out.html`,
  `password_reset_form.html`, `password_reset_done.html`,
  `password_reset_confirm.html`, `password_reset_complete.html` — the six
  templates `django.contrib.auth.views` looks up by name. Placed under
  `templates/registration/` per Django's hardcoded convention.
- `templates/registration/password_reset_email.html` and
  `password_reset_subject.txt` — body / subject for the reset email.
- `templates/accounts/signup.html`, `templates/bracket/my_groups.html`,
  `templates/bracket/group_create.html`, `templates/bracket/group_join.html`
  — the app-specific pages.

*Static:*
- `static/css/style.css` — ~70 lines of plain CSS. Centered 720px column,
  system font stack, simple form/button styling, lists for groups. No
  framework.

**Files modified**
- `apps/bracket/models.py` — added `import secrets`, the
  `JOIN_CODE_ALPHABET` / `_LEN` / `_MAX_TRIES` constants, a
  `generate_join_code()` helper, and a `Group.save()` override that fills
  `self.join_code` if blank by generating + pre-checking uniqueness
  (retries up to 10x; falls through to DB unique constraint as the
  ultimate safety net).
- `config/settings/base.py` — added `LOGIN_URL = "login"`,
  `LOGIN_REDIRECT_URL = "my_groups"`, `LOGOUT_REDIRECT_URL = "login"` so
  `@login_required` and Django's auth views know where to send users.
- `config/urls.py` — replaced the bare `admin/` only urlconf with three
  includes: `admin/`, `accounts/` → `apps.accounts.urls`, `""` →
  `apps.bracket.urls`.
- `apps/bracket/migrations/0001_initial.py` — black reformatted on first
  `make format` of Phase 2's new files. Not a Phase 2 intent change; just
  noise from the formatter touching files it hadn't seen yet.

**Design decisions (Steven approved up-front)**
- **Password reset wired now, console backend, real SMTP later** (decision
  1a): kept `django-anymail` and the Resend dep out of Phase 2 entirely.
  Template + URL + view layer is complete; only the email transport
  changes when Phase 3 ships. `dev.py` already had
  `EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"` set
  from Phase 0, so zero settings work was needed.
- **Plain CSS, no framework** (decision 2): wrote a single ~70-line
  stylesheet. Treating Phase 2 templates as throwaway pending Phase 4
  (predictions UI) where the bracket layout will actually pressure-test
  the styling approach.
- **Subclass `UserCreationForm`** (decision 3): 8 lines vs hand-rolling
  password-confirmation + hashing logic. Built-in form correctly handles
  custom `User` with `email` as `USERNAME_FIELD` once `Meta.model` and
  `Meta.fields` are overridden.
- **Join code: 6 chars from 31-char alphabet** (decision 4): alphabet is
  `ABCDEFGHJKMNPQRSTUVWXYZ23456789` (uppercase letters + digits,
  excluding `0`, `O`, `1`, `I`, `L`). 31⁶ ≈ 887M combos so collision is
  vanishingly rare at any realistic group count; pre-check loop is more
  about clean error semantics than collision avoidance. Generated by
  `secrets.choice` (CSPRNG, not `random`) since the code is also a
  share-link credential — predictable codes would let outsiders guess
  their way into a group.
- **Logged-out `/` → login, logged-in `/` → my_groups** (decision 5): no
  marketing page; this is a tiny private pool. The `home` view is a
  three-line conditional redirect.

**Implementation notes (judgment calls inside the agreed scope)**
- **FBV for signup, but built-in CBVs for everything else auth**: the
  plan said "function-based, with Django's auth forms". I went FBV for
  the views I owned (signup, group create/join), but for login, logout,
  password-reset (the full 6-step flow) I mounted
  `django.contrib.auth.urls` rather than re-implementing those as FBVs.
  Net effect: same UX, ~150 fewer lines of view code, and the templates
  are still the customization surface area. Worth flagging because
  "function-based" was explicit in the plan.
- **Owner auto-added as member on group create**: `create_group`
  immediately creates a `GroupMembership` row for the creator. Otherwise
  the owner would have to "join" their own group, which is silly.
- **`GroupJoinForm.clean_join_code` is case-insensitive on input**: the
  smoke test confirms a lowercase code lookup succeeds because the form
  uppercases before querying.
- **`Group.save()` join-code generation**: TOCTOU-safe enough — the
  pre-check is best-effort and the DB unique constraint is the real
  guard. At our scale, collisions are essentially impossible.

**Smoke tests (Django test client through `manage.py shell`, all green)**

Anonymous routing:
```
GET /               → 302 /accounts/login/
GET /groups/        → 302 /accounts/login/?next=/groups/
GET /accounts/login → 200 (bytes=1301)
GET /accounts/signup→ 200 (bytes=1909)
GET /password_reset → 200 (bytes=1034)
```

Signup + auto-login + landing:
```
POST signup         → 200 path=/groups/
user exists?        → True
GET /groups/ (authed)→ 200
```

Create group:
```
POST /groups/new/   → 200 path=/groups/
group join_code     → 'J3PT7S' (len=6)   ← all chars from approved alphabet
owner is alice?     → True
alice in group?     → True
```

Second user joins via lowercase code (form normalizes):
```
POST /groups/join/  → 200 path=/groups/
members count       → 2
```

Bad code rejected with form error:
```
POST bad code       → 200 has_error=True   ← "No group found" in body
```

Password reset email actually sent (console backend printed full email
to stderr — subject, From/To, body with `/accounts/reset/<uid>/<token>/`
link); request redirected to `/accounts/password_reset/done/`.

Logout:
```
POST /logout/       → 200 path=/accounts/login/
```

`make check`: System check identified no issues (0 silenced).
`make lint`: clean.
`make format`: only side effect was reformatting the auto-generated
Phase 1 migration file (noted above).

**Deviations from `initial-architecture.md`**
- **Auth views are mostly built-in CBVs, not FBVs.** Plan said
  "function-based, with Django's auth forms" for all auth views. I kept
  signup as an FBV but delegated login / logout / password-reset to
  `django.contrib.auth.urls` (CBVs under the hood). Same UX, simpler
  code, no real downside. Noting it because it's a literal departure
  from the plan wording.
- **`render.yaml` and Resend deps not touched.** Per decision 1a,
  Resend / `django-anymail` / SMTP-from-address config is Phase 3's
  problem. The reset email currently goes out as
  `From: webmaster@localhost` (Django default).

**Pending / deferred (NOT blockers for Phase 2 sign-off)**
- **Real From: address** for password-reset email — Phase 3, when we
  wire Resend and set `DEFAULT_FROM_EMAIL`.
- **Group detail / membership listing UI** — currently `my_groups` shows
  group name + join code, but no member list, no edit/delete, no "leave
  group". Will revisit when we know whether Phase 4 (predictions UI)
  wants a group-detail page anyway.
- **Email verification on signup** — not required for v1 per scope.
  Users sign up with any email and can immediately use the app. Resend
  later if we want it.
- **Rate limiting on signup / password-reset** — none. Acceptable for
  a private pool of friends; revisit if we ever go public.
- **No tests yet.** Smoke test was scripted ad-hoc via test client in
  `shell`; not yet checked in as a `TestCase`. Will add proper test
  coverage for the lock-time + scoring logic in Phase 5, and probably
  backfill auth/group tests then too.

**No new dependencies introduced.** Pure Django. Resend + django-anymail
deferred to Phase 3 per decision 1a.

**Untouched (per working contract)**
- `.env` — never read, edited, or inspected.

---

## Phase 3 — Deploy to Render ✅ 2026-06-24 (live verified 2026-06-25)

**Scope shipped**

Render Blueprint-driven deploy of the full Phase 1/2 app. Web service +
free Postgres (90-day window) + whitenoise static files + gunicorn WSGI +
Resend email backend, all defined declaratively in `render.yaml`. Includes
an env-driven `bootstrap_superuser` management command because Render's
free tier doesn't expose a shell (forced a mid-phase pivot from the
"manual via shell" plan).

Steven completed the GitHub push at end of this round; the Render build /
deploy run itself was not observed in this session. Live-URL smoke test
is the only blocker remaining for Phase 3 sign-off.

**Files added**

*Python:*
- `apps/accounts/management/__init__.py` (empty)
- `apps/accounts/management/commands/__init__.py` (empty)
- `apps/accounts/management/commands/bootstrap_superuser.py` — 17-line
  custom management command. Reads `DJANGO_SUPERUSER_EMAIL` and
  `DJANGO_SUPERUSER_PASSWORD` from environment. No-ops with a log message
  if either is unset. No-ops with a log message if a user with that email
  already exists. Otherwise calls `User.objects.create_superuser()`.
  Designed to be safe in `buildCommand` on every deploy.

*Infra:*
- `render.yaml` — Render Blueprint spec defining one web service
  (`wc26-bracket`, runtime `python`, plan `free`, branch `main`) and one
  Postgres database (`wc26-bracket-db`, plan `free`). Build chain:
  `pip install -r requirements.txt` → `collectstatic --noinput` →
  `migrate --noinput` → `bootstrap_superuser` → `seed_bracket`. Start
  command: `gunicorn config.wsgi:application`. Six env vars wired:
  `DJANGO_SETTINGS_MODULE=config.settings.prod`, `PYTHON_VERSION=3.12.13`,
  `SECRET_KEY` (Render `generateValue: true`), `DATABASE_URL`
  (`fromDatabase` reference to the Postgres instance, so Render auto-wires
  the connection string), `DEFAULT_FROM_EMAIL=onboarding@resend.dev`
  (hardcoded), and three `sync: false` slots that Steven sets in the
  dashboard: `RESEND_API_KEY`, `DJANGO_SUPERUSER_EMAIL`,
  `DJANGO_SUPERUSER_PASSWORD`.

**Files modified**

- `config/settings/prod.py` — full prod config now:
  - `DATABASES` parsed from `DATABASE_URL` via `dj_database_url.parse(...,
    conn_max_age=600, ssl_require=True)`. 10-minute connection pooling
    avoids reconnect overhead on each request; `ssl_require=True` matches
    Render Postgres's hard requirement.
  - `ALLOWED_HOSTS` reads from env var, then *additionally* appends
    `RENDER_EXTERNAL_HOSTNAME` (an env var Render auto-sets on every
    service) if present. Effect: Steven doesn't need to manually set
    `ALLOWED_HOSTS` for the `*.onrender.com` URL — it just works. He'd
    only need to set it when adding a custom domain.
  - Whitenoise middleware inserted at index 1 (right after
    `SecurityMiddleware`, per whitenoise docs).
  - `STORAGES` dict configured with the Django 5 API (not the deprecated
    `STATICFILES_STORAGE` shim). Uses
    `whitenoise.storage.CompressedManifestStaticFilesStorage` for the
    `staticfiles` key (compresses + hashes static files for
    long-term-cache headers) and the default `FileSystemStorage` for
    `default`.
  - Email: `EMAIL_BACKEND = "anymail.backends.resend.EmailBackend"`,
    `ANYMAIL = {"RESEND_API_KEY": ...}`, `DEFAULT_FROM_EMAIL` and
    `SERVER_EMAIL` both default to `onboarding@resend.dev` (Resend
    sandbox sender; override via env var when verified domain ships).
  - All four env-var checks raise `ImproperlyConfigured` early in module
    load if missing (`SECRET_KEY`, `ALLOWED_HOSTS`/`RENDER_EXTERNAL_HOSTNAME`,
    `DATABASE_URL`, `RESEND_API_KEY`). Prevents booting a half-configured
    prod instance.
  - Security headers from Phase 0 retained (`SECURE_PROXY_SSL_HEADER`,
    secure cookies, HSTS 30d with subdomains + preload).

- `requirements.txt` — extended with seven new pinned dependencies (see
  below for the full table).

**Design decisions (Steven approved up-front via AskUserQuestion)**
- **Decision 1a: Resend wired in Phase 3, not split to 3.5.** Means the
  password-reset flow is end-to-end functional on live URL the moment
  deploy succeeds (modulo the sandbox recipient restriction).
- **Decision 2-sandbox: Use Resend's `onboarding@resend.dev` sender, not
  a verified domain.** Zero DNS / domain-purchase work to ship.
  Trade-off: sandbox can only deliver to email addresses on Steven's
  Resend verified list, so non-verified friends won't actually receive
  password-reset emails until a domain is verified. Documented as a
  reversible decision — flipping to a verified domain later requires
  *zero* code change: one env var (`DEFAULT_FROM_EMAIL`) flip in Render
  dashboard + DNS work on the domain side, auto-redeploys.
- **Decision 3-blueprint: `render.yaml` IaC, not manual dashboard
  setup.** Whole infra reproducible from repo; future tear-down and
  rebuild costs nothing.
- **Decision 4 → pivoted mid-phase.** Originally: "Manual via Render
  shell." Discovered (Steven flagged it) that Render free tier doesn't
  expose shell access. Pivoted to env-driven `bootstrap_superuser`
  management command baked into `buildCommand`. Slightly more code but
  fully self-contained and idempotent.

**Implementation notes (judgment calls inside the agreed scope)**
- **`django-anymail==15.0` installed WITHOUT the `[resend]` extra.**
  Initial install used `django-anymail[resend]==15.0` which pulled ~15
  transitives (svix, standardwebhooks, pydantic, httpx, anyio, etc.) for
  inbound webhook signature verification — a code path we don't use in
  v1 (no bounce/delivery callbacks). I flagged the over-pull, Steven
  confirmed "manual debugging sounds fine", and we uninstalled the
  svix tree and reinstalled clean. Net new deps dropped from 24 → 6.
  `pip check` clean after the reinstall.
- **`bootstrap_superuser` is idempotent by design and never raises.**
  Logs a clear message in all three cases (no env, user exists,
  created). Means the command being permanently in `buildCommand` is
  safe; Steven can leave the env vars set or delete them after first
  deploy without any error noise.
- **`ALLOWED_HOSTS` auto-derives from `RENDER_EXTERNAL_HOSTNAME`** — see
  prod.py notes above. Not surfaced as a question; just applied because
  it removes a manual config step.

**Smoke tests (local only — live deploy not yet verified)**

Dev settings still load cleanly:
```
.venv/bin/python manage.py check
System check identified no issues (0 silenced).
```

Prod settings load cleanly when required env vars are stubbed:
```
SECRET_KEY=stub-secret \
  ALLOWED_HOSTS=test.local \
  DATABASE_URL='postgres://u:p@host:5432/db' \
  RESEND_API_KEY=stub-key \
  DJANGO_SETTINGS_MODULE=config.settings.prod \
  .venv/bin/python manage.py check
System check identified no issues (0 silenced).
```

`bootstrap_superuser` command lifecycle:
```
=== command discovery ===
manage.py help bootstrap_superuser → "Create a superuser from env vars
                                       if one doesn't exist (idempotent)."

=== no env vars ===
"DJANGO_SUPERUSER_EMAIL/PASSWORD not set; skipping."

=== first run with env vars ===
"Created superuser phase3-test@example.com."

=== second run with same env vars (idempotency) ===
"Superuser phase3-test@example.com already exists; skipping."
```

`make lint` clean. `black --check apps config manage.py` reports
`32 files would be left unchanged`.

**Live smoke tests — all green (2026-06-25, reported by Steven as
"completed with flying colors")**
- `/admin/` login with the bootstrap superuser ✓
- Sign-up → land on My Groups ✓
- Create a group → see join code ✓
- Second account joins via code ✓
- Password reset → real email delivered to a Resend-verified address ✓
- 15-minute idle cold-start wake-up test ✓

Pre-deploy hiccup (already documented in
[[feedback-clarifying-questions]]): `sync: false` env vars in
`render.yaml` did NOT auto-prompt in the Render dashboard because the
Blueprint already existed. Steven added `DJANGO_SUPERUSER_EMAIL` /
`DJANGO_SUPERUSER_PASSWORD` manually in the Environment tab, which
triggered a redeploy; the build then ran `bootstrap_superuser` and
printed `Created superuser <email>.`. Idempotent design held — no risk
of re-creating on subsequent deploys.

**Deviations from `initial-architecture.md`**
- **Plan had Render deploy as Phase 5; it ran as Phase 3.** Already
  documented in the 2026-06-24 plan revision note.
- **Plan said "Database migration, create superuser, smoke test."** The
  `create superuser` step assumed shell access. Reality (Render free
  tier has no shell): pivoted to `bootstrap_superuser` env-driven
  command + bake into `buildCommand`. This is a meaningful enough
  change that the plan file should arguably be updated; for now the
  deviation is captured here.
- **`render.yaml` adds a couple of things the plan didn't explicitly
  call out**: the four `sync: false` env vars (Resend key, two
  superuser env vars), the explicit `PYTHON_VERSION`, and the
  `seed_bracket` invocation in `buildCommand` (so a fresh deploy comes
  up with the 32 matches already wired).

**Pending / deferred (NOT blockers for Phase 3 sign-off, but worth
remembering)**
- **Resend verified domain.** Steven explicitly chose to defer this
  decision. Sandbox restricts password-reset deliverability to verified
  test recipients. Flipping later is one env var + DNS work; no code
  change.
- **Custom app domain** (e.g. `bracket.something.com` instead of
  `wc26-bracket.onrender.com`). Trivial later: Render dashboard add +
  one DNS record + extend `ALLOWED_HOSTS`. No code change.
- **Full team data** still only 3 host-nation placeholders. Steven will
  populate `TEAMS` in `seed_teams.py` after the group stage finishes
  (~2026-06-27); seed_teams is not in `buildCommand` yet, so re-seeding
  teams in prod will require either committing the updated TEAMS list
  (triggering a redeploy that runs `seed_teams` if we add it) or
  running it via local-against-remote-DB workaround (see below).
- **ScoringRule data.** Still no rows. Will be hand-added via `/admin/`
  on the live URL, or via a future `seed_scoring_rules` command.
- **Local-against-remote-DB workflow** documented in the chat history
  for the "I need to run a one-off mgmt command and Render has no
  shell" scenario: copy External Database URL from Render dashboard,
  set as `DATABASE_URL` env var locally alongside stubbed `SECRET_KEY`
  / `ALLOWED_HOSTS` / `RESEND_API_KEY`, run `manage.py <cmd>`. Goes
  over SSL public internet; fine for occasional ops.

**Dependencies introduced** (per dep-approval contract — all pinned to
exact versions)

Approved up-front:
| Package | Pin | Purpose |
|---|---|---|
| `psycopg` | 3.3.4 | Postgres driver (psycopg 3) |
| `psycopg-binary` | 3.3.4 | Bundled with `psycopg[binary]` extra; no system libpq needed |
| `gunicorn` | 26.0.0 | Production WSGI server |
| `whitenoise` | 6.12.0 | Static file serving |
| `dj-database-url` | 3.1.2 | Parses Render's `DATABASE_URL` env var |
| `django-anymail` | 15.0 | Email backend for Resend (base, no `[resend]` extra) |

Also added to `requirements.txt`:
| Package | Pin | Note |
|---|---|---|
| `resend` | 2.32.2 | Official Resend Python SDK. Not used by `django-anymail`'s base Resend backend (that backend just makes HTTP calls via the existing `requests` lib). Available in the env for future direct use. |

`pip check` clean after install.

**Untouched (per working contract)**
- `.env` — never read, edited, or inspected.
- The Resend API key, superuser email, and superuser password — given to
  Steven by name only (env var keys), values handled entirely on his side.

---

## Phase 4 — Predictions UI ✅ 2026-06-25 (commit `334e398`)

**Scope shipped**

End-to-end one-shot bracket UI. A user opens a group's bracket page, fills
in winner picks for all 32 matches (later rounds derive their teams from
the user's earlier picks), and hits **Save Predictions** to lock in their
bracket. They can hit **Change Predictions** any time before the global
lock to revise. As matches resolve (admin sets `Match.winner`), their
picked teams highlight green (correct) or red (incorrect). Group-mates'
brackets become visible after the global lock fires.

This phase included a significant **mid-conversation design pivot** from
the original architecture plan's per-match dynamic picking (each match
locks 1h before its kickoff) to a **one-shot bracket** model (single
global lock 5 minutes before R32-1 kickoff). Pivot was Steven's call mid-
implementation discussion; the architecture plan was updated in the same
commit to reflect the new design (Phase 4 section rewritten in
`initial-architecture.md`).

**Files added**

*Python:*
- `apps/bracket/services.py` (235 lines). Pure functions over the bracket
  state, no models added:
  - `tournament_lock_time()` / `is_tournament_locked()` are actually in
    `models.py` (alongside `TOURNAMENT_LOCK_WINDOW = timedelta(minutes=5)`
    and `TOURNAMENT_LOCK_REFERENCE_SLOT = "R32-1"`) since `Prediction.clean()`
    needs them at model layer.
  - `build_user_bracket(user, group)` returns a per-round structure with
    each match enriched with: actual or derived `home`/`away` teams, the
    user's pick, `has_teams` / `pickable` flags, and a `scoring` state
    (`"correct"` / `"incorrect"` / `"neutral"`). Top-level metadata
    includes `lock_time`, `is_locked`, `submitted`, `submitted_at`,
    `pick_count`, `complete`, `editable_phase`.
  - `build_group_bracket(group)` aggregates all members' picks per match
    for the post-lock group view. Returns `picks: []` (empty) pre-lock so
    in-progress picks stay hidden (per design decision).
  - `reconcile_user_picks(user, group)` walks the bracket top-down and
    deletes any `Prediction` whose `picked_winner` is no longer in its
    match's derived teams. Called after every pick save. Cascades
    naturally because deletions in early rounds invalidate downstream
    derivations on subsequent iterations. R32 picks are never auto-
    reconciled (R32 teams are admin-set, not user-derived).
  - Helper `_slot_sort_key()` parses the numeric suffix of slot strings
    ("R32-2" → 2) so per-round ordering is `1, 2, 3, …, 16` instead of
    lexicographic `1, 10, 11, …, 2`.

*Templates:*
- `templates/bracket/bracket_view.html` — full page. Header with group
  name, join code, countdown clock (pre-lock) or "Bracket locked" badge
  + view toggle (post-lock). Includes either `_user_bracket.html` (My
  Picks) or `_group_bracket.html` (Group Picks) based on `?view=` GET
  param. Trailing inline `<script>` runs the countdown JS; tears down
  the interval and reloads on lock expiry.
- `templates/bracket/_user_bracket.html` — the HTMX swap target. Contains
  the actions panel (pick count + Save/Change button) and the bracket
  grid. Each Save/Change form `hx-post`s back to this same target.
- `templates/bracket/_match_card.html` — single match card. Branches on
  three states:
  1. `has_teams`: render `<form>` with two team buttons, each `hx-post`ing
     to `match_pick` with the team id. Picked button gets `.picked` class;
     scoring state on the parent card via `data-scoring` attr.
  2. Partial (one source picked, other still pending): renders both slots
     read-only, the known one with `.team-readonly.known` styling, the
     unknown with `<em>waiting…</em>` placeholder. Communicates progress
     without misleading "TBD".
  3. Neither: just "TBD".
- `templates/bracket/_group_bracket.html` — read-only grid for the group
  view. Each match shows actual home/away teams plus a list of all
  members' picks, color-coded against `Match.winner`.

*Infra (additions only to existing files):*
- `apps/bracket/migrations/0002_groupmembership_bracket_submitted_and_more.py`
  (auto-generated). Adds the two submission-tracking fields. Reformatted
  by `black` after generation.

**Files modified**

- `apps/bracket/models.py`:
  - Added `TOURNAMENT_LOCK_WINDOW = timedelta(minutes=5)`,
    `TOURNAMENT_LOCK_REFERENCE_SLOT = "R32-1"`, module-level
    `tournament_lock_time()` and `is_tournament_locked()` helpers.
  - Removed `Match.LOCK_WINDOW` and `Match.is_locked()` (no longer used;
    grep-confirmed only Phase 1's seed_bracket comment and the
    Prediction.clean call referenced them).
  - Added `GroupMembership.bracket_submitted` (BooleanField, default
    False) and `bracket_submitted_at` (DateTimeField, nullable).
  - Rewrote `Prediction.clean()` to check global lock instead of per-
    match lock. Error message updated accordingly.
- `apps/bracket/views.py` extended with five view functions:
  - `bracket_view(group_id)` — full page render. Pre-lock + `?view=group`
    redirects back to the my-view (group picks are hidden until lock).
  - `match_pick(group_id, match_id)` — HTMX POST endpoint. Validates
    membership, validates not locked + not submitted, validates the team
    is in the match's derived teams, then `update_or_create`s the
    Prediction and calls `reconcile_user_picks`. Returns the full
    `_user_bracket.html` fragment for HTMX swap.
  - `submit_bracket(group_id)` — HTMX POST. Flips the submitted flag if
    the bracket is complete; rejects with 400 otherwise.
  - `unsubmit_bracket(group_id)` — HTMX POST. Flips the flag back.
  - All three HTMX endpoints share `_render_user_bracket_swap()` helper.
- `apps/bracket/urls.py` — four new routes:
  `/groups/<int:group_id>/bracket/`,
  `/groups/<int:group_id>/bracket/match/<int:match_id>/pick/`,
  `/groups/<int:group_id>/bracket/submit/`,
  `/groups/<int:group_id>/bracket/unsubmit/`.
- `config/settings/base.py` — `"django_htmx"` added to `INSTALLED_APPS`,
  `"django_htmx.middleware.HtmxMiddleware"` to `MIDDLEWARE`.
- `templates/base.html` — htmx 2.0.7 script tag (Cloudflare CDN, `defer`)
  in `<head>`; `hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'` on
  `<body>` so all HTMX POSTs carry CSRF without per-form `{% csrf_token %}`
  tags. Added `{% block body_class %}` so the bracket page can override
  body styling (needs a wider max-width than the 720px default).
- `templates/bracket/my_groups.html` — "Open bracket →" link per group.
- `apps/bracket/management/commands/seed_bracket.py` — comment updated
  to reference the new global lock semantics (the placeholder kickoff is
  why the lock never fires until R32-1's real kickoff is set).
- `static/css/style.css` — ~250 lines added for the bracket page.
- `requirements.txt` — `django-htmx==1.27.0` added.

**Design decisions (Steven approved up-front)**

The Phase 4 design was re-negotiated several times mid-discussion. Final
locked-in decisions, in chronological order of resolution:

1. **Bracket layout**: traditional bracket tree on desktop (left-to-right,
   single-sided, R32 → FINAL); vertical round-sections on mobile
   (<768px). Same HTML, CSS media query handles the transformation. I
   originally proposed round-by-round sections everywhere and called the
   tree "expensive" — Steven pushed back, I recanted the framing, and we
   ended at the responsive combo.
2. **Pick derivation**: dependent rounds (R16/QF/SF/FINAL) derive
   matchups from the user's prior-round winner picks. THIRD derives from
   SF *loser* picks (the SF team the user did NOT pick). Source picks
   become invalid if changed → see cascade decision below.
3. **Group view visibility**: hidden pre-lock. Toggle "My Picks" / "Group
   Picks" only meaningful post-lock; group view returns to my-view if
   accessed pre-lock.
4. **Late joiners**: can join + view post-lock but cannot enter picks.
   No new schema state needed — they simply have 0 Predictions and the
   Save/Change buttons never appear because the global lock has fired.
5. **HTMX delivery**: `htmx.min.js` from Cloudflare CDN + `django-htmx`
   middleware (chosen for `request.htmx` truthy/falsy access, even though
   the views don't actually need to branch on it yet — kept the
   middleware wired anyway for future fragment-vs-page logic).
6. **Pivot to one-shot bracket** (decision 6, mid-discussion): instead of
   per-match dynamic picking, user fills the whole bracket once,
   single global lock = `R32-1.kickoff_at - 5 minutes`. Eliminates the
   chain-divergence UX problem and matches how small private bracket
   pools normally work.
7. **Save / Change UX**: per-pick auto-save under the hood (each click
   writes a Prediction immediately) + a per-membership `bracket_submitted`
   flag that gates editing. Save button enabled only when all 32 picks
   are made; clicking flips the flag (read-only state, Change button
   appears). Late-bracket-with-no-Save-clicked still counts at lock —
   submitted flag is purely about editability, not commit intent.
8. **Partial-state rendering** (added during browser test): when only
   one source pick of a dependent match exists, the card shows the known
   team with the other slot reading "waiting…". Was raised after Steven
   tested R16-1 with only R32-1 picked and saw a misleading "TBD".

**Implementation notes (judgment calls inside the agreed scope)**

- **Cascade-clear of orphaned downstream picks** (not explicitly
  approved, flagged at handoff and accepted): when a user changes an
  earlier-round pick that invalidates a downstream pick's options, the
  downstream Prediction is auto-deleted. E.g., picked USA in R32-1,
  picked USA in R16-1, then change R32-1 to MEX → R16-1 derived teams
  become (MEX, ?), USA is no longer in the match → R16-1 prediction
  deleted. Save Predictions becomes disabled again until refilled. The
  alternative (leave orphans, surface a warning) was rejected as
  needlessly fiddly. Implemented in `reconcile_user_picks`, called from
  `match_pick` after every save.
- **One Prediction is the source of truth, even with the submitted
  flag**: deliberate. Submitted is a UX gate, not a commit checkpoint.
  This means there's no "snapshot at Save time" — if you Save, then
  Change, then never re-Save before lock, your latest auto-saved picks
  count. Steven explicitly chose this forgiving model.
- **HTMX swap target is the whole `#bracket-grid`** (the actions panel
  + 32-card grid), not just the single card that was clicked. Reason:
  cascade-clears can affect multiple cards downstream, and the Save
  button's enabled state can flip on any pick. Full-grid swap is the
  one swap pattern that covers every change. Response is ~10KB per pick;
  acceptable for the pool size.
- **Countdown clock is inline `<script>` in `bracket_view.html`**, not a
  separate JS file. ~20 lines. Tears down on lock expiry and reloads
  the page so the locked state renders.
- **HTMX version pin (htmx 2.0.7)**: pinned in the script src URL, not
  via a pip dep. Lives entirely in the template. Approved during browser-
  test phase; verified on cdnjs first.
- **No `request.htmx` branching in views yet.** Every HTMX endpoint
  returns the fragment unconditionally. Plain-browser fallback (curl,
  non-HTMX client) gets fragment HTML, which is degraded but not broken.
  The middleware is wired anyway so future endpoints can branch.

**Smoke tests**

*Shell tests via Django test client (10 assertions, all green):*
- GET bracket page → 200, page renders with countdown
- POST `match_pick` for R32-1 with USA → 200, Prediction saved
- POST `match_pick` for R32-2 with CAN → 200, Prediction saved
- `build_user_bracket(u1, g)` returns R16-1 with derived home=USA,
  away=CAN, pickable=True ← derivation works
- POST `match_pick` for derived R16-1 with USA → 200
- POST `match_pick` for R32-1 with MEX → 200, AND R16-1 prediction is
  None after the call ← cascade works
- POST `submit_bracket` with incomplete bracket → 400
- GET bracket with `?view=group` pre-lock → 302 redirect ← visibility
  gate works
- Set Match.winner=MEX (user's pick), build bracket → R32-1 scoring is
  `"correct"`. Flip to USA → scoring is `"incorrect"`.
- Force lock by setting R32-1.kickoff_at to past → `is_tournament_locked()`
  is True. POST `match_pick` → 400. GET bracket → 200 (renders locked
  state, "Bracket locked" in body). GET `?view=group` → 200 (now allowed).

*Browser tests (Steven, on local dev at `:8765`):*
- Bracket page renders with countdown ticking, R32-1 / R32-2 picks
  visible and clickable.
- Pick USA in R32-1 → highlights blue, Save button stays disabled
  ("1 of 32 picks made"), R16-1 shows partial state "🇺🇸 USA / waiting…".
- Pick CAN in R32-2 → R16-1 transitions to full pickable state with
  USA vs CAN team buttons.
- Cascade verified: change R32-1 to MEX → R16-1 USA pick disappears.
- Bracket-tree spatial alignment verified after CSS fix (see below):
  R32-1 / R32-2 visually flow into R16-1, same down the column.
- Steven additionally tested by manually setting `Match.winner` for
  R32-1 and R32-2 in `manage.py shell` and visually confirmed the
  green / red highlight on his picked teams renders correctly.

**Two bugs caught in browser test, both fixed before commit**

1. **R32 cards rendered in lexicographic order** (1, 10, 11, …, 16, 2,
   3, …, 9). Sort key was `m.slot` (a string). Fixed by adding
   `_slot_sort_key()` that parses the numeric suffix; both
   `build_user_bracket` and `build_group_bracket` now use it.
2. **Cards visually clipped to ~70px**, hiding the bottom team button.
   Root cause: `height: 70px` on `.match-card` was less than the
   content (meta + two ~26px buttons = ~92px). `overflow: hidden`
   meant the second button was sliced off. Fixed by bumping
   `.match-card { height: 100px }` and `.bracket-rounds { min-height:
   1680px }` (16 R32 cards × 100px + breathing room) so the bracket-
   tree alignment math still works.

**Deviations from `initial-architecture.md`**

The plan was actively updated in the same commit. The old per-match
dynamic-picking text was replaced with the one-shot bracket spec; the
revision note in the plan documents the pivot rationale and date.
Other than the pivot itself, no deviations.

**Pending / deferred (NOT blockers for Phase 4 sign-off)**

- **Auto-advancement when admin sets Match.winner** — when a winner is
  set on R32-X, the winning team should auto-populate
  `R16-(X/2).home_team` or `.away_team` per the `feeds_into`/`feeds_as`
  wiring. Still deferred to Phase 5 (alongside scoring). Workaround for
  now: Steven manually sets home/away on dependent matches via admin
  as results come in.
- **Leaderboard + scoring page** — Phase 5. Per-user point totals
  computed from `Prediction.picked_winner == Match.winner` joined with
  `ScoringRule`.
- **Bracket lock cron / wake-up** — when LOCK_TIME passes, the page
  needs to re-render in locked state. Currently handled by the
  countdown JS doing `location.reload()` on expiry, which works only
  for users with the page open. Acceptable for v1 (the lock state is
  computed fresh on every GET regardless), but worth noting.
- **Pickable validation has a subtle UX gap on team change**: if user
  picks USA in R32-1, then clicks MEX in R32-1, the POST is just an
  `update_or_create` on Prediction so MEX replaces USA cleanly. But the
  Reconcile step runs after, which cascades downstream if needed.
  Tested OK in smoke test; flagging in case there's a corner case I
  missed.
- **No formal tests yet** — still using shell-based smoke tests via
  `Client`. Phase 5 will introduce real `TestCase` coverage (lock-time
  enforcement, scoring math, cascade reconciliation).
- **R32 still has only 3 host nations seeded** (USA, MEX, CAN). Full
  knockout team data lands ~2026-06-27 after group stage finishes.
  Until then, the bracket is mostly TBD placeholders — useful only for
  developer testing.
- **Pre-pick validation accepts any Team object** that's in the match's
  current derived teams. If admin changes Match.home_team after a user
  has already picked the (now-changed) team, that pick survives. Edge
  case; would be handled by a reconcile-on-admin-edit if we cared.
- **Group view picks display** uses `email|truncatechars:24`. No
  username/display-name field on User. Acceptable for a friend pool;
  revisit if anonymity is desired.

**Dependencies introduced** (per dep-approval contract — all pinned to
exact versions)

| Package | Pin | Purpose | Transitives |
|---|---|---|---|
| `django-htmx` | 1.27.0 | Middleware exposing `request.htmx`; required for future fragment-vs-page response branching | None new — only `asgiref>=3.6` and `django>=4.2`, both already in lockfile |

`pip check` clean after install.

Also (not a Python dep, but in the dependency story): htmx 2.0.7 from
the cdnjs CDN. Pinned in `templates/base.html` `<script src>` URL.

**Untouched (per working contract)**
- `.env` — never read, edited, or inspected.

---

## Phase 5 — Leaderboard + scoring + auto-advancement ✅ 2026-06-25

**Scope shipped**

Per-round scoring values are seeded; admin-set `Match.winner` auto-advances
the winner into the next match's `home_team`/`away_team` slot (and the
*loser* of an SF into THIRD); per-group leaderboard renders on demand with
positional tied ranks; user brackets stay strictly insulated from canonical
advancement. Phase 5 was scoped, designed, and shipped in a single evening
session; all five planned steps are complete with shell-level smoke tests
passing. Steven's browser verification happens out of band.

**Files added**
- `apps/bracket/management/commands/seed_scoring_rules.py` — idempotent
  upsert of the 6 `ScoringRule` rows (R32=1, R16=2, QF=4, SF=8, THIRD=10,
  FINAL=15). Uses `get_or_create` (not `update_or_create`) intentionally
  so admin-tweaked point values are preserved across re-runs. Verified by
  setting R32=99 in shell, re-running the command, and confirming the 99
  stuck.
- `templates/bracket/leaderboard.html` — table view: rank, player (full
  name or email fallback), total points, per-round `correct/total` cells.
  Highlights the requesting user's row (`tr.you` → soft amber bg + `you`
  tag chip). Members who haven't hit Submit Predictions get a `draft`
  chip next to their name (purely visual — picks count regardless per
  Phase 4's forgiving model).

**Files modified**
- `apps/bracket/models.py`:
  - `Match.save()` override: reads previous `winner_id` from DB before
    `super().save()`, runs `_advance_winner(self)` post-save if it
    changed. The previous-value snapshot is via `.values_list(...).first()`
    (one column, one row) so it stays cheap even though every Match save
    pays for it.
  - `_advance_winner(match)` module-level helper: handles two cascade
    paths. (a) `feeds_into` push — sets downstream match's `home_team`
    or `away_team` based on this match's `feeds_as`; clearing a winner
    clears the downstream slot; swapping a winner overwrites it. (b)
    SF → THIRD loser push — when an SF winner is set, the *other* team
    in that SF gets pushed to `THIRD.home_team` (SF-1) or
    `THIRD.away_team` (SF-2). Idempotency guard: only writes the
    downstream save if the current value differs from the target, so
    repeated saves don't churn.
  - `_determine_sf_loser(sf_match)` module-level helper: returns the
    team in the SF that isn't the winner; gracefully `None` if any of
    (winner, home, away) is unset or the winner isn't one of the two
    sides (defensive against admin-set inconsistencies).
- `apps/bracket/services.py`:
  - **Important behavioral fix**: rewrote `_derived_teams` to be strict
    per-round. R32 → canonical `match.home_team`/`away_team`
    (admin-seeded); THIRD → SF losers from this user's SF picks;
    everything else → pure derivation from this user's source-round
    picks. The previous implementation had an early-return
    `if home and away: return home, away` that would silently fall
    through to canonical teams once auto-advancement filled them in.
    Once that happened, `reconcile_user_picks` would then delete the
    user's downstream `Prediction` rows because their `picked_winner`
    wasn't in the new derived pair — silent data loss for any user
    whose pick diverged from canonical reality. The fix predates the
    auto-advancement code by intent (called out during design Q&A,
    implemented alongside the bug it would have triggered).
  - `compute_group_standings(group)` new public service. Single query
    `Prediction.objects.filter(group=group, picked_winner=F('match__winner'))`
    pulls all correct picks for the group; in-memory aggregation by
    user_id with per-round counts; multiplies by `ScoringRule.points`
    for total. Then `GroupMembership` outer-pass adds zero-point
    entries for members who haven't picked at all (so leaderboard
    never silently omits a player). Sort key
    `(-total_points, user.email.lower())` — points desc, email asc as
    tiebreaker.
- `apps/bracket/views.py`:
  - `ROUND_TOTALS` module-level constant: `{R32:16, R16:8, QF:4, SF:2,
    THIRD:1, FINAL:1}`. Used by the leaderboard view to render the
    "correct / total" denominator. Stays in sync with `seed_bracket`
    SLOTS but neither is enforced — drift would only show wrong
    denominators on the leaderboard, not break scoring.
  - `leaderboard_view(request, group_id)` — `@login_required`, membership
    check via existing `_get_membership_or_404`. Computes positional
    tied rank (e.g. tied players share rank, next rank skips) by
    walking the sorted standings. Flattens `per_round` dict into a
    `round_cells` list aligned with `round_columns` so the template
    can iterate without needing a `get_item` custom filter.
- `apps/bracket/urls.py` — added one route:
  `groups/<int:group_id>/leaderboard/` → `name="leaderboard_view"`.
- `templates/bracket/bracket_view.html` — added Leaderboard link in the
  group-meta nav line alongside "Back to groups".
- `templates/bracket/my_groups.html` — added a second `bracket-link`
  per group row pointing at the leaderboard.
- `static/css/style.css` — appended ~50 lines for `table.leaderboard`
  (zebra-free, light grey header, monospace numeric cells, soft amber
  highlight for `tr.you`, pill-shaped `you-tag` / `not-submitted-tag`
  chips).
- `render.yaml` — `seed_scoring_rules` added to `buildCommand` after
  `seed_bracket`. On next prod deploy the 6 ScoringRule rows get
  created once and left alone forever. (Idempotent re-runs.)

**Design decisions** (more nuance in the session conversation logs)

1. **User bracket vs canonical bracket are strictly independent.**
   Steven called this out during design Q&A: setting `Match.winner` in
   admin must only update the canonical bracket. A user's bracket
   visualization (which teams display in each round) is frozen on
   their own predicted future from the moment of lock. Auto-advancement
   only mutates `Match` rows; never `Prediction` rows. The
   `_derived_teams` fix above is the structural enforcement of this
   invariant on the read side; the absence of any reconcile call in
   `Match.save()` is the structural enforcement on the write side.
2. **Scoring is correct/incorrect, nothing else.** A user's picked
   team is compared against `Match.winner` as a simple equality check.
   If the user's picked team isn't even *in* the canonical matchup
   (because their R32 picks diverged enough that their fantasy R16-1
   matchup has zero overlap with canonical R16-1), they still just
   get red + 0 points on that pick. The bracket card still visually
   shows their two derived teams — they only lose the chance to score,
   never the bracket structure itself. Steven explicitly confirmed
   this is the intended behavior.
3. **Compute scoring on the fly; no materialized table.** The
   tournament is 32 matches with a tiny pool. A `Standing` model
   would just create cache-invalidation work for ~no perf gain. Every
   leaderboard GET re-queries Predictions and aggregates. "Updates
   when admin sets a winner" = the next GET reflects it. No polling,
   no background jobs.
4. **ScoringRule seeding uses `get_or_create`, not `update_or_create`.**
   Steven said point values are admin-editable. If an admin changes
   R16 to 3 in the dashboard, re-deploying the app shouldn't reset it
   to 2. Different semantics from `seed_teams` (which uses
   `update_or_create` because team rosters *should* drift back to
   canonical).
5. **Positional tied rank, not dense rank.** Tied players share rank,
   next rank skips. Standard sports convention. Steven explicitly
   said ties are fine post-final ("not that serious for the friends
   using this") so no tiebreaker beyond email-alphabetical.
6. **Per-round columns show `correct/total`, not points.** "Correct
   counts tell you how well you actually predicted; points are
   computable from the rules." Template gets `round_cells: [{label,
   correct, total}, ...]` rather than a dict, so iteration is direct
   and no custom template filter is needed.
7. **Leaderboard pre-lock = (b) "render empty leaderboard"** (out of
   the three options Steven was offered). Shows all members at 0/0/0
   with a "Picks are still open" header note. Lets people verify the
   page renders before kickoff and see who's in the group. Falls out
   naturally because `compute_group_standings` already returns all
   memberships, and pre-lock there's just no `Match.winner` set so
   every per-round count is 0.
8. **SF → THIRD loser cascade lives in `Match.save()` not as a
   one-shot manual fill.** Originally `seed_bracket`'s comment said
   admin should manually set THIRD.home_team / away_team after the
   SFs were played. Auto-advancement handles it now — both SF winner
   set/cleared/swapped scenarios push the loser (or clear the slot)
   onto THIRD correctly. Comment in `seed_bracket.py` was NOT
   updated — minor doc-drift; the wiring still skips THIRD
   intentionally in `WIRING`, which is correct (it's not a normal
   feeds_into; it's the loser-side cascade in `_advance_winner`).

**Implementation notes / non-obvious bits**

- `Match.save()` snapshot of previous winner uses
  `Match.objects.filter(pk=self.pk).values_list('winner_id',
  flat=True).first()` rather than `Match.objects.get(pk=self.pk)`. One
  column, one row, no model instantiation — cheaper than the full
  fetch, and the only thing we need is the FK id to compare.
- Downstream save in `_advance_winner` uses `update_fields=[field]` so
  it only touches the one column. This also avoids recursion concerns:
  the downstream save is a non-winner-changing save, so its own
  `Match.save()` override no-ops the advancement check (old_winner_id
  == new_winner_id).
- `_advance_winner` writes both cascade paths (`feeds_into` push AND
  SF→THIRD loser push) in the same call. Only one is relevant per
  match (SF matches have a `feeds_into` of FINAL *and* SF→THIRD
  trigger; R32 matches have only `feeds_into`). The SF case fires
  both correctly: SF-1 winner → FINAL.home AND SF-1 loser → THIRD.home.
- `compute_group_standings` does NOT use `.annotate()` with a
  `Sum`/`Count` ORM-side aggregation. The natural query
  (`Prediction × Match.winner × ScoringRule.points`) involves a
  multi-table join with a conditional that's awkward to express
  cleanly in the ORM. The in-memory pass over filtered `Prediction`
  rows is the same cost (32 matches × N members = at most a few
  hundred rows) and reads more naturally.
- Leaderboard table renders `s.user.get_full_name|default:s.user.email`.
  `get_full_name()` returns an empty string when first_name/last_name
  are both blank — relies on Django's truthy-default behavior. For
  the current testing accounts (no names set) it falls through to
  email correctly.
- The `not-submitted-tag` chip shows for any standings row where
  `bracket_submitted == False`. This is intentionally informational —
  not a penalty. Per Phase 4's forgiving lock model, every Prediction
  row in the DB at lock time counts whether the user clicked
  Submit Predictions or not.

**Group view scoring was already wired in Phase 4** (originally
planned as Step 5; turned out to be a no-op)

The original Phase 5 plan listed "extend `build_group_bracket` to mark
each pick correct/incorrect" as a separate step. On re-reading
`templates/bracket/_group_bracket.html`, the template was already
doing the comparison inline using `entry.winner.id == pick.team.id` /
`entry.winner.id == entry.home.id` etc., against the `picks` list
already populated by `build_group_bracket`. The CSS classes
(`.pick-correct`, `.pick-incorrect`, `.team-winner`) were also already
defined in Phase 4. Smoke test confirmed all three classes render
correctly in the group view once `Match.winner` is set. Decision: no
code change. The template-inline comparison is slightly less
consistent than the service-layer `_scoring_state` pattern used by
`build_user_bracket`, but per the working contract refactoring for
consistency-without-functional-improvement was skipped.

**Smoke tests run (all shell-based via Django Client / ORM)**

1. `seed_scoring_rules` first run created 6 rows; second run created
   0 rows (idempotent).
2. Admin-edit preservation: set R32 points to 99 in shell, re-ran
   command, value stuck.
3. Auto-advance — `R32-1.winner = MEX` → `R16-1.home = MEX`
   (canonical). Sarah's R16-1 Prediction (USA) stayed in DB; her
   bracket-view display still showed USA, not MEX.
4. Auto-advance — `R32-2.winner = BRA` → `R16-1.away = BRA`.
   Canonical R16-1 now MEX v BRA.
5. Clear winner — `R32-1.winner = None` → `R16-1.home = None`.
6. Swap winner — `R32-1.winner = USA` → `R16-1.home = USA`.
7. SF→THIRD loser cascade — `SF-1.winner = USA` (vs MEX) →
   `THIRD.home = MEX` (loser) AND `FINAL.home = USA` (winner via
   feeds_into).
8. SF-2 cascade — `SF-2.winner = BRA` (vs CAN) → `THIRD.away = CAN`,
   `FINAL.away = BRA`.
9. SF winner correction — `SF-1.winner: USA → MEX` → `THIRD.home`
   updates from MEX to USA (new loser), `FINAL.home` updates from
   USA to MEX (new winner).
10. `compute_group_standings` with 3 test users (Sarah 3pts: R32-1
    USA correct + R16-1 USA correct; Alice 1pt: R32-2 BRA correct;
    Bob 0pts: no picks) → sorted (Sarah, Alice, Bob) with all three
    present.
11. Leaderboard view at `/groups/4/leaderboard/` returns 200, renders
    all 3 user rows, correct ranks (1/2/3), correct points (3/1/0),
    `you` tag on Sarah's row, R32 column shows correct counts, all
    other rounds show 0.
12. Pre-lock leaderboard on Steven's own single-member group returns
    200, shows "Picks are still open" header, Steven row with 0
    points across the board.
13. Nav links wired — bracket_view page contains
    `/groups/{id}/leaderboard/`, my_groups page contains same.
14. Post-lock group view — set R32-1 kickoff to past so
    `is_tournament_locked()` returns True, hit
    `/groups/4/bracket/?view=group`, rendered HTML contains all of
    `pick-correct`, `pick-incorrect`, `team-winner` classes.

**Pending / deferred (NOT blockers for Phase 5 sign-off)**

- **`seed_teams` still not wired into `render.yaml` buildCommand.**
  Steven explicitly deferred — the TEAMS list in `seed_teams.py` is
  still the 3-host-nation placeholder. Wiring it now would create the
  3 placeholder rows in prod on every deploy. Plan: populate the full
  32-team list locally after group stage finishes (~2026-06-27), then
  add `python manage.py seed_teams` to `render.yaml` buildCommand and
  redeploy.
- **R32 draw teams and kickoff times** — Steven will hand-enter via
  admin after the FIFA draw is published (~2026-06-27). Phase 6 work.
- **No formal `TestCase` coverage yet.** Phase 6 buffer day will add:
  lock-time enforcement, scoring math edge cases, auto-advancement
  cascade, `_derived_teams` user-bracket isolation, cascade
  reconciliation on user pick change.
- **`seed_bracket.py` comment about manually setting THIRD home/away
  is now stale** (auto-advancement handles it). Minor doc-drift,
  worth cleaning up in Phase 6 alongside other doc passes.
- **Admin "set winner" UX is unimproved** — uses the default Django
  admin form. Steven explicitly didn't want this in Phase 5 scope. If
  fat-fingering becomes an issue during the tournament, a custom
  admin action ("set winner with confirmation") could be added.
- **No notifications on winner set / leaderboard change.** Out of
  scope per Phase 5 conversation. The intended user behavior is "log
  in periodically to check the leaderboard"; the page reflects
  current state on every load.
- **`bracket_view` for the group view redirects to "mine" pre-lock**
  (Phase 4 behavior, unchanged). This is still correct — pre-lock
  there are no other-members' picks to show, by design.
- **Submission-status `draft` chip on leaderboard could be confusing**
  in the friend pool if someone reads it as "their picks won't
  count". Mitigated by the existing `title=` tooltip explanation;
  could be revisited if users actually ask.

**Deviations from `initial-architecture.md`**

- Plan said Phase 5 would include "HTMX polling every ~30s during
  match windows, or a manual refresh button". Steven explicitly chose
  neither — leaderboard recomputes on demand each GET, no polling, no
  refresh affordance needed.
- Plan didn't anticipate the `_derived_teams` isolation bug. The fix
  was identified during design Q&A when Steven asked the clarifying
  question about whether admin-set winners would change users'
  bracket displays (they shouldn't, but with the old `_derived_teams`
  they would have once auto-advancement filled `match.home_team`).
  Caught before any user-visible damage because Phase 4 had not yet
  had any actual winners set in prod.
- Plan listed Phase 5 step "extend build_group_bracket to tag
  scoring" — turned out to already be wired at template level in
  Phase 4. No code change for Step 5.

**Dependencies introduced**

None. All Phase 5 work is on existing Django ORM, existing services
module, existing templates.

**Linter / formatting note**

After the bulk of Phase 5 was written, Steven's editor's linter
reformatted `apps/bracket/views.py` (multi-line imports, expanded
dict-comprehension formatting in `leaderboard_view`). Pure cosmetic,
no logic changes; intentional per Steven's note.

**Untouched (per working contract)**
- `.env` — never read, edited, or inspected.

---

## Username display pass ✅ 2026-06-25

Small follow-up to Phase 5 before Phase 6 hardening. Steven flagged that
email-only player labels on the leaderboard "feel lame". The User model
had `username = None` since Phase 0 (we'd standardized on
email-as-USERNAME_FIELD); this pass restores a `username` `CharField`,
makes it mandatory on signup, and routes it to every place the UI used
to render email-as-display-name.

**Scope shipped**
- `User.username` is now a `CharField(max_length=100, unique=True,
  validators=[UnicodeUsernameValidator()])`, mandatory at signup, shown
  on the leaderboard, in the header nav, and on group-view pick rows.
- `email` remains the `USERNAME_FIELD` (i.e. the credential users
  log in with); `username` is purely the display label.
- Existing users (4 in dev, 1 in prod) get a backfilled username from
  the local-part of their email via a single in-migration `RunPython`
  step.

**Files added**
- `apps/accounts/migrations/0002_user_username.py` — 3-operation
  migration: AddField nullable + unique → RunPython backfill →
  AlterField NOT NULL + validator. Splitting into three ops is
  necessary because (a) `unique=True` + a single default would break
  the constraint, and (b) `AlterField` to NOT NULL on a populated
  table fails without a prior backfill.

**Files modified**
- `apps/accounts/models.py`:
  - `username = CharField(max_length=100, unique=True,
    validators=[UnicodeUsernameValidator()], help_text=…)` replacing
    `username = None`.
  - `REQUIRED_FIELDS = ["username"]` (Django uses this for
    `createsuperuser` prompts; it lists fields required *in addition
    to* `USERNAME_FIELD` and the password).
  - `__str__` returns `self.username` instead of `self.email` — admin
    list pages, debug output, and `{{ user }}` in templates now show
    the friendly label.
- `apps/accounts/forms.py` — `EmailUserCreationForm.Meta.fields =
  ("username", "email")`. Username field appears first on the signup
  page (UX: pick your display name first, then enter the email
  you'll use to log in).
- `apps/accounts/admin.py` — `username` added to `list_display` (as
  the first column), `search_fields`, `fieldsets` (alongside email
  under the main section), and `add_fieldsets` (so the "add user"
  page in admin requires it too).
- `apps/accounts/management/commands/bootstrap_superuser.py` — reads
  optional `DJANGO_SUPERUSER_USERNAME` env var; falls back to
  `email.split('@')[0][:100]` if unset. Passed through to
  `create_superuser()`. Existing prod superuser is unaffected (the
  command's `User.objects.filter(email=email).exists()` early-return
  is unchanged); only matters if Steven ever wipes and re-bootstraps.
- `templates/base.html` — header `<span class="user">{{ user.email }}
  </span>` → `{{ user.username }}`.
- `templates/bracket/leaderboard.html` — player cell `{{
  s.user.get_full_name|default:s.user.email }}` → `{{
  s.user.username }}`. Per Steven's brief, the goal of mandatory-in-DB
  was specifically to "eliminate any 'if not User.username display
  email' fallback in the template", so the fallback is gone.
- `templates/bracket/_group_bracket.html` — picker `{{
  pick.user.email|truncatechars:24 }}` → `{{ pick.user.username }}`.
  Dropped the truncation: usernames are bounded to 100 chars by the
  model and (in practice) much shorter; CSS can clip if anyone really
  goes long.
- `apps/bracket/services.py: compute_group_standings` — sort
  tiebreaker `user.email.lower()` → `user.username.lower()`. Docstring
  updated to match.

**Design decisions**

1. **Case-sensitive uniqueness.** Steven explicitly picked this when
   offered the case-sensitive vs case-insensitive choice. Simpler
   (just `unique=True` at the DB level; no functional `LOWER()` index
   needed); friends can pick whatever capitalization they want. Side
   effect: "Steven" and "steven" can coexist as distinct users,
   technically allowing impersonation-via-capitalization. Acceptable
   for the friend-pool scale.
2. **Backfill from email local-part, not a prompt.** Existing rows
   needed *something* in the new column. Three options were
   considered: (a) auto-derive from email prefix in a data migration,
   (b) prompt at deploy time, (c) leave nullable forever and check in
   the templates. Picked (a) — deterministic, no manual step on
   deploy, falls out of the model's natural mapping. Steven can
   change his own username via admin afterward.
3. **Mandatory in the DB, not just in the form.** The whole point of
   the change per Steven's brief: "make it mandatory, not optional,
   so as to eliminate any 'if not User.username display email' in the
   CSS logic." The AlterField step at the end of the migration
   enforces NOT NULL at the schema level — no `null=True` left around
   for some future code path to slip through.
4. **No `DJANGO_SUPERUSER_USERNAME` added to `render.yaml`.** The
   project-bracket-app memory notes that Render's
   `sync: false` env vars only get the dashboard prompt at *initial
   Blueprint creation* — adding a new one to `render.yaml` later
   means Steven has to set it manually in the Render dashboard. To
   avoid that one-time hop on next deploy, bootstrap_superuser
   instead derives the username from email prefix when the env var
   is unset. The env var is supported as an opt-in if Steven ever
   does want explicit control.
5. **Used `UnicodeUsernameValidator` (Django's standard).** Allows
   letters/digits/`./_/@/+/-`. Doesn't allow spaces, slashes, or
   most punctuation. Same set used by Django's stock User model — no
   surprises if Steven (or anyone he sends here) has seen Django
   forms before.
6. **`__str__` returns username, not email.** Cosmetic for now;
   matters for admin list pages and `repr()` output during debugging
   (cleaner labels in autocomplete dropdowns, error messages, log
   lines).

**Implementation notes**
- The migration's `_safe_base()` helper strips characters not in
  `UnicodeUsernameValidator`'s regex before deriving the username
  base. Email local-parts can contain `~`, `*`, `!`, etc.
  (technically valid per RFC 5321) which would fail the post-AlterField
  validator. Defensive belt-and-suspenders — none of the 4 existing
  users tripped it.
- Collision handling in the backfill: numeric suffix appended within
  the 100-char limit (`base[:100 - len(suffix)] + suffix`). In
  practice no collisions on this DB; tested in isolation but the
  branch is unexercised.
- `bootstrap_superuser` uses `or` rather than checking env-var
  presence explicitly — `DJANGO_SUPERUSER_USERNAME=""` is treated the
  same as unset (both fall through to the email-prefix derivation).
  Intentional: an empty env var almost certainly means "I forgot to
  set this" rather than "I want a zero-length username".

**Smoke tests (all shell-based via Django Client)**
1. Signup with no username → 200 status, form shows "This field is
   required" error, no user created in DB.
2. Signup with valid username → 302 redirect (success), user created
   with the entered username.
3. Signup with duplicate username → 200, form shows "already exists"
   uniqueness error, no user created.
4. Signup with invalid characters (`no spaces!`) → 200, form shows
   validator error.
5. Leaderboard page renders usernames (e.g. `sarah`, not
   `sarah@test.com`) and email strings are absent from the rendered
   HTML.
6. Header nav (`base.html`) renders username when logged in, no
   email anywhere.
7. Group view (`?view=group`, post-lock) renders usernames in the
   group-picks list; no email strings anywhere on the page.
8. `python manage.py check` clean; `python manage.py makemigrations
   accounts --dry-run` reports "No changes detected" (model matches
   the migration state).
9. Migration applied cleanly on dev DB:
   `s.conwaynielsen@gmail.com` → `s.conwaynielsen`, `sarah@test.com`
   → `sarah`, etc. (4 users, 0 collisions).

**Pending / deferred**
- **Steven's prod superuser will end up with username
  `s.conwaynielsen`** after the migration backfills on first prod
  deploy. If he wants a different display name, the simplest path is
  to edit it via `/admin/` after the deploy (no DB intervention, no
  re-bootstrap needed).
- **No update to `project-bracket-app` memory.** The User-model
  schema is now slightly different from what Phase 0 documented, but
  the memory file mostly talks about higher-level architecture (the
  email-as-USERNAME_FIELD decision is still correct — username is
  display-only). If this turns out to confuse future-me, worth
  adding a line.
- **No tests for the migration's backfill collision branch.** The
  branch is reachable only with email local-parts that collide
  after sanitization (e.g., two users with `john@a.com` and
  `john@b.com`). Phase 6 test pass can cover if Steven wants
  belt-and-suspenders.

**Dependencies introduced**
None. `UnicodeUsernameValidator` and `UserCreationForm` are both
already-imported Django stdlib pieces.

**Deviations from `initial-architecture.md`**
The plan never spec'd a username field — it standardized on
"email as USERNAME_FIELD" in Phase 0 and never revisited. This pass
is additive (username is for display only; email is still the
credential), so no contradiction, but it is a *new* product decision
not anticipated in the original architecture doc. Worth a one-line
note there if/when we do a Phase 6 doc-sweep.

**Untouched (per working contract)**
- `.env` — never read, edited, or inspected.

---

## Test coverage pass ✅ 2026-06-25

Phase 4 / Phase 5 / Username pass all shipped with shell-based smoke
tests only — Steven flagged that "long overdue" and asked for unit
tests "ASAP". This pass introduces pytest-django, ships 75 tests
covering both apps, and adds a granular CLI so individual tests can
be run during debugging without re-executing the whole suite.

**Scope shipped**
- 75 tests across 9 files; full suite runs in ~8s.
- pytest-django integration; `make test` now invokes pytest.
- Shared fixtures (`bracket`, `make_user`, `make_group`, `make_membership`)
  in a project-root `conftest.py`.
- Granular CLI: `make test`, `make test <app>`, `make test <app>:<file>`,
  `make test <app>:<file>:<test_name>` — driven by `scripts/run_tests.sh`.
- `.DEFAULT` guard so unknown top-level targets still get Make's
  "No rule to make target" error (typo safety preserved).

**Files added**
- `pytest.ini` — `DJANGO_SETTINGS_MODULE = config.settings.dev`,
  `--strict-markers`, standard test-file glob.
- `conftest.py` (project root) — `bracket` fixture (calls
  `seed_bracket` + `seed_scoring_rules` + creates 8 Team rows + seeds
  R32-1 and R32-2 with future kickoff so `is_tournament_locked()`
  returns False by default), `_BracketEnv` helper class exposing the
  teams + a `lock_now()` shortcut, and three factory fixtures
  (`make_user`/`make_group`/`make_membership`) as closures with
  auto-incrementing email/username counters.
- `apps/accounts/tests/__init__.py` (empty package marker).
- `apps/accounts/tests/test_models.py` — `TestUserModel` (5 tests):
  `__str__` returns username, username uniqueness IntegrityError,
  email uniqueness IntegrityError, superuser flag-setting, empty-email
  ValueError.
- `apps/accounts/tests/test_forms.py` — `TestEmailUserCreationForm`
  (5 tests): valid form creates user with both fields, missing
  username invalid, missing email invalid, invalid username chars
  rejected by validator, duplicate username rejected.
- `apps/accounts/tests/test_views.py` — `TestSignupView` (3 tests):
  GET renders form, valid POST creates+redirects, missing-username
  POST returns 200 with no creation.
- `apps/accounts/tests/test_commands.py` — `TestBootstrapSuperuser`
  (4 tests): no-op when env vars missing, uses explicit
  `DJANGO_SUPERUSER_USERNAME` when set, falls back to email-prefix
  when unset, idempotent on second run.
- `apps/bracket/tests/__init__.py` (empty package marker).
- `apps/bracket/tests/test_models.py` (18 tests across 5 classes):
  - `TestMatchAutoAdvancement` (8 tests) — set winner pushes to
    home, set winner pushes to away, clearing clears downstream,
    swapping updates downstream, SF→FINAL+THIRD, SF-2 cascade,
    SF winner correction re-cascades, no-winner-change save is a
    no-op for downstream.
  - `TestPredictionLockEnforcement` (2 tests) — pre-lock save
    allowed, post-lock save raises `ValidationError`.
  - `TestTournamentLockTime` (4 tests) — None when no R32-1,
    kickoff − 5min math, locked inside window, unlocked outside.
  - `TestGroupModel` (3 tests) — auto-generates 6-char join_code,
    preserves explicit code, unique across groups.
  - `TestGroupMembershipUniqueness` (1 test) — duplicate `(group,
    user)` raises `IntegrityError`.
- `apps/bracket/tests/test_services.py` (14 tests across 4 classes):
  - `TestDerivedTeamsIsolation` (3 tests) — **the regression-critical
    invariant suite**. R32 reads canonical; R16+ derives purely
    from user picks even after auto-advance fills canonical; user
    Prediction rows survive admin-set winner changes.
  - `TestReconcileUserPicks` (3 tests) — R32 change orphans R16
    pick → deleted; R32 picks themselves never auto-deleted; cascade
    propagates through multiple rounds (R32 → R16 → QF) in one pass.
  - `TestComputeGroupStandings` (5 tests) — correct picks score
    round points, zero-pick users included, sort tiebreaker is
    username asc, admin-edited `ScoringRule.points` reflected,
    empty group returns `[]`.
  - `TestBuildUserBracket` (3 tests) — returns all 6 rounds in
    order, reports lock state, complete-flag requires 32 picks.
- `apps/bracket/tests/test_views.py` (15 tests across 5 classes):
  - `TestBracketView` — member 200, non-member 404, group-mode
    pre-lock redirect to mine.
  - `TestLeaderboardView` — member 200, non-member 404,
    unauthenticated redirects to login.
  - `TestMatchPick` (5 tests) — valid pick creates Prediction,
    rejected when locked, rejected when submitted, rejected when
    team not in match, rejected on match with no derived teams.
  - `TestSubmitBracket` — requires complete bracket (400 when
    empty), rejected when locked.
  - `TestUnsubmitBracket` — rejected when not currently submitted,
    success clears the flag.
- `apps/bracket/tests/test_commands.py` (11 tests across 3 classes):
  - `TestSeedBracket` (5) — creates 32 matches, idempotent, wires
    `feeds_into`/`feeds_as` correctly, SF→FINAL wiring, THIRD left
    unwired.
  - `TestSeedScoringRules` (4) — creates 6 rows, default point
    values match spec, idempotent, admin edits preserved.
  - `TestSeedTeams` (2) — placeholder team set created, idempotent.
- `scripts/run_tests.sh` — bash translator from colon-delimited arg
  to pytest invocation. Validates that `apps/<app>/tests/` exists and
  that `<file>.py` exists; exits 2 with a clear stderr message if
  not. Test-name uses pytest `-k <name>` so callers don't need to
  know which class the test lives in. Executable via `chmod +x`.

**Files modified**
- `requirements.txt` — 5 new pinned deps (see Dependencies below).
- `Makefile` — `test` target now shells out to
  `scripts/run_tests.sh` with `$(filter-out $@,$(MAKECMDGOALS))` so
  the trailing positional arg gets forwarded. `.DEFAULT` rule
  underneath uses a shell-time `firstword $(MAKECMDGOALS) = test`
  check to either no-op the trailing arg or print Make's standard
  "No rule to make target" error and exit 2.

**Design decisions**

1. **pytest-django over stock Django TestCase.** Steven explicitly
   picked this despite the recommendation against. Net effect: same
   test code style (class-based + `setUpTestData`-style fixtures),
   pytest as the runner, `@pytest.mark.django_db` on each DB-touching
   class, function-based test setup via fixtures rather than
   `TestCase.setUp`. Class-based test layout preserved because it
   matches Django convention and grouped fixtures shared across
   related tests; pure pytest functions would have multiplied the
   fixture wiring per test.
2. **All deps in `requirements.txt`, no `requirements-dev.txt`
   split.** Adds ~5MB to the prod image; acceptable for the project's
   single-file dependency convention. Render free tier builds are
   already fast.
3. **Project-root `conftest.py`, not per-app.** Both apps share the
   `bracket` and user-factory fixtures, and Django pytest projects
   conventionally put cross-cutting fixtures at the root. Per-app
   conftest files could be added later if app-specific fixtures
   emerge.
4. **Factory closures (`make_user`, etc.) rather than parametrized
   pytest fixtures.** Each call returns a *new* user with a unique
   auto-incremented email/username, which is what test classes
   actually want. Parametrize would require explicit naming per
   call site.
5. **Single test → `pytest -k <name>` rather than full nodeid.** A
   user typing `make test bracket:test_models:test_winner_set_pushes...`
   shouldn't need to know that test lives in
   `TestMatchAutoAdvancement`. `-k` matches substring against the
   nodeid path, so bare method names work.
6. **CLI uses `.DEFAULT` with shell guard, not the `$(EXTRA_GOALS):
   @:` pattern-rule trick.** First attempt was a conditional rule
   definition that broke on `bracket:test_models:test_name` because
   Make parses the colons as target/prereq separators. Switched to
   `.DEFAULT` (which is a special target, not a pattern, and so
   doesn't have that parse issue) with a `firstword` check on
   `$(MAKECMDGOALS)` to distinguish "trailing arg to test" from
   "user typo'd a goal name".

**Implementation notes**
- `bracket` fixture calls `call_command("seed_bracket")` instead of
  hand-building 32 Match rows. Matches the prod seeding path, so any
  drift between the test setup and what gets deployed is caught here
  first.
- `_BracketEnv` helper exposes team handles as attributes
  (`bracket.usa`, `bracket.mex`, etc.) — readable test code without
  dict subscripts.
- `_BracketEnv.lock_now()` pulls R32-1's kickoff into the past
  rather than mocking `timezone.now`. Cheaper than time mocking, no
  need for `freezegun` or similar, matches what production does
  (lock state is recomputed from DB every call).
- `make_user` defaults: email/username derived from a per-fixture
  counter (`user1@test.com`, `user2@test.com`, ...) so tests don't
  collide on uniqueness constraints when they don't need to specify.
- `compute_group_standings` empty-group test creates a `Group` row
  without going through `make_group` (which auto-creates an
  owner membership). Verifies the empty-iter branch is reachable.
- `bootstrap_superuser` tests use `monkeypatch.setenv` /
  `monkeypatch.delenv` — pytest's built-in env-var sandbox. No
  pollution of the actual test process env.
- `test_views.py::TestSubmitBracket._make_complete` was written as
  a helper to brute-force a 32-pick complete bracket for testing the
  positive submit path, but the positive-submit test was deferred
  (it would have required generating a complete bracket every time
  the fixture initializes, which is non-trivial). The helper is
  unused right now — flagging here so a future Phase 6 expansion can
  pick it up cleanly.

**Smoke tests (the test suite itself, plus the workflow CLI)**
1. `make test` → 75 passed in 8.10s.
2. `make test accounts` → 17 passed in 1.61s.
3. `make test bracket` → 58 passed in 6.81s.
4. `make test bracket:test_commands` → 11 passed in 0.21s.
5. `make test bracket:test_models:test_swapping_winner_updates_downstream_slot`
   → 1 passed, 17 deselected in 0.12s.
6. `make test nonexistent` → exit 2,
   `Error: apps/nonexistent/tests/ does not exist`.
7. `make test bracket:bogus` → exit 2,
   `Error: apps/bracket/tests/bogus.py does not exist`.
8. `make typo` → exit 2,
   `make: *** No rule to make target 'typo'.  Stop.`
9. `make typo test` → exit 2, same Make error (typo fails before
   test runs).
10. `make lint` clean on all new files; `make check` clean.

**Dependencies introduced** (all explicitly approved + pinned)

| Package | Pin | Purpose |
|---|---|---|
| `pytest` | 9.1.1 | Test runner |
| `pytest-django` | 4.12.0 | Django settings/db fixture wiring |
| `iniconfig` | 2.3.0 | pytest transitive — ini-file parser |
| `pluggy` | 1.6.0 | pytest transitive — plugin system |
| `Pygments` | 2.20.0 | pytest transitive — terminal output highlighting |

`pip check` clean post-install. Compatibility verified:
`pytest-django==4.12.0` requires `pytest>=7.0.0`, satisfied by 9.1.1.
Both compatible with Python 3.12 and Django 5.2 LTS.

**Pending / deferred**
- **No CI configured.** Tests run on-demand only. No GitHub Actions,
  no pre-commit hook, no Render build step running the suite. Phase
  6 hardening could add a minimal `pytest` step to `render.yaml`
  buildCommand or a GitHub Actions YAML.
- **No coverage tooling.** `coverage.py` or `pytest-cov` would let
  us measure what's actually exercised. Skipped per "no new deps
  beyond what was asked for" — Steven can add later.
- **Migration backfill branch (username collision suffix) untested.**
  Reachable only with synthetic email collisions in
  `apps/accounts/migrations/0002`; low value to test as-is.
- **Positive submit-bracket test deferred** — the
  `_make_complete` helper is in place but no test exercises it. A
  follow-up could parametrize a complete-bracket scenario and
  assert the `bracket_submitted` flag transitions correctly.
- **No view-level test for `match_pick` success state with cascade**
  — i.e., picking R32-1, then changing it, and asserting the
  reconcile fires through the view layer (not just at the service
  layer). The service-layer reconcile is tested; the view-layer
  glue is not.
- **The `_BracketEnv` fixture seeds 8 teams** (USA/MEX/CAN/BRA/ESP/
  POR/JPN/KOR). Tests that want to exercise the full 32-team
  bracket would need to seed more. Acceptable for current coverage.

**Deviations from `initial-architecture.md`**
- Plan listed `pytest-django==4.x` as **optional** ("can stick with
  `manage.py test` if you'd rather not add deps"). Adopted now.
- Plan didn't anticipate the `make test <app>:<file>:<test>` CLI
  ergonomics. Net-additive; doesn't change anything documented.
- The plan's Phase 6 was titled "Hardening + go-live prep" — this
  pass covers the *test* portion of hardening. R32 draw entry,
  invite-real-users, and final UX sanity check are still pending
  Phase 6 work.

**Untouched (per working contract)**
- `.env` — never read, edited, or inspected.

---

## Tournament lock time codified + timezone-aware UI ✅ 2026-06-25

**Why**
- The opener is now 3 days away (2026-06-28). The lock time needed to be set
  to a real value, not the year-2099 placeholder. Real value: Sunday
  2026-06-28 13:00 America/Denver, i.e. 19:00 UTC. Lock fires at kickoff − 5
  minutes (= 12:55 MDT / 18:55 UTC).
- Up to this point all kickoff times rendered in UTC because
  `TIME_ZONE = "UTC"`. A user in California would have seen "Jun 28 19:00"
  instead of their actual local lock time of 11:55 AM PDT. Fixable without
  schema changes by combining a server-side default tz (Mountain) with a
  client-side `<time datetime>` relocalization pass.

**Decisions made before coding**
1. **Codify R32-1 in `seed_bracket.py` rather than rely on admin entry.**
   R32-1.kickoff_at drives the entire global lock; reproducibility across
   local / staging / prod matters more than admin flexibility for that one
   field. Other 31 matches keep their existing admin-managed pattern
   (placeholder 2099 → admin enters real value when scheduled). Schedule
   volatility (FIFA shifts venues / kickoff times occasionally) is lower
   for the opener than for downstream matches, reinforcing the asymmetry.
2. **Client-side relocalization via `Intl.DateTimeFormat`, not per-user
   timezone preference.** Per-user tz would have required: User schema
   migration, signup form picker, `timezone.activate()` middleware, and
   still relied on JS to detect a sane default. Pure client JS is ~15
   lines, zero schema, zero new deps, and just-works for any browser. We
   accept that no-JS users see Mountain time (the server-render fallback)
   — that's a reasonable default given Steven's the tournament admin and
   the pool is small / friend-group sized.
3. **`TIME_ZONE = "America/Denver"`** for server-side fallback. DB still
   stores UTC (`USE_TZ=True` unchanged). Picked Mountain because Steven
   runs the pool from there and admin pages will render in his tz by
   default — no manual conversion when entering kickoffs.
4. **Augment the lock-countdown copy.** Previously "Time until lock: 1d
   4h 23m". Now also shows the absolute moment ("Brackets lock at
   Jun 28, 12:55 PM MT (your local time)") because the user explicitly
   wanted geographic users to see *their* local lock time, not just a
   countdown. The `MT` suffix in the server-rendered fallback gets
   stripped when JS rewrites the element.

**Done**
- `apps/bracket/management/commands/seed_bracket.py`:
  - Added `R32_1_KICKOFF = datetime(2026, 6, 28, 13, 0,
    tzinfo=ZoneInfo("America/Denver"))` constant. Stored as aware
    datetime; Django converts to UTC on save (= 2026-06-28 19:00 UTC).
  - Added force-sync block after the feeds-wiring loop: compares R32-1's
    current `kickoff_at` to the constant; if different, updates with
    `update_fields=["kickoff_at"]` and increments `kickoff_synced`.
    Re-running the seed is a no-op once the value matches. An admin
    edit to R32-1 will be re-overwritten on next seed (intentional —
    code is now authoritative for that field).
  - Stdout summary line gained a `{kickoff_synced} kickoff-synced` token.
  - Docstring updated: split "kickoff_at NOT set" into "R32-1 IS code-
    managed (exception)" + "R32-2..FINAL NOT code-managed (still admin)".
- `config/settings/base.py`:
  - `TIME_ZONE = "UTC"` → `"America/Denver"`. Comment explains the
    division of labor (server fallback render in Mountain, JS
    relocalizes per viewer).
- `templates/bracket/_match_card.html`:
  - `<span class="kickoff">{{ ...|date:"M j H:i" }}</span>`
    → `<time class="kickoff" datetime="{{ ...|date:'c' }}">{{ ...|date:"M j, P" }} MT</time>`.
  - Switched from `H:i` (24-hour, e.g. "19:00") to `P` (Django's
    locale-style 12-hour with AM/PM, e.g. "1:00 p.m."). The "MT" suffix
    is only seen by no-JS users; JS rewrites textContent entirely.
- `templates/bracket/_group_bracket.html`: same `<span>` → `<time>` swap.
- `templates/bracket/bracket_view.html`:
  - Countdown line rewritten from "Time until lock: <countdown>" to
    "Brackets lock at <time>{lock_time}</time> (your local time) ·
    <countdown> remaining". Still uses `data-lock-time` for the
    ticker (no change to that JS); the new `<time>` element is what
    `tz.js` relocalizes.
- `static/js/tz.js` (new, ~25 lines):
  - IIFE that defines an `Intl.DateTimeFormat` instance (no locale arg
    = browser default, month-short / day-numeric / hour-numeric /
    minute-2-digit).
  - `relocalize(root)` walks `<time[datetime]>` inside the root,
    parses the ISO attr via `new Date()`, replaces textContent. Sets
    `data-tz-applied="1"` to make it idempotent across re-fires.
  - Runs on `DOMContentLoaded` (or immediately if doc already ready),
    AND on `htmx:afterSwap` events bubbling to `document.body` — so
    elements injected by HTMX swaps (e.g. `match_pick` re-renders the
    bracket grid) also get relocalized.
- `templates/base.html`: added `<script src="{% static 'js/tz.js' %}"
  defer></script>` as a sibling to the htmx CDN script. Both deferred,
  both load after parsing.
- `apps/bracket/tests/test_commands.py`:
  - Added `datetime` / `zoneinfo.ZoneInfo` imports.
  - 3 new tests in `TestSeedBracket`:
    - `test_r32_1_kickoff_force_set_to_canonical`: fresh seed →
      R32-1.kickoff_at == 2026-06-28 13:00 America/Denver.
    - `test_r32_1_kickoff_resyncs_after_admin_edit`: seed → admin
      edit (set to 2030-01-01 UTC) → re-seed → original value
      restored. Asserts the force-overwrite semantics.
    - `test_other_r32_kickoffs_remain_placeholder`: R32-2.kickoff_at
      still has year 2099. Pins the "only R32-1 is code-managed"
      invariant.

**Smoke tests**
1. `make test` → 78 passed in 8.10s (was 75; +3 new).
2. `make lint` clean.
3. `make check` clean.
4. Lock-window math, sanity-checked by hand: 2026-06-28 13:00 MDT
   = 2026-06-28 19:00 UTC. tournament_lock_time() returns
   2026-06-28 18:55 UTC = 12:55 MDT = 11:55 PDT = 14:55 EDT.

**Files touched**
- `apps/bracket/management/commands/seed_bracket.py`
- `apps/bracket/tests/test_commands.py`
- `config/settings/base.py`
- `templates/base.html`
- `templates/bracket/_match_card.html`
- `templates/bracket/_group_bracket.html`
- `templates/bracket/bracket_view.html`
- `static/js/tz.js` (new)

**Decisions worth remembering**
- **Only R32-1 is code-managed; R32-2..FINAL stay admin-managed.**
  Steven asked the question explicitly: "why don't other matches need
  their kickoff time changed?" Answer recorded in conversation: the
  lock is one-shot and only gates off R32-1; other kickoffs are
  display-only; FIFA may shift downstream times, so admin entry is
  more flexible than redeployment. If we ever introduce per-match
  locking (e.g. QF picks editable until QF kicks off), every
  kickoff_at becomes behavior-affecting and this asymmetry would need
  revisiting.
- **`Intl.DateTimeFormat()` with no locale arg uses the browser's
  default.** That gives American English-style date formatting for
  most US users without us having to detect or store a locale. If
  a user has their browser set to e.g. en-GB, they'll get
  "28 Jun, 12:55" instead of "Jun 28, 12:55 PM" — acceptable; locale-
  aware rather than locale-imposed.
- **`<time>` element, not `<span>`.** Semantic HTML; screen readers
  and crawlers can interpret the `datetime` attribute. Also lets
  `tz.js` query with `time[datetime]` rather than a custom class
  selector.
- **`data-tz-applied="1"` guard.** Without it, a second HTMX swap
  could re-format already-formatted text (parsing "Jun 28, 12:55 PM"
  via `new Date()` would yield Invalid Date and the script would
  bail, but the guard avoids the wasted work and silent failure
  mode).
- **`make typo`-style typo detection from the prior milestone
  remains intact** — the Makefile's `.DEFAULT` rule was unchanged.

**Pending / deferred**
- **No automated test of `tz.js`.** The relocalization is JS-only and
  the suite is Python-only. A Playwright/Selenium pass could verify
  that a `<time datetime="2026-06-28T19:00:00Z">` element ends up
  with locale-formatted text after page load, but that's well outside
  the current test stack and would require browser-test deps.
  Manual verification only.
- **No verification of `htmx:afterSwap` path.** The `match_pick` flow
  is the main consumer (it returns a new bracket grid via HTMX). The
  swap relocalization works in theory but has only been reviewed by
  inspection, not exercised in a browser run yet. Quick manual test
  recommended after deploy: pick a match, confirm `<time>` elements
  in the re-rendered grid show local tz not UTC.
- **R32-2..R32-16 kickoffs still placeholder.** Steven will enter
  these via admin after the R32 draw (~2026-06-27). The
  `{% if kickoff_at.year < 2099 %}` guard hides the time entirely
  until entered, so users see "TBD"-style cards with no time
  rather than wrong times.
- **`seed_teams` still deferred** from `render.yaml` buildCommand
  (per prior milestone) — Steven will run it locally once the
  group stage finalizes the 32-team set.

**Deviations from `initial-architecture.md`**
- Plan didn't specify timezone handling at all (the architecture doc
  predates the deploy-readiness pass). Net-additive; doesn't change
  anything documented.
- Plan listed seed_bracket as setting "topology + placeholders only,
  no kickoff times". Now: topology + 31 placeholders + 1 hardcoded
  (R32-1). Net change is one constant + one force-sync block. Plan
  file not updated since this is a small refinement and the docstring
  in the command itself is now the authoritative reference.

**Untouched (per working contract)**
- `.env` — never read, edited, or inspected.
- `render.yaml` — no env-var or buildCommand changes needed. The
  `TIME_ZONE` switch is in settings, not env. The codified R32-1
  kickoff runs via the existing `seed_bracket` buildCommand step.


## R32 draw load + display-name templates ✅ 2026-06-27 (live verified same day)

T-1 day to kickoff. The FIFA R32 draw locked in, so this milestone
closes the "R32 draw entry" item from Phase 6 hardening (project memory).
Two threads landed together:
1. Encode the canonical 32-team WC26 roster + 16 R32 matchups as
   code-managed seed data (parallel to how R32-1 kickoff was already
   code-managed).
2. Fix the match-card templates to render display names instead of
   FIFA 3-letter codes — bug caught only after prod deploy.

**Why code-managed instead of admin-entered**: the FIFA R32 draw is
fixed once announced. Encoding it in source keeps prod immune to admin
slip-ups, gives local/test environments a fully-populated R32 out of
the box (no manual entry per dev box), and makes the matchup table
greppable / diffable. Same justification as R32-1 kickoff from the
prior milestone. R16+ home/away stays cascade-driven (via
`_advance_winner` from `Match.save`) because those slots aren't known
until results come in.

**What shipped**

1. **`seed_teams.py` expanded from 3-team placeholder to full 32-team
   roster.** Alphabetical by display name (matches
   `Team.Meta.ordering`). Each entry: `(FIFA code, display name, flag
   emoji as \U escape pair)`. Six judgment calls baked in (see
   "Decisions worth remembering" below).
2. **`seed_bracket.py` gained `R32_MATCHUPS`** — a 16-entry dict
   mapping slot → `(home_code, away_code)`. `handle()` now resolves
   teams via `Team.objects.in_bulk(..., field_name="code")` and
   force-sets `home_team`/`away_team` on each R32 match. Idempotent
   re-sync if matchups ever change.
3. **New `CommandError` if `seed_teams` hasn't run.** seed_bracket
   computes the set of required FIFA codes from `R32_MATCHUPS` and
   raises with the missing codes listed if any aren't in the DB. Avoids
   cryptic `KeyError` downstream. Updated docstring explicitly states
   the seed_teams prereq.
4. **stdout now reports `matchups-synced` count** alongside the
   existing `kickoff-synced`. First-time prod run logged
   `16 matchups-synced`, `1 kickoff-synced`.
5. **Test updates**:
   - `TestSeedBracket` gained an `autouse=True` fixture
     `_seed_teams` that calls `seed_teams` before each test in the
     class. Without it the new CommandError would fire in every test.
   - Three new tests: `test_r32_matchups_force_set` (spot-checks
     R32-1=GER/PAR and R32-16=COL/GHA), `test_r32_matchups_resync_after_admin_edit`
     (swaps home/away, re-runs seed, asserts reset), and
     `test_aborts_loudly_without_teams` (deletes all teams, expects
     CommandError matching "seed_teams").
   - `TestSeedTeams.test_creates_placeholder_teams` renamed to
     `test_creates_full_roster` — asserts count == 32 and spot-checks
     `{USA, CAN, MEX, GER, BRA, ENG}.issubset(codes)`. Old test
     comment referenced "3 placeholder host nations" which was now
     stale.
6. **Shared `conftest.py` rework**: the project-wide `bracket`
   fixture now calls `seed_teams` *before* `seed_bracket` (the old
   order would now hit the new CommandError). The fixture's previous
   8-team inline `TEAM_FIXTURES` (USA/MEX/CAN/BRA/ESP/POR/JPN/KOR
   created via `Team.objects.create`) is replaced with
   `FIXTURE_TEAM_CODES`, a 7-code list that pulls teams from
   seed_teams's roster via `Team.objects.get(code=...)`. KOR (South
   Korea) was dropped entirely — it was provisioned for SF
   cascade tests that never actually used it (grep confirmed
   `self.kor` was set on `_BracketEnv` but never referenced from any
   test). The R32-1/R32-2 home/away overrides (USA/MEX, CAN/BRA) and
   the kickoff override (T+1 day) still happen — they override
   seed_bracket's GER/PAR/FRA/SWE force-set so existing tests stay
   stable.
7. **Template fix: `team.code` → `team.name`** in seven spots across
   two templates. Bug surfaced only after the first prod deploy when
   Steven hit the live URL and saw "GER" / "PAR" / "BIH" on match
   cards instead of "Germany" / "Paraguay" / "Bosnia & Herz.". The
   tooltip `title=` attribute already used `.name`; the visible card
   text was using `.code` for tighter card width, but the
   judgment-call abbreviations in seed_teams (Bosnia & Herz., DR
   Congo) made the full names compact enough.
   - `_match_card.html`: lines 16, 23, 31, 39 (home/away on
     interactive + read-only card variants).
   - `_group_bracket.html`: lines 18, 22 (home/away on group view),
     line 33 (each member's pick label).
8. **Prod load** ran from laptop via local-against-remote-DB
   workaround. Output recorded for posterity:
   - `seed_teams`: `Seed complete: 29 created, 3 updated, 32 total`
     (the 3 updates are the Phase-3 USA/CAN/MEX placeholders being
     refreshed to the canonical display names — though Mexico's
     display name is unchanged at "Mexico" so technically it's a
     no-op write; harmless).
   - `seed_bracket`: `Bracket seed: 0 created, 0 round-synced, 0
     (re)wired, 1 kickoff-synced, 16 matchups-synced, 32 total
     matches.` (32-match topology already existed from Phase 3; R32-1
     kickoff was sitting on the 2099 placeholder until this run; all
     16 matchups set for the first time.)

**Files touched**
- `apps/bracket/management/commands/seed_teams.py`
- `apps/bracket/management/commands/seed_bracket.py`
- `apps/bracket/tests/test_commands.py`
- `conftest.py`
- `templates/bracket/_match_card.html`
- `templates/bracket/_group_bracket.html`
- `apps/bracket/R32.md` (new — human-readable matchup ledger kept as
  a historical artifact; intentionally not authoritative)

**Decisions worth remembering**

- **R32.md as ledger, not source of truth.** R32.md lists the 16
  matchups with team display names — easy to eyeball against the
  official draw. But it's not parsed or read by code. Codes + flags
  live in `seed_teams.TEAMS`; matchups live in
  `seed_bracket.R32_MATCHUPS`. The split keeps Team identity attached
  to the Team model (its natural home) and lets R32.md stay a thin,
  delete-able artifact post-tournament.
- **FIFA 3-letter codes, not ISO 3166-1 alpha-3.** Where they diverge
  the FIFA convention wins: `GER` (not DEU), `NED` (not NLD), `SUI`
  (not CHE), `RSA` (not ZAF), `POR` (not PRT), `CRO` (not HRV), `ALG`
  (not DZA), `PAR` (not PRY). Flag emoji escapes use the ISO 3166-1
  alpha-2 regional-indicator pairs (separate from the FIFA codes —
  e.g. Germany = FIFA `GER` + flag emoji from `DE`).
- **England flag = 🇬🇧 (Union Jack / GB), not the subdivision
  flag 🏴󠁧󠁢󠁥󠁮󠁧󠁿.** The subdivision flag (`U+1F3F4` + tag sequence for
  "gb-eng") is the technically-correct representation but renders
  inconsistently across older Android, Linux, and some Windows
  builds — falls back to a plain black flag. The UK Union Jack
  renders universally. Steven explicitly chose render-reliability
  over technical correctness here.
- **Display name calls (Steven's per-team picks)**:
  - `USA` for "USA" (not "United States" — matches R32.md, tighter
    on cards).
  - `Bosnia & Herz.` (16-char "Bosnia and Herzegovina" shortened).
  - `DR Congo` (FIFA short form; full "Democratic Republic of the
    Congo" too long for cards).
  - `Cape Verde` (English) over `Cabo Verde` (FIFA-official since
    2013).
  - `Ivory Coast` over `Côte d'Ivoire` (FIFA-official) — English
    readability.
- **Alphabetical-by-display-name ordering in TEAMS list**: matches
  `Team.Meta.ordering = ["name"]`, easy to scan or grep, easy to
  slot in WC 2030 additions later.
- **CommandError on missing teams > silent skip**: explicit failure
  with the missing codes listed forces correct order
  (`seed_teams` → `seed_bracket`). A silent "skip if missing" mode
  could ship a half-wired bracket to prod and we'd never notice.
- **Bug caught post-deploy was a missing-coverage gap, not a logic
  error.** All 86+ tests passed, but no test exercised
  template rendering of team names on a match card. Worth filing
  mentally as "if we ever add view rendering tests, assert the team
  name string appears in the response HTML."

**Operational notes**

- **prod.py hard-requires four env vars** for `python-dotenv` /
  base-settings loading: `DATABASE_URL`, `SECRET_KEY`,
  `ALLOWED_HOSTS`, `RESEND_API_KEY`. The local-against-remote-DB
  workaround needs all four set. `SECRET_KEY` / `ALLOWED_HOSTS` /
  `RESEND_API_KEY` can be dummy values for management commands
  (they're not used by seed commands; only `DATABASE_URL` is). The
  pattern used:
  ```
  export SECRET_KEY='not-used-by-seed'
  export ALLOWED_HOSTS='localhost'
  export RESEND_API_KEY='not-used-by-seed'
  export DATABASE_URL='<Render external DB URL>'
  export DJANGO_SETTINGS_MODULE=config.settings.prod
  .venv/bin/python manage.py seed_teams
  .venv/bin/python manage.py seed_bracket
  unset SECRET_KEY ALLOWED_HOSTS RESEND_API_KEY DATABASE_URL DJANGO_SETTINGS_MODULE
  ```
  `python-dotenv` is invoked with `override=False`, so `export`-set
  values win over anything in `.env`.
- **Local pre-seed cleanup** (one-time): when running the new
  `seed_bracket` against a dev DB that had stale R16/QF/winner state
  from earlier manual testing, the fastest reset was
  `Match.objects.all().update(home_team=None, away_team=None, winner=None)`
  followed by `seed_bracket`. Avoid `.save()`-looped clears because
  `_advance_winner` re-fires mid-loop on every save.

**Verification**

1. `make test` clean across the whole repo (~88+ tests after the
   3 new ones).
2. Local smoke test on `runserver` (against SQLite reset to clean
   state): all 16 R32 cards populated, England shows 🇬🇧, DR Congo
   shows 🇨🇩 (not 🇨🇬), R32-1 kickoff visible in browser-local tz,
   R32-2..16 hide the kickoff via the year-2099 guard, no layout
   regressions on the long-name cards (USA vs Bosnia & Herz.,
   England vs DR Congo).
3. CI green on push (~30-45s, Mode B Render deploy auto-fires).
4. Live URL verified post-deploy. Initial check surfaced the
   `.code`-vs-`.name` bug; template fix pushed, CI re-ran, second
   deploy verified — all 16 R32 matchups now render display names
   with flags on the live bracket.

**Pending / deferred**

- **R32-2..FINAL kickoff entry** — still admin-managed. FIFA schedule
  needs to be entered per match (or all at once). Templates hide the
  time via the 2099-year guard until a real kickoff is entered, so
  cards display correctly without it. Not blocking for go-live.
- **R32.md retention**: kept in `apps/bracket/` as an artifact. Safe
  to delete after the tournament ends 2026-07-19.
- **View-rendering test coverage**: no test asserts that the bracket
  HTML contains a team name string. The `.code`/`.name` bug would
  have been caught earlier with even a one-line assertion. Not a
  blocker; worth a follow-up if Phase 6 hardening continues.
- **Resend domain flip**: still deferred (Steven hasn't purchased
  domain). Sandbox mode covers personal-circle invites for now.

**Deviations from `initial-architecture.md`**
- Plan listed the R32 draw as fully admin-entered. Now: code-managed
  in `seed_bracket.py` + `seed_teams.py`. Net-additive (one dict + one
  force-sync loop) and reversible. Plan file not updated; the
  seed_bracket docstring is the authoritative reference.

**Untouched (per working contract)**
- `.env` — never read, edited, or inspected.
- `render.yaml` — no Blueprint / env-var / buildCommand changes. Prod
  seed ran entirely from laptop via existing infra.
- `requirements.txt` — no new dependencies.

## Render deploy triage + application logging ✅ 2026-07-01

Two threads in one session, both operational hardening while the
tournament is live (R32 in progress, R16 slate this weekend). No new
features; no schema changes; no new dependencies.

**Thread 1 — Render deploy stuck overnight**

Symptom: site started 5xxing overnight (2026-06-29 → 2026-06-30) with
no application logs to inspect. Steven pushed an empty commit
(`332066d`) to force a redeploy. Build succeeded (migrations,
superuser bootstrap, seed commands all ran clean), but the deploy
stalled between Render's `==> Setting WEB_CONCURRENCY=1 ...` line and
the expected `==> Running 'gunicorn ...'` line. Gunicorn was never
invoked — the runtime layer wedged before start-command handoff.

Diagnosis path:
- Confirmed no recent code changes were causal: `6e101cb "important
  block"` was README-only (added a "no association with FIFA"
  callout); `332066d` was the empty trigger; last real code commit was
  `7486bd5` on 2026-06-27 (display-name template fix).
- Confirmed `status.render.com` clean.
- Confirmed linked Postgres `wc26-bracket-db` showing "available".
- Confirmed both stuck log lines were Render-emitted (`==>` prefix),
  so the gap is Render's platform, not the app.

Fix: **dashboard → web service → Settings → "Clear build cache &
deploy"**. Third deploy attempt (with cache cleared) proceeded past
the stall, gunicorn booted, site went live. Total downtime was
roughly overnight into morning MT. Empty-commit redeploys re-use the
build cache and *do not* unstick the underlying wedged state — this
was the operational lesson.

Captured as memory: `project_render_deploy_stuck.md` so future
sessions don't rediagnose from scratch.

**Thread 2 — Application logging shipped**

Motivation: incident above surfaced zero prod-side observability
beyond gunicorn access logs. `config/settings/base.py` had no
`LOGGING` config; codebase had zero `logger.*` calls. Tracebacks were
going to stdout with Django's default (barely-formatted) handler;
domain events (picks, submits, winner advances) were invisible.

Scope explicitly approved before touching code:
- Central `LOGGING` dict in `base.py`, inherited by dev + prod.
- Plain human-readable format, not JSON. Rationale: Render's log
  viewer isn't a structured-log tool; Steven will eyeball these more
  than query them.
- Single `StreamHandler` → stdout. Render captures stdout. No file
  handler (free-tier disk is ephemeral).
- Root at WARNING; `apps.bracket` + `apps.accounts` at INFO;
  `django.request` + `django.security` at WARNING with
  `propagate=False` so they land in the same stream without
  duplicating.
- INFO for event success (pick saved, bracket submitted, winner set,
  advance wired, signup, seed summary). WARNING for user-facing
  rejections that indicate confusion or clock skew (pick / submit
  rejected because locked or already-submitted).
- No new dependencies. No Sentry. No per-request access logging
  (gunicorn already emits it). No SQL query logging.

**Log-call sites added**

- `apps/bracket/views.py`
  - `match_pick`: WARNING on lock/submit reject (includes
    `locked=<bool>` and `submitted=<bool>` so the record self-explains
    which branch fired); INFO on successful pick save
    (user + group + match slot + team code).
  - `submit_bracket`: WARNING on reject; INFO on successful submit.
- `apps/bracket/models.py`
  - `Match.save()`: INFO on winner change (set or cleared), inside
    the existing `old_winner_id != self.winner_id` guard so it only
    fires on true transitions.
  - `_advance_winner()`: INFO on downstream mutation for the
    `feeds_into` path *and* the SF→THIRD path. Only fires when there's
    an actual state change (guarded by the pre-existing
    `current != target` check).
- `apps/accounts/views.py`
  - `signup`: INFO after `login()`.
- `apps/bracket/management/commands/seed_teams.py` &
  `seed_bracket.py`
  - Both emit their existing summary line to `logger.info` alongside
    `stdout.write`. Local UX unchanged; prod build logs now capture
    the summary without extra scraping.

**Test added**

`test_pick_rejected_when_locked_logs_warning` in
`apps/bracket/tests/test_views.py`. Uses `caplog.at_level(WARNING,
logger="apps.bracket.views")` (needed because our loggers use
`propagate=False`, so caplog's root handler wouldn't otherwise see
these records). Asserts a `WARNING` record fires from
`apps.bracket.views` with `"pick rejected"` and `"locked=True"` in the
message. Suite now at 82 passing.

**Files touched**
- `config/settings/base.py` — `LOGGING` dict appended after
  `DEFAULT_AUTO_FIELD`.
- `apps/bracket/views.py` — 1 import, 4 log calls.
- `apps/bracket/models.py` — 1 import, 3 log-call sites (Match.save +
  2 branches of _advance_winner).
- `apps/accounts/views.py` — 1 import, 1 log call.
- `apps/bracket/management/commands/seed_teams.py` — 1 import, 1 log
  call.
- `apps/bracket/management/commands/seed_bracket.py` — 1 import, 1
  log call.
- `apps/bracket/tests/test_views.py` — 1 import, 1 new test.

**Decisions worth remembering**
- **Format string: `"%(asctime)s %(levelname)s %(name)s
  %(message)s"`**. Deliberate choice against JSON. Rationale: Render
  free tier's log viewer is a plain scroller. Human-readable wins for
  low-volume eyeball scanning; a rewrite to structured is cheap later
  if the viewing tool changes.
- **`propagate=False` on named loggers.** Without this, records
  duplicate: once via the named logger's handler, once via the root
  logger's handler. Cost: `caplog` in tests needs an explicit
  `logger=` argument to see them.
- **INFO threshold decision for domain events** (pick saved, winner
  set, etc.). WARNING would only fire for rejections; a boring quiet
  log stream during normal play is a *feature*, not undertesting. If
  volume ever becomes a problem, we can drop `apps.bracket` to
  WARNING with one line in `base.py`.
- **Skipped password-reset request logging** despite it being in the
  original scope. Django's built-in `PasswordResetView` is wired via
  `accounts/urls.py`; adding one log line would mean subclassing a
  CBV or wiring a signal. Scope creep for one event; flagged for
  Steven's redirect and he did not push back.

**Verification**
1. `make test` clean — 82 passing (was 81 before the new test).
2. Confirmed the new WARNING branch fires via the new test (which
  asserts the exact message content, not just count).
3. No dev-side behavior change: seed commands still print their
  summary to stdout in normal color-styled Django management output;
  the new `logger.info` mirrors it for prod capture.

**Pending / deferred**
- **Tier decision for the tournament window** — outage above is the
  strongest data point yet that free tier isn't ideal for a
  live-audience deployment. Starter ($7/mo) gets shell access + real
  logs + no wedged-runtime surprises. Reversible after 2026-07-19.
  Steven hasn't decided; flagged in `project_render_deploy_stuck.md`.
- **View-rendering test coverage** (carried forward from last
  milestone). Still no test asserts team name strings appear in
  bracket HTML. Same low-priority bucket as before.
- **Log-based metrics / alerting** — none. No Sentry integration.
  If tournament traffic exposes a bug, Steven will grep the Render
  log stream manually.
- **CI/CD quiz** — still queued for next-session start via
  `pending_quiz_cicd.md`. Deferred again this session.

**Untouched (per working contract)**
- `.env` — never read, edited, or inspected.
- `render.yaml` — no Blueprint / env-var / buildCommand changes.
- `requirements.txt` — no new dependencies.
- `prod.py` — no direct edits; the new `LOGGING` config is inherited
  from `base.py` via `from .base import *`.
