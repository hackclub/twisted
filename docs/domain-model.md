# Domain model and game rules

All models live in `twisted/twisted_site/models.py`. Users are the stock
`django.contrib.auth` `User`. **Usernames are the HCA `sub` with `!` replaced by `_`.**
Everything app-specific hangs off `Profile` (a one-to-one with `User`, `related_name="profile"`).

## Models

| Model | Key fields / relations | Notes |
|---|---|---|
| `Profile` | `user` (1:1), `slack_id`, `slack_username`, `slack_pfp_url`, `verification_status`, `ysws_eligible`, `hca_access_token`, `hackatime_access_token`, `hackatime_state`, `is_allowed`, `is_staff`, `staff_permissions` (1:1, nullable), `twists`, `referred_by` (self FK, `related_name="referrals"`), `my_referral_code`, `country` + `country_cached_until`, `region` (FK `ShopRegion`) | `get_country()` returns the cached country, or calls `refresh_country()` (HCA, cached for `COUNTRY_CACHE_TTL` = 3 h, falling back to `"Unknown"`) once it has expired. `time_logged()` / `time_shipped()` sum the `reduced_minutes` of journals. `add_currency` / `remove_currency` are atomic and write a `CurrencyLog` row. |
| `CurrencyLog` | `profile`, `old_balance`, `difference`, `note`, `created_at` | Ledger for `Profile.twists`. Never change `twists` without going through `add_currency` / `remove_currency`. |
| `ProfileStaffPermissions` | booleans: `superuser`, `view_users`, `view_projects`, `manage_journals`, `view_pathways`, `manage_pathways`, `manage_fulfillments`, `manage_shop`, `view_review`, `manage_review`, `manage_announcements`, `view_auditlogs` | The admin UI derives its list of editable permissions from the model's `BooleanField`s, so adding a field adds a toggle automatically. |
| `Project` | `user`, `project_name` (≤50), `project_description` (≤2000), `project_type` (`software`/`hardware`), `hackatime_project_names` (JSON list), `repo_url`, `playable_url` (≤200), `screenshot_url` (≤500) | The length limits are module constants (`PROJECT_*_MAX_LENGTH`). The model, the client settings form and the Ari webhook validator all use them. `is_shipped()` means the latest ship exists and is not `requested_changes`. `is_approved()` means the latest ship is `approved`. |
| `Journal` | `project`, `type` (`hackatime`/`lookout`/`untracked`), `content` (Markdown), `minutes_worked`, `reduced_minutes` | `reduced_minutes` is the amount that counts. `minutes_worked` is the raw amount. `lookout` exists in the choices but nothing creates it. |
| `ProjectShip` | `project`, `status`, `note_to_maker`, `audit_note`, `technical_features`, `deflation_reason`, `final_status`, `final_note_to_maker`, `final_audit_note` | Statuses: `pending`, `requested_changes`, `rejected`, `approved`. The `final_*` fields hold the second-pass (organizer) decision. |
| `Pathway` | `name`, `min_mins` (default 300), `start`, `end` | A time-boxed challenge with its own shop. Helpers: `in_progress()`, `ended()`, `didnt_start()`, `get_unspent_mins(user)`, `mins_spent(user)`, `qualified_participants()`, and atomic `add_currency` / `remove_currency` for golden twists. |
| `PathwayTimeSpent` | `pathway`, `user`, `unlocked`, `minutes`, `golden_twists`; unique (`pathway`, `user`) | A user's membership in a pathway and their golden-twist balance in it. |
| `PathwayCurrencyLog` | `pathway_ts`, `old_balance`, `difference`, `note` | Ledger for golden twists. |
| `ShopRegion` | `name` | Users pick a region. Prices are per region. |
| `ShopItem` | `pathway`, `item_name`, `item_description`, `stock` (default 999), `image_url` | Every item belongs to a single pathway. |
| `ShopItemRegionalPricing` | `region`, `item`, `price` | An item without a price for the user's region is hidden from that user. |
| `ShopOrder` | `user`, `item`, `pathway`, `region_name`, `price_paid`, `status` (`pending`/`fulfilled`/`rejected`), `staff_note` | Created by a purchase and resolved in admin fulfillment. |
| `UploadedFile` | `uploaded_by`, `link`, `cdn_response`, `uploaded_thru`, `filesize` | One row per R2 upload. |
| `AuditLog` | `user`, `path`, `post`, `pii`, `additional_context` (JSON), `timestamp` | Every admin request writes one, including denied requests (`additional_context["allowed"] = False`). |
| `AriWebhookDelivery` | `delivery_id` (unique) | Lets the webhook skip deliveries that Ari retries. |

Most foreign keys use `on_delete=PROTECT`. Deleting users, projects, regions or other rows that
something references raises `ProtectedError`.

## Game rules (as implemented)

### Journals (`views/client/journal.py`)
- **Hackatime journals** (the only kind for software projects): the minutes come from Hackatime. The
  amount available is `Project.hackatime_time_unjournaled()`, which is Hackatime time on the linked
  Hackatime projects since 2026-09-07 minus the `minutes_worked` of existing hackatime journals.
  The cap is `999*60` minutes.
  - The entry needs `ceil(max(1, minutes/180))` Markdown images (`![...](...)`).
  - It needs at least `min(100, minutes // 3)` characters of prose. Image Markdown is not counted, and whitespace runs count as one character.
- **Untracked journals** (hardware projects only): the user enters the minutes, from 0 to 180.
  The prose requirement is `min(100, minutes*2)`. The view warns about "time deflation".
  These are the only journals a user can delete.
- Editing a journal changes only `content`. The edit is re-validated against the image and prose rules for the existing `reduced_minutes`.
- No journal can be created, edited or deleted after the project is shipped.

### Shipping (`views/client/project.py::SubmitProject`)
Requirements: the user owns the project, `playable_url` and `screenshot_url` are set,
`profile.ysws_eligible` is true (that is, the user has passed ID verification), the project has at
least 60 logged minutes, and Ari is configured. The view creates a `ProjectShip` and calls
`ari.send_ship`. If the send fails, it deletes the ship.

### Review lifecycle
Ari sends webhooks that update the latest ship (see [integrations.md](integrations.md)).
`requested_changes` unlocks the project for editing again. A reviewer note containing
`!reship` automatically creates and submits a new ship, and `!silent` suppresses the
Slack DM to the maker.

### Currencies
- **Twists** (`Profile.twists`) are the main currency. `TWISTS_PER_HOUR = 50` is defined but
  **no code currently awards twists**. Data migrations 0046 and 0052 reset the balances.
  `tests/test_economy.py::TwistEarningTests` still expects `Profile.twists_earned()` and
  `Profile.refresh_twists()`, which earned 50 twists per hour of `reduced_minutes`; both methods
  have been removed. Any new awarding logic should go through `Profile.add_currency`.
- **Golden twists** (`PathwayTimeSpent.golden_twists`) exist per pathway. Users deposit
  twists into an unlocked pathway at 1:1 (`ShopView.deposit`). Items are paid for in golden twists.

### Pathways (`views/client/pathways.py`)
- A user unlocks a pathway that is in progress when `get_unspent_mins(user) >= min_mins`. Unspent
  minutes are total logged minutes minus the minutes already committed to other pathways.
  Unlocking sets `PathwayTimeSpent(unlocked=True, minutes=min_mins)`.
- The shop lists only pathways the user has unlocked whose start date has passed.

### Shop and fulfillment
- Purchase (`ShopView.purchase`) runs in one transaction with `select_for_update`. It checks
  that the pathway is unlocked, the item is in stock, the user has a region, a regional price
  exists and the golden-twist balance covers it. It then decrements stock, debits golden twists
  and creates a `ShopOrder`.
- In admin fulfillment, rejecting an order restores the stock and refunds the golden twists.

### Referrals
`/?ref=CODE` sets a `referral` cookie that lasts one hour. On the user's **first** login,
`AuthCallbackView` sets `profile.referred_by` from that cookie. A user's own 12-character
code is generated the first time they open the referrals frame.

## Creating a local admin

See the README. In `uv run manage.py shell`, set `profile.is_staff = True` and attach a
`ProfileStaffPermissions` with every flag set to true.
