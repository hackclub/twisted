# AGENTS.md

Twisted (https://twisted.hackclub.com) is a Hack Club YSWS site built with Django 6 and PostgreSQL.
Participants log project time (Hackatime or untracked journals) and ship projects for review in Ari.
They earn **twists**, which they deposit into time-boxed **pathways** as **golden twists** and spend in
each pathway's shop. The client UI is a retro desktop in which every app window is an iframe.
The staff panel is custom-built.

Detailed docs are in [`docs/`](docs/README.md). Read the relevant doc before you change an area, and
update it when you change the behaviour it describes.

## Commands

Run Python through `uv run`, from `twisted/`. Do not call `python` or `manage.py` directly, and do not activate `.venv`.

```bash
cd twisted
cp .env.example .env                       # first time only
docker compose up -d db                    # Postgres 16; required for running the app and the tests
uv run manage.py migrate
uv run manage.py tailwind install          # first time only (needs npm)
uv run manage.py tailwind dev              # runserver + Tailwind watcher
uv run manage.py test --settings mysite.test_settings          # full test suite
uv run manage.py test twisted_site.tests.test_journals --settings mysite.test_settings
uv run manage.py makemigrations            # CI runs makemigrations --check
uv run manage.py update_vendor_assets --check                 # vendored JS
uvx ruff check                             # from the repo root; CI lints with ruff (ALL rules)
```

For local development, set `DEBUG=true`, `AUTH_DEBUG=true` (fake HCA identity) and `DEBUG_REVIEW=true`
(skips Ari and adds a local review panel at `/admin/review/`). To create a local admin, follow
the steps in README.md.

## Map

- `twisted/mysite/`: settings (all configuration comes from env vars), `test_settings.py`, root URLs, `TimezoneMiddleware`.
- `twisted/twisted_site/`: the app.
  - `models.py`: every model, plus shared limits and constants.
  - `urls.py`: every route.
  - `views/client/`: participant views. Desktop frames have URL names starting with `fr.`.
  - `views/admin/`: staff views. Every one subclasses `AdminView`.
  - `views/ari.py`: the review webhook.
  - `views/image_upload.py`: R2 image uploads.
  - `hca.py`, `hackatime.py`, `ari.py`, `slack.py`: external service clients.
  - `validation.py`: URL checks.
  - `templates/{client,admin,cotton}/`, `static/` (`vendor/` holds checked-in third-party JS), `tests/`.
- `twisted/common/templates/base.html`: base template for the landing pages. `twisted/tailwindcsstheme/` holds the Tailwind v4 sources.

## Rules that are easy to break

- **Auth in every view.** Client views start with
  `if self.request.user.is_anonymous: return redirect("homepage")`, and they check ownership
  explicitly (`project.user != request.user`).
  - Shipped projects (`project.is_shipped()`) must reject settings and journal changes.
- **Admin permission pattern.** In an `AdminView` handler, check `self.perms.<flag>` and set
  `self.allowed = True` only when the check passes. If `allowed` stays `False`, `dispatch` redirects
  to `admin.dash` and logs the denial.
  - Every admin request writes an `AuditLog`. Put details in `self.audit_log.additional_context`
    and set `.pii = True` when the request touches personal data.
- **Currency changes go through** `Profile.add_currency` / `remove_currency` and
  `Pathway.add_currency` / `remove_currency`. These are atomic and write ledger rows. Use
  `select_for_update` in purchase-style flows.
- **Slack:** pass every user-controlled string through `slack.escape_mrkdwn()`.
  `log_to_channel` never raises. Maker notifications must not fail webhook handling.
- **URLs from users or Ari** must pass `validation.invalid_http_urls` or `sanitize_http_url`, which allow only http(s).
- **Field limits** live in `models.py` (`PROJECT_*_MAX_LENGTH`). Reuse them rather than hard-coding numbers.
- **No CDN JavaScript.** Load JS only from `static/vendor/`; `test_static_assets.py` enforces this. Pass data to JS
  with `json_script` or `data-*` attributes, not string interpolation inside `<script>`. Never pass user
  input to the templates that render `{{ info|safe }}`.
- **Journal images** must be R2 uploads. `journal_markdown.js` hides external images, which would let the image host log readers' IPs.
- **Ari secrets:** `ARI_SIGNING_SECRET` signs outbound requests and `ARI_WEBHOOK_SECRET` verifies
  inbound ones. Never accept a webhook when the webhook secret is empty. Record a delivery id only after its event has been applied.
- **Never enable `DEBUG_REVIEW` outside local development**: ships would never reach reviewers.
- **Migrations:** add one for every model change. Data migrations use `apps.get_model` and have a reverse function.
  Do not renumber or squash the existing duplicate 0034/0036 files.
- **Style:** ruff runs with `select = ["ALL"]`.
  - Annotate types and use `@override`.
  - Write `_ = call()` when discarding a return value.
  - Put an exception's message in a variable before raising it.
  - Use `as_user(request.user)` to reach `.profile` with types.
  - The code base uses hand-written `View.get`/`post` with `request.POST.get` validation, not Django forms.
- **Tests:** mock external services where the code under test imports them, e.g.
  `patch("twisted_site.views.client.project.log_to_channel")`.
  Tests need Postgres, and the test settings do not load `.env`.

## Known issues (as of 2026-11-22)

- `tests/test_economy.py::TwistEarningTests` calls `Profile.twists_earned()` and
  `refresh_twists()`. Both were removed, and nothing awards twists yet (`TWISTS_PER_HOUR = 50` is unused).
- `CurrencyLog.__str__` and `PathwayCurrencyLog.__str__` reference a `profile.username` field that does not exist.
- `docker-compose.yml`'s `web` service targets a `development` stage that the Dockerfile does not define.
- `.github/dependabot.yml` has an empty `package-ecosystem`.
- `.claude/worktrees/fix-docker-build` is an accidentally committed gitlink.
- `tailwindcsstheme/static_src/src/styles.css` hard-codes `.venv/lib/python3.13/...` as a source path.
- Migration 0051 creates an `ApiKey` model that `models.py` no longer defines, so `makemigrations --check`
  (and CI) wants a `DeleteModel`. Decide whether to drop the table before generating that migration.
