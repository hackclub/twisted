# Frontend

Templates live in `twisted/twisted_site/templates/` (`client/`, `admin/`, `cotton/`) plus
`twisted/common/templates/base.html`. There is no JS bundler. Scripts are plain files
loaded with `{% static %}`, plus inline `<script>` blocks.

## Three template roots

| Root | Used by | Notes |
|---|---|---|
| `common/templates/base.html` (`{% extends "base.html" %}`) | `client/homepage.html` and `client/faqs.html` (logged-out pages) | blocks `head` and `body`; `<body class="font-vintage os">`; sets the `django_timezone` cookie with `cookieStore`; pages use `<c-homepage_taskbar />` |
| `client/osbase.html` | every desktop page and frame: `dashboard.html`, `discover`, `pathways`, `referrals`, `shop`, `projects/*`, `projects/journal/*` | blocks `css`, `js`, `extra_stuff` and `body`; loads marked, DOMPurify and `js/journal_markdown.js` (with `data-allowed-image-base="{% r2_public_url %}"`); defines `createWindow(title, src)` |
| `cotton/base.html` (`<c-base>`) | all admin pages (they use no `{% extends %}`) | dark zinc theme; `{% htmx_script %}`; `hx-headers` carries the CSRF token; sidebar comes from `sidebar_links`/`page`; `messages` render as `<c-ui.alert>`; context `error` becomes a toast; scripts load in the order cotton-ui JS, then Alpine collapse/focus, then Alpine core; slots `head` and default |

`projects/journal/new_journal.base.html` is the shared base for `new_hackatime.html` and
`new_untracked.html`. Its blocks are `links`, `journal_log_message`, `preform` and `form`.
`admin/pathways/listing.html` is a bare htmx fragment.

## Desktop "OS" (`client/dashboard.html`)

- Desktop icons call `newWindow(title, url)`. Each window is a clone of
  `<template id="window-template">` with an **iframe** that loads a full `osbase` page. This
  works because of `X_FRAME_OPTIONS = "SAMEORIGIN"`.
- Windows can be dragged (with pointer capture) and resized from 8 handles. They can be
  minimised, maximised and focused (z-index), and each has a taskbar button. The start menu
  shows the avatar, twists, links to Admin and Docs, and logout.
- **postMessage protocol.** Child frames send `{type: "internal", action, ...}` to the parent:
  - `open` takes `title` and `src`, and optionally `width` and `height`.
  - `close` takes `src`.
  - `refresh-projects` takes no extra fields.
  The parent checks `event.origin` and only opens same-origin http(s) URLs (`getSafeInternalUrl`).
  From a frame, prefer `createWindow(...)`.
- `startup_windows`, from the dashboard view's query params, are opened when the page loads.
- Music: `twistedly.mp3` autoplays. The paused preference is stored in localStorage, and a WebAudio
  visualiser animates the player.

## Components (django-cotton)

`<c-a.b_c>` maps to `cotton/a/b_c.html`. Components can read the parent context.

| Component | Purpose |
|---|---|
| `base`, `sidebar/index`, `sidebar/item` | admin layout. Sidebar icons come from `icons.hackclub.com` |
| `admin/dialog` | Alpine modal with a `trigger` slot and a `title` |
| `pathway_card` (admin), `client/pathway_card` (client) | pathway cards |
| `homepage_taskbar` | landing-page taskbar with a clock and music visualiser |
| `mdedit` | Markdown editor: Write/Preview tabs, a toolbar, image upload by paste or file picker, localStorage drafts under `mdedit-draft:<save_id>`. It uses fixed element ids, so a page can hold **only one** |
| `mdpreview` | renders the Markdown in its slot with `renderJournalMarkdown` |
| `project_ship_mark`, `ship_message`, `svg/tick`, `svg/cross` | ship status UI |

Admin pages also use django-cotton-ui `c-ui.*` components (button, card, tabs, table, input,
select, datepicker, badge, avatar, pagination, toast, alert, drawer, and others).

## JavaScript

- **Vendored libraries** (`static/vendor/`, see its README): marked, DOMPurify, Alpine (with
  collapse and focus) and Chart.js. **No runtime CDN JavaScript.** `tests/test_static_assets.py`
  fails if a page references `cdn.jsdelivr.net` or `gstatic.com` in scripts, so do not add CDN script tags.
  Update the libraries with `uv run manage.py update_vendor_assets` (add `--check` to only report).
  htmx is served by `django-htmx`.
- **Alpine and htmx are used on admin pages only.** Client pages use vanilla JS with `onclick=` handlers.
  Examples of htmx: live user search on `admin/users.html`, and shop-item editing in a popover on
  `admin/pathways/detail.html`.
- **Markdown** (`static/js/journal_markdown.js`): `renderJournalMarkdown(content, target)`
  calls `DOMPurify.sanitize(marked.parse(...))`. Any image whose URL does not start with the
  R2 public URL is replaced with an "External images are not supported" notice. This prevents IP
  logging; see migration 0054. Links get `target=_blank rel=noreferrer`.
- **Charts** (`static/js/admin_charts.js`): `areaChart(canvasId, dataId)` and `pieChart(...)`
  read `[["Label","Value"], ...]` from `{{ data|json_script:"id" }}`. Do not put JSON straight into inline JS.
- **Uploads:** JS POSTs `FormData` with `csrfmiddlewaretoken`, `file` and a `ref` (`journals`,
  `project_screenshot` or `shop_item`) to `{% url 'misc.upload_file' %}`.

## Tailwind

- Tailwind v4, built through django-tailwind (`TAILWIND_APP_NAME = "tailwindcsstheme"`) with
  PostCSS (`@tailwindcss/postcss`, `postcss-nested`, `postcss-simple-vars`).
- Sources are in `twisted/tailwindcsstheme/static_src/src/styles.css`. The output
  (`static/css/dist/styles.css`) is gitignored, so it has to be built:
  `uv run manage.py tailwind install` once, then `tailwind dev` / `tailwind start` (watch) or `tailwind build`.
- `styles.css` scans `**/*.{html,py,js}` plus a **hard-coded** venv path to the
  django_cotton_ui templates (`.venv/lib/python3.13/...`). If the Python version changes, update that path.
- `cotton-ui.sources.css` is generated by `manage.py cotton_ui_sources`. Do not edit it.
- Theme tokens (`@theme`): a purple palette (`background`, `foreground`, `card`, `primary`, `secondary`,
  `accent`, `muted`, `border`, `success`/`warning`/`destructive`, `twisted-200…999`).
  Fonts are `font-vintage` (local Pirkkala), `font-latin` (Figtree) and `font-symbol`. The `.resize-*`
  classes are used by the window resize handles.
- Scoping: client pages use the `.os` class with the purple tokens. Admin pages use `<body class="dark">`, which has its own
  overrides and the cotton-ui `ink-*`/zinc classes. Don't mix the two styles.
- `98.css` and `@tailwindcss/typography` are installed but never imported. Class names such as
  `sunken-panel` therefore do nothing.

## Template tags

- `maths`: `|divide:n`.
- `time_filters`: `|minutes_to_hours_minutes` (90 → `1h 30m`).
- `uploads`: `{% r2_public_url %}`.
- Also used: `humanize`, `humanizelib` (django-humanize), `mathfilters`, `tailwind_tags`,
  `django_htmx`, `tz`.

## Gotchas

- No CSP is configured. Inline scripts and handlers are everywhere.
- A few templates use `{{ info|safe }}` (`ship.html`, `journal/edit.html`,
  `new_journal.base.html`). Never put user input into `info`. Pass dynamic values to JS
  through `data-*` attributes or `json_script`.
- External images and fonts (icons.hackclub.com, assets.hackclub.com, Google Fonts, Slack/cachet
  avatars) are still loaded. Only journal Markdown is restricted to R2.
- `newWindow` uses `innerHeight - w` where it should use `h` for the random y position. It also has a leftover `console.log`.
