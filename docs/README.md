# Twisted project docs

These are notes on how the codebase works, for contributors and coding agents. Start with
[`../AGENTS.md`](../AGENTS.md) for the short version.

| Doc | Contents |
|---|---|
| [architecture.md](architecture.md) | repo layout, stack, settings and env vars, request conventions, deployment, known oddities |
| [domain-model.md](domain-model.md) | models, currencies, journals, shipping, pathways, shop and referral rules |
| [views-and-urls.md](views-and-urls.md) | every route, desktop frames, the `AdminView` permission and audit pattern, how to add a view |
| [integrations.md](integrations.md) | Hack Club Identity, Hackatime, Ari review webhooks, Slack, Cloudflare R2 |
| [frontend.md](frontend.md) | template roots, the desktop window system, cotton components, JS, Tailwind |
| [testing.md](testing.md) | running tests, CI, ruff rules, mocking conventions, migrations |

Keep these docs current. When code changes behaviour described here, update the matching doc
in the same change.
