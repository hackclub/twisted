# Architecture

Twisted (https://twisted.hackclub.com) is a Hack Club YSWS ("You Ship, We Ship") site.
Teens build software or hardware projects, log time in journals, ship the projects for
review, earn **twists** (currency), and spend them in time-boxed **pathways** to buy
shop items (the end goal is parts for a PC). The UI is a retro desktop: start menu,
draggable windows and background music.

## Repository layout

```
.                         # uv project root (pyproject.toml, uv.lock, .python-version = 3.13)
├── CLAUDE.md / AGENTS.md
├── docs/                 # this documentation
├── .github/              # CI: ruff + Django tests; dependabot (uv, grouped)
├── .claude/worktrees/fix-docker-build   # accidentally committed gitlink (mode 160000), ignore it
└── twisted/              # Django project root (run all manage.py commands from here)
    ├── manage.py
    ├── .env.example      # copy to twisted/.env
    ├── Dockerfile, entrypoint.sh, docker-compose.yml, Procfile.tailwind
    ├── mysite/           # project package: settings, test_settings, urls, middleware, wsgi/asgi
    ├── common/           # tiny app: only templates/base.html (the root HTML skeleton)
    ├── tailwindcsstheme/ # django-tailwind theme app (Tailwind sources under static_src/)
    └── twisted_site/     # the real app: models, views, templates, static, tests, migrations
```

### `twisted_site/` in detail

| Path | Purpose |
|---|---|
| `models.py` | Every model plus shared constants (field limits, `TWISTS_PER_HOUR`, choice dicts) and the `as_user()` typing helper. See [domain-model.md](domain-model.md). |
| `urls.py` | All routes (included at `/` by `mysite/urls.py`). See [views-and-urls.md](views-and-urls.md). |
| `views/client/` | Participant-facing views. Most render *frames* loaded into desktop windows. |
| `views/admin/` | Staff panel. Every view subclasses `AdminView` (`views/admin/admin.py`). |
| `views/ari.py` | Inbound Ari review webhook (`/api/ari/`). |
| `views/image_upload.py` | `/api/upload_image/`: validates images and uploads them to Cloudflare R2. |
| `hca.py`, `hackatime.py`, `ari.py`, `slack.py` | Thin clients for external services. See [integrations.md](integrations.md). |
| `validation.py` | `is_http_url` / `sanitize_http_url` / `invalid_http_urls`: only absolute http(s) URLs are stored. |
| `templatetags/` | `maths`, `time_filters`, `uploads` template libraries. See [frontend.md](frontend.md). |
| `management/commands/update_vendor_assets.py` | Refreshes vendored JS from the npm registry. |
| `templates/` | `client/`, `admin/`, `cotton/` (django-cotton components). |
| `static/` | Images, audio, video, fonts, `js/`, and `vendor/` (checked-in third-party JS). |
| `tests/` | Django `TestCase` suite. See [testing.md](testing.md). |
| `admin.py` | Empty: `django.contrib.admin` is **not** installed; the staff panel is custom. |

## Stack

- **Django 6** (uses the built-in `django.tasks` framework with the `django_tasks_local.ThreadPoolBackend`).
- **PostgreSQL 16** (required: `django.contrib.postgres` is installed and the settings only configure Postgres; there is no SQLite fallback).
- **django-cotton** + **django-cotton-ui** components, **Tailwind** via `django-tailwind`, **Alpine.js**, **htmx** (admin only, via `django-htmx`), **marked** + **DOMPurify** for Markdown, **Chart.js** for admin charts.
- **whitenoise** (`CompressedManifestStaticFilesStorage`) serves static files; **gunicorn** (gthread, 3 workers × 4 threads) in production.
- **authlib** for Hack Club Identity OIDC, **slack_sdk** (via `slack-bolt`) for Slack, **boto3** for R2, **Pillow** for image validation.
- Some dependencies in `pyproject.toml` are unused leftovers (e.g. `django-jazzmin`, `django-google-charts`, `django-qsstats-magic`, `aiohttp`). Check with `grep` before assuming something is used.

## Settings and environment

`mysite/settings.py` loads `twisted/.env` with python-dotenv **only when `ALLOWED_HOSTS`
is unset or empty** in the real environment. Required variables (a `KeyError` at import
time if they are missing): `SECRET_KEY`, `POSTGRES_DB/USER/PASSWORD/HOST`. Others are read
at import time by the modules that use them: `HCA_CLIENT_ID/SECRET`
(`views/client/auth.py`) and `R2_ENDPOINT/ACCESS_KEY/SECRET_KEY` (`views/image_upload.py`).
Others are read per request (`HCA_REDIRECT_URI`, `HACKATIME_*`, `R2_BUCKET`,
`R2_PUBLIC_URL`, `LOGIN_ENABLED`, `DEFAULT_PFP`).

| Variable | Effect |
|---|---|
| `DEBUG` | Turns off the secure-cookie, SSL-redirect and HSTS settings, adds `django_browser_reload`, and prefixes Slack log posts with `[DEBUG]`. Also the default for `DEBUG_REVIEW` and `AUTH_DEBUG`. |
| `DEBUG_REVIEW` | Skips Ari submission (`ari.send_ship` returns early), makes `ari.is_configured()` true, and swaps `/admin/review/` for a local debug review panel. **Never enable in production.** |
| `AUTH_DEBUG` | `hca.get_user_data()` returns a fake identity ("Heidi Hacksworth") and the HCA OAuth scope list is reduced. Defaults to `DEBUG`. |
| `LOGIN_ENABLED` | `true`, `false` (block all logins) or `maybe` (only profiles with `is_allowed=True` can log in; staff toggle this on the user's admin page). |
| `ARI_INGEST_ENDPOINT`, `ARI_SIGNING_SECRET`, `ARI_WEBHOOK_SECRET` | Ari review integration. All three are needed for shipping unless `DEBUG_REVIEW`. Without `ARI_WEBHOOK_SECRET`, inbound webhooks return 503. |
| `SLACK_TOKEN`, `SLACK_LOG_CHANNEL` | Bot token and the channel that receives activity logs. |
| `R2_*` | Cloudflare R2 (S3-compatible) bucket for journal image uploads. |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | Comma-separated lists. |
| `DEFAULT_PFP` | Fallback avatar when the Slack lookup fails (else `static/images/twisted_t.png`). |
| `NPM_BIN_PATH` | Used by django-tailwind. |

Other notable settings:

- `LOGIN_URL = "homepage"` (the homepage hosts the login button).
- `CSRF_COOKIE_HTTPONLY = False` so that JS (the image uploader) can read the token.
- `X_FRAME_OPTIONS = "SAMEORIGIN"`: needed because desktop windows load frames with iframes from the same origin.
- `USE_X_FORWARDED_HOST` and `SECURE_PROXY_SSL_HEADER`: production runs behind a TLS-terminating proxy.
- `mysite/middleware.TimezoneMiddleware` activates the timezone in the `django_timezone` cookie (set by the front end).
- `/health` and `/health/` return 204, for container health checks.

`mysite/test_settings.py` `setdefault`s a full fake environment, then imports the real
settings. It forces `DEBUG`/`DEBUG_REVIEW` off, removes whitenoise, uses MD5 password hashing
and plain `StaticFilesStorage`. Tests still need a real Postgres.

## Request flow and conventions

- **Class-based `View`s with hand-written `get`/`post`.** The code does not use Django forms or
  generic views. POST data is read with `request.POST.get(...)` and validated by hand.
  Error messages go back by re-calling `self.get(request, ..., info=..., context=...)`
  or through `django.contrib.messages`.
- **Auth check:** most client views begin with
  `if self.request.user.is_anonymous: return redirect("homepage")`. Only
  `upload_file` uses `@login_required`. Ownership checks (`project.user != request.user`)
  are explicit in each view. Keep both checks in every new view.
- **Ship lock:** once a project `is_shipped()` (its latest ship is not `requested_changes`),
  settings and journal create/edit/delete views redirect to the project detail page.
- **Slack activity log:** most user actions call `slack.log_to_channel(...)`. Every
  user-controlled string passed to Slack **must** go through `slack.escape_mrkdwn()`.
- **Typing:** the code is checked with pyright, pyrefly and ty (hence the inline
  `# ty:ignore[...]`, `# pyright: ignore[...]` and `# pyrefly: ignore[...]` comments). Use
  `as_user(request.user)` to reach `.profile` / `.projects` with proper types.
  `TemplateContext` (`dict[str, Any]`) is the loose context-dict alias.
- **Ruff** with `select = ["ALL"]` and a short ignore list (see [testing.md](testing.md)).

## Deployment

The `Dockerfile` (single `build` stage) installs Node 22 and the uv dependencies, runs
`tailwind install`, `tailwind build` and `collectstatic`, and then starts `entrypoint.sh`. That
script runs `migrate --noinput` and then gunicorn on `:8000`. The container runs as UID 999.
`docker-compose.yml` is mainly used for local Postgres (`docker compose up db`). Its
`web` service references a `development` target that the Dockerfile does not define.

## Known oddities

- `CurrencyLog.__str__` and `PathwayCurrencyLog.__str__` reference `profile.username`,
  which does not exist on `Profile` (use `profile.user.username` or `slack_username`).
- In `AdminView`, the `HttpResponse("err")` returned by views on a denied permission is never
  shown. Because `self.allowed` stays `False`, `dispatch` replaces it with a redirect to
  `admin.dash` plus an error message.
- The `.claude/worktrees/fix-docker-build` gitlink is a leftover. (`twisted/Procfile.tailwind`
  is still used: it is the honcho Procfile that `manage.py tailwind dev` runs.)
