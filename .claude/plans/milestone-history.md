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
