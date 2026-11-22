# External integrations

All of them are plain `requests` / SDK calls with `timeout=10`. Tests mock them (see
[testing.md](testing.md)). None of them should be called for real in tests.

## Hack Club Identity (HCA): login (`views/client/auth.py`, `hca.py`)

- OIDC via authlib. The client is registered as `oauth.hca` with metadata from
  `https://auth.hackclub.com/.well-known/openid-configuration`.
- `POST /auth/login/` redirects to HCA. If the user is already logged in and has a Hackatime token, it redirects to the dashboard instead.
- `GET /oauth/callback/` (`AuthCallbackView`) runs these steps:
  1. Applies the `LOGIN_ENABLED` gate.
  2. Exchanges the code for a token.
  3. Requires `sub` and `slack_id` (users without a linked Slack account are rejected).
  4. Gets or creates the `User` (username = `sub` with `!`→`_`) and the `Profile`.
  5. Looks up the Slack display name with `users_info`. The avatar is always
     `https://cachet.hackclub.com/users/<slack_id>/r`.
  6. Stores `verification_status`, `ysws_eligible` and `hca_access_token`.
  7. Applies the referral cookie (first login only) and the `maybe` gate, then calls `login()`.
  8. Generates `hackatime_state` and redirects to Hackatime OAuth.
- `hca.get_user_data(token)` calls `GET /api/v1/me` and returns an `Identity` dataclass that includes the
  addresses. `Profile.get_country()` uses it. When `AUTH_DEBUG` is on, it returns a fixed fake identity.

## Hackatime: time tracking (`hackatime.py`)

- OAuth: `GET /oauth/hackatime_callback/` compares the `state` with `profile.hackatime_state` using
  `hmac.compare_digest`. It exchanges the code at `https://hackatime.hackclub.com/oauth/token`, calls
  `hackatime.me()`, and **requires the Hackatime `slack_id` to match the profile's**.
  Only then does it store `hackatime_access_token`.
- `hackatime.projects(token, start=2026-09-07 UTC)` returns `HackatimeProject` entries
  (name, total_seconds, most_recent_heartbeat, languages). Only time after the program
  start date counts.

## Ari: project review (`ari.py`, `views/ari.py`)

Docs: https://ari.hackclub.com/docs/webhooks. There are two separate secrets:
- `ARI_SIGNING_SECRET` signs **outbound** requests. A POST carries an `X-Ari-Signature`
  header, the HMAC-SHA256 hex digest of the body. A GET sends `Authorization: Bearer <secret>`.
- `ARI_WEBHOOK_SECRET` verifies **inbound** deliveries. The signature is
  `HMAC(secret, f"{timestamp}.{delivery_id}." + body)`, compared against `X-Ari-Signature`, with
  `X-Ari-Timestamp` (at most 5 minutes old) and `X-Ari-Delivery-Id`. An empty secret means every
  delivery is rejected.

Outbound:
- `send_ship(ship)` POSTs to `ARI_INGEST_ENDPOINT` with these fields: `external_id = "twisted-<project.id>"`, maker
  (email, Slack name and id), title, description, repo/demo/thumbnail URLs, `track` (the project
  type), Hackatime project names, every journal (with `minutes`, which is the reduced minutes for
  untracked journals and 0 for the rest), and links to the project and its admin page.
  It does nothing when `DEBUG_REVIEW` is on.
- `get_project_status(project)` calls `GET <endpoint>/status?external_id=...`.
  `ship_passes_from_status()` maps Ari's `phase`/`decision` to a pair (first pass, second pass) of
  `PROJECT_SHIP_STATUSES` values for the project detail page.

Inbound (`POST /api/ari/`, CSRF-exempt, in `AriView`):
1. Returns 503 if there is no webhook secret and 401 if the signature is bad. Returns 200 "Delivery already processed" if the delivery
   id has been seen before. Returns 400 for malformed JSON or for a payload that fails validation (`_InvalidPayloadError`).
2. Resolves the project from `external_id`, then dispatches on `event`:
   - `ship.updated` overwrites the project fields from `ship`. URLs go through
     `sanitize_http_url` and are dropped if they are too long. The title is trimmed to the model limit.
     The maker gets a DM listing the `changes`.
   - `review.changes` (with `decision == "changes"`) sets the latest ship to `requested_changes`.
     It handles the `!silent` and `!reship` flags in the note. For `!reship` it enqueues the
     `send_ship_after_delay` task, which uses `django.tasks`.
   - `review.approved` / `review.rejected` set the status, notes and justification fields.
   - `review.reverted` sets the ship back to `requested_changes` with a note, and `review.requeued` sets it back to `pending`.
   - A changed decision resets `final_status` to `pending`.
   - The maker is DMed through `_notify_maker`. A Slack failure does not fail the webhook.
3. The delivery id is recorded only **after** the event has been applied successfully, so Ari can retry after a crash.

Set `DEBUG_REVIEW=true` locally to skip Ari completely. `/admin/review/` then becomes a form
where you can set ship statuses yourself.

## Slack (`slack.py`)

- `slack_bot = WebClient(token=SLACK_TOKEN)` is created at import time.
- `log_to_channel(msg)` posts to `SLACK_LOG_CHANNEL`. It never raises; errors are logged.
  It is used for logins, project creation and setting changes, journals, ships, orders and fulfillment.
- `send_blocks(channel=..., blocks=..., text=...)` sends Block Kit messages. Maker DMs use their `slack_id` as the channel.
- `escape_mrkdwn(text)` escapes `& < >`. **Always** pass user text through it, to prevent
  `<!channel>` pings and link spoofing.

## Cloudflare R2: image uploads (`views/image_upload.py`)

- `POST /api/upload_image/` (`@login_required`) takes a `file` and an optional `ref` (stored as `uploaded_thru`).
- Validation: the content type must be png/jpeg/webp/gif and the size at most 10 MB (a server-side limit). Pillow then
  `verify()`s the image, and the detected format must match both the content type and the file extension.
- The file is stored as `<uuid4>-<size>/<slugified-stem><ext>` in `R2_BUCKET`. The public link is
  `R2_PUBLIC_URL/<key>`. A `UploadedFile` row is created.
- The JSON response is `{"status": "ok", "link", "name", "response"}` on success and `{"status": "error", "reason"}` on failure.
  Note that errors are returned with HTTP 200.
- Migration 0054 blocks external images in journals, which stops an embedded image from logging readers' IPs. Journal images are expected to
  be R2 uploads. See [frontend.md](frontend.md) for how rendering enforces this.
