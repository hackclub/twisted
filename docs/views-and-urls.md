# Views and URLs

Every route is in `twisted/twisted_site/urls.py`. Always use the URL **names** with
`redirect()`, `resolve_url()` or `{% url %}`.

## Public and auth

| Path | Name | View |
|---|---|---|
| `/` | `homepage` | `client.HomepageView`: landing page with the login button; stores the `?ref=` cookie |
| `/faqs/` | `faqs` | `client.FaqsView` |
| `/auth/login/` (POST) | `login` | redirect to HCA |
| `/oauth/callback/` | `auth_callback` | HCA callback |
| `/oauth/hackatime_callback/` | `hackatime_callback` | Hackatime callback |
| `/auth/logout/` (POST) | `logout` | |
| `/api/upload_image/` (POST) | `misc.upload_file` | R2 image upload |
| `/api/ari/` (POST) | `ari` | Ari webhook |
| `/health`, `/health/` | `health`, `health-slash` | 204 (defined in `mysite/urls.py`) |

## Client desktop and frames

`/dashboard/` (`DashboardView`) renders the desktop shell (`client/dashboard.html`).
App windows load **frame** pages from `/dashboard/frame/...`. Their URL names start with `fr.`.
These frame pages extend `client/osbase.html` and are not full-site pages.

The desktop can open windows at startup from query parameters:
- `?project=<id>` opens that project's detail window. Slack messages and Ari metadata
  link to `/dashboard/?project=<id>`.
- `?windows=<name>` (can be repeated) opens `fr.<name>`. Add `&fullscreen_win=1` to make the windows fullscreen.
- `?discover` opens the discover window.

| Path under `/dashboard/frame/` | Name | View |
|---|---|---|
| `projects/` | `fr.projects` | `ListProjects`: the user's own projects |
| `projects/create/` | `fr.projects.create` | `CreateProject` |
| `projects/<project_id>/` | `fr.projects.detail` | `ProjectDetail`: public. Ships and reviewer feedback are shown only to the owner, along with the live Ari status |
| `projects/ship/<project_id>/` | `fr.projects.ship` | `SubmitProject` |
| `projects/<project_id>/settings/` | `fr.projects.settings` | `ProjectSettings`: name, description, type, Hackatime projects, URLs |
| `projects/<project_id>/journals/new/hackatime/` | `fr.projects.journals.new.hackatime` | |
| `projects/<project_id>/journals/new/untracked/` | `fr.projects.journals.new.untracked` | hardware projects only |
| `journals/delete/<journal_id>/` | `fr.projects.journals.delete` | untracked journals only |
| `journals/edit/<id>/` | `fr.projects.journals.edit` | |
| `pathways/` | `fr.pathways` | `PathwaysView` |
| `pathways/<pathway_id>/unlock/` (POST) | `fr.pathways.unlock` | |
| `referrals/` | `fr.referrals` | |
| `discover/` | `fr.discover` | every project, paginated 120 per page |
| `shop/` | `fr.shop` | `ShopView`. POST `action` = `setRegion`, `deposit` or `purchase` |

## Admin panel (`/admin/...`)

This is a custom panel; `django.contrib.admin` is not installed. Every view subclasses
`views/admin/admin.py::AdminView`:

- `dispatch` redirects anonymous users to `homepage` and non-staff (`profile.is_staff`) to
  `dashboard`. It creates an empty `ProfileStaffPermissions` if the user has none, and
  builds `self.audit_log`, which it **saves after every request**.
- **Permission pattern:** a handler checks `self.perms.<flag>`. If the check passes, it sets
  `self.allowed = True`. Otherwise it returns anything, and `dispatch` sees `allowed == False`,
  records the denial and redirects to `admin.dash` with an error message. **Forgetting
  `self.allowed = True` makes a page inaccessible. Setting it before the check leaks access.**
- Call `self.get_context_data(page=..., subpage=...)` to get the sidebar (filtered by permissions) and the `profile`.
- Add details to `self.audit_log.additional_context` (a dict), and set `self.audit_log.pii = True`
  when the request touches personal data. An `additional_context` key ending in `__img` is
  rendered as an image in the logs view.

| Path | Name | Permission | Notes |
|---|---|---|---|
| `/admin/` | `admin.dash` | any staff | Chart.js analytics: hours logged and shipped, by type and by country. One grouped query over journals; it charts the cached `Profile.country` and never calls HCA. Expired countries (up to 50 per load) are refreshed by the `tasks.refresh_profile_countries` background task |
| `/admin/users/` | `admin.users` | `view_users` | search; POST `logoutall` (needs `superuser`) deletes every session |
| `/admin/users/<user_id>/` | `admin.users.detail` | `view_users` / POST `superuser` | `toggle_is_allowed` (responds with an HX-Trigger toast), `change_permissions`, `make_admin`, `remove_admin` |
| `/admin/projects/<project_id>/` | `admin.projects.detail` | `view_projects` | shows journal create/edit/delete buttons with `manage_journals` |
| `/admin/projects/<project_id>/journals/new/` | `admin.journals.create` | `view_projects` + `manage_journals` | staff journal form: type, content, minutes worked, approved (`reduced_`) minutes. Skips the participant limits and the ship lock |
| `/admin/journals/<journal_id>/` | `admin.journals.edit` | `view_projects` + `manage_journals` | same form; the audit log stores the before/after minutes, not the text |
| `/admin/journals/<journal_id>/delete/` (POST) | `admin.journals.delete` | `view_projects` + `manage_journals` | |
| `/admin/pathways/` | `admin.pathways` | `view_pathways` | |
| `/admin/pathways/new/` | `admin.pathways.create` | `manage_pathways` | dates are interpreted in the current (cookie) timezone, each with its own UTC offset (DST-safe) |
| `/admin/pathways/<pathway_id>/edit/` | `admin.pathways.edit` | `manage_pathways` | edit name, start/end and minimum minutes (same form and parsing as create); the audit log stores before/after |
| `/admin/pathways/<pathway_id>/` | `admin.pathways.detail` | view `view_pathways`, POST `manage_shop` | participants, and `new_listing` with per-region prices |
| `/admin/pathways/_shopitems/<listing_id>/` | `admin.pathways.shopitems` | view `view_pathways`, POST `manage_shop` | edit an item; an empty price removes that region's pricing |
| `/admin/fulfillment/` | `admin.fulfillment` | `manage_fulfillments` | `?status=` filter; POST `fulfill` / `reject` (reject refunds) |
| `/admin/shop/` | `admin.shop` | `manage_shop` | |
| `/admin/shop/regions/` | `admin.shop.regions` | `manage_shop` | `create` / `update` / `delete` (deleting a region with prices fails) |
| `/admin/review/` | `admin.review` | `view_review` / POST `manage_review` | real review happens in Ari; with `DEBUG_REVIEW`, a local editor |
| `/admin/announcements/` | `admin.announcements` | `manage_announcements` | placeholder page |
| `/admin/logs/` | `admin.logs` | `view_auditlogs` | 100 per page; `?context_mode=true` hides entries with no context |

Admin list pages must not call per-row model helpers such as `Profile.time_logged()`,
`shipped_projects()` or `Project.latest_ship()` in a loop: each runs several queries per row.
Annotate instead. `models.latest_ship_status(project_ref)` is a subquery for the latest ship
status, `models.status_is_shipped()` interprets it, and `views/admin/users.py::with_project_stats`
attaches per-user project totals in one query.

## Adding a view

1. Put it in the right `views/client/*.py` or `views/admin/*.py` module and export it from that
   package's `__init__.py` (`__all__`).
2. Add the route to `twisted_site/urls.py`, with an `fr.` prefix for desktop frames and `admin.` for staff pages.
3. Client views need the anonymous redirect and ownership checks. Admin views need the
   `allowed` pattern described above.
4. Add tests in `twisted_site/tests/`.
