# Testing, linting and CI

## Running tests

Tests need a **real PostgreSQL**: `tests/test_harness.py` asserts `connection.vendor == "postgresql"`.

```bash
cd twisted
docker compose up -d db           # postgres:16 on localhost:5432 (needs POSTGRES_* in twisted/.env)
uv run manage.py test --settings mysite.test_settings
uv run manage.py test twisted_site.tests.test_journals --settings mysite.test_settings   # a single module
```

`mysite/test_settings.py` `setdefault`s a complete fake environment (Postgres
`django/django@127.0.0.1:5432`, dummy secrets, `R2_PUBLIC_URL=https://example.invalid/uploads`,
`LOGIN_ENABLED=true`) and then imports `mysite.settings`. Because that sets `ALLOWED_HOSTS`, **`.env` is not
loaded during tests**. Real shell env vars take precedence. The test settings also turn off `DEBUG`, `DEBUG_REVIEW`
and the secure-cookie and SSL-redirect settings, remove whitenoise, and use MD5 hashing and plain `StaticFilesStorage`.

## CI (`.github/workflows/`)

- `tests.yaml` runs on push and PR with a Postgres service (`twisted_test` credentials):
  ```bash
  uv sync --frozen --dev
  uv run python twisted/manage.py check --settings=mysite.test_settings
  uv run python twisted/manage.py makemigrations --check --dry-run --settings=mysite.test_settings
  uv run coverage run twisted/manage.py test twisted_site common --settings=mysite.test_settings --verbosity 2
  ```
  **Model changes without a migration fail CI.**
- `ruff-check.yaml` runs `ruff check` (unpinned ruff, Python 3.13). Run it locally with `uvx ruff check` from
  the repo root.
- Pyright and pyrefly are configured in `pyproject.toml` but are **not** run in CI. The code still
  carries their ignore comments, so keep new code type-clean.
- `.github/dependabot.yml` has `package-ecosystem: ""`, so version updates are not configured.
  The grouped uv bump PRs in the git history probably come from Dependabot security updates, which are enabled in the repo settings.

## Ruff configuration

The config is in `pyproject.toml`. It sets `extend-select = ["ALL"]` and `line-length = 100`, but E501 is ignored. These rules are ignored too:
A002, C901, CPY001, D100–D104, D107, D203, D212, D401, PLC0415, PLR0911/0912/0915, S102 and S105.
Migrations are fully exempt. Tests also skip PT009, PT027 and S106. In practice this means:
- annotate every function;
- assign discarded return values to `_` (`_ = obj.delete()`), as the code does everywhere;
- define error messages in a variable before `raise` (EM101/TRY003), e.g. `err = "..."; raise ValueError(err)`;
- use `@override` (from `typing`) on overridden methods.

## Test conventions

- Tests are Django `TestCase`s in `twisted/twisted_site/tests/test_*.py`. There are no factories or shared base classes. Each
  class builds its fixtures in `setUp` (`User.objects.create_user`, `Profile.objects.create`,
  `ProfileStaffPermissions.objects.create(...)` for admin access, and `self.client.force_login`).
- Class attributes are annotated with `# pyright: ignore[reportUninitializedInstanceVariable]`.
- External services are mocked with `unittest.mock.patch` **where the code under test uses them**:
  - Slack: `twisted_site.views.client.project.log_to_channel`, `twisted_site.views.ari.send_blocks`, `twisted_site.views.client.auth.slack_bot.users_info`.
  - Hackatime: `twisted_site.hackatime.requests.get`, `patch.object(Project, "get_hackatime_projects")`, `views.client.auth.hackatime.me`.
  - HCA: `views.client.auth.oauth.hca.authorize_access_token`, `twisted_site.models.hca.get_user_data`.
  - Ari: `twisted_site.ari.ARI_WEBHOOK_SECRET` etc. (module constants), `twisted_site.ari.time.time`, `views.client.project.ari.send_ship` / `.is_configured`.
  - R2: `views.image_upload.s3` / `file_uploader`.
- Env flags are toggled with `patch.dict(os.environ, {"LOGIN_ENABLED": "maybe"})`, and settings with
  `@override_settings(DEBUG_REVIEW=True)`.
- To test a data migration, keep its logic in module-level functions and test them via
  `import_module("twisted_site.migrations.00NN_name")` (see `test_block_external_images_migration.py`).

## Test files

| File | Covers |
|---|---|
| `test_admin.py` | admin access by staff flag and permission, superuser actions, audit logs, constant query counts for the dashboard and user pages, background country refresh |
| `test_admin_journals.py` | staff journal create/edit/delete, validation, `manage_journals` checks, audit context |
| `test_admin_workflows.py` | pathway create/edit (including DST offsets), shop listing and region CRUD with validation, pathway list query count |
| `test_ari.py` | webhook signature verification, status mapping, every webhook event, duplicate deliveries, URL sanitising |
| `test_ari_client.py` | outbound Ari client, `send_ship` payload, `DEBUG_REVIEW` skipping submission |
| `test_auth.py` | Hackatime OAuth callback |
| `test_auth_callbacks.py` | HCA callback, referrals, the `LOGIN_ENABLED` modes, avatar fallback, login and logout |
| `test_block_external_images_migration.py` | migration 0054 |
| `test_client_workflows.py` | project creation, project lists, referrals, region selection, project visibility |
| `test_economy.py` | twist earning, deposits, purchases, fulfillment and refunds |
| `test_harness.py` | test settings safety, `/health`, Postgres and migrations applied |
| `test_image_upload.py` | upload validation and the R2 key |
| `test_integrations.py` | Hackatime and HCA HTTP clients |
| `test_journals.py` | journal create/edit/delete rules |
| `test_middleware.py` | `TimezoneMiddleware` |
| `test_models.py` | time accounting, ship state, pathway lifecycle |
| `test_pathways_view.py` | pathway grouping and unlock |
| `test_profile.py` | `get_country` caching and failures |
| `test_project_settings.py` | settings validation, Hackatime failure |
| `test_slack.py` | Slack helpers and escaping |
| `test_static_assets.py` | vendored JS only (no CDN), `json_script` chart data, `data-allowed-image-base` |
| `test_submission.py` | shipping rules and rollback when Ari fails |
| `test_template_tags.py` | custom filters |
| `test_url_validation.py` | `validation.py` |
| `test_vendor_update.py` | the `update_vendor_assets` command |

**Known issue:** `test_economy.TwistEarningTests` calls `Profile.twists_earned()` and
`Profile.refresh_twists()`. Neither method exists in `models.py`; they were removed in the
"Currency overhaul" commit (`5551b4b`). These tests fail with an `AttributeError` until the
twist-earning logic (50 twists per hour, `TWISTS_PER_HOUR`) is implemented again or the tests
are updated.

## Migrations

- `twisted_site/migrations/` contains 0001–0054. Keep a single leaf node.
- There are two files numbered 0034, the squash `0034_pathwaygroup_squashed_0036_...` and
  `0034_profile_country...`, and two empty merges numbered 0036. `0039` merges again.
  Do not "clean these up": production databases have already applied them.
- Data migrations: 0033 (Hackatime name to list), the squash plus 0035 (PathwayGroup added, then
  removed), 0043 (sanitize project URLs), 0046 and 0052 (reset twists and golden twists, irreversible), 0053
  (cachet avatar URLs), and 0054 (block external journal images; reads `R2_PUBLIC_URL`).
- In data migrations, use `apps.get_model` and give a reverse function (`RunPython.noop` is acceptable).
