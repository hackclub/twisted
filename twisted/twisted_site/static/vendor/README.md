# Vendored frontend dependencies

These files are checked into the repository so that pages never load JavaScript from a
third-party CDN at runtime (no SRI pinning, CDN outage or upstream-compromise risk).
Update them deliberately, not automatically.

| File | Package | Version | Source file |
|---|---|---|---|
| `marked/marked.umd.js` | [marked](https://www.npmjs.com/package/marked) | 18.0.14 | `lib/marked.umd.js` |
| `dompurify/purify.min.js` | [dompurify](https://www.npmjs.com/package/dompurify) | 3.4.16 | `dist/purify.min.js` |
| `alpine/alpine.min.js` | [alpinejs](https://www.npmjs.com/package/alpinejs) | 3.17.4 | `dist/cdn.min.js` |
| `alpine/collapse.min.js` | [@alpinejs/collapse](https://www.npmjs.com/package/@alpinejs/collapse) | 3.17.4 | `dist/cdn.min.js` |
| `alpine/focus.min.js` | [@alpinejs/focus](https://www.npmjs.com/package/@alpinejs/focus) | 3.17.4 | `dist/cdn.min.js` |
| `chart.js/chart.umd.min.js` | [chart.js](https://www.npmjs.com/package/chart.js) | 4.5.1 | `dist/chart.umd.min.js` |

The updater writes the license files shipped by each package next to
the vendored file, but this repository's `.gitignore` excludes `LICENSE*` files, so they
are not tracked here; Alpine's npm tarballs do not ship one at all (the builds carry the
MIT attribution inline).

`htmx` is not vendored here: admin pages use `{% htmx_script %}` from `django-htmx`,
which serves the htmx build bundled with that package. The client pages do not use htmx.

## Updating

Use the management command (it downloads from the npm registry directly, so npm/node are
not required):

```bash
uv run manage.py update_vendor_assets          # update every asset to its latest release
uv run manage.py update_vendor_assets --check  # report outdated assets, exit 1 if any
```

It copies each package file listed above, strips `sourceMappingURL` comment lines, copies
the license files that exist, and rewrites the version table below. Major version bumps
are flagged: review the changelog, then run the test suite and a production-mode
`collectstatic` before committing.

To do it by hand instead:

```bash
mkdir -p /tmp/vendorpack && cd /tmp/vendorpack
npm pack marked@<version> dompurify@<version> alpinejs@<version> \
    @alpinejs/collapse@<version> @alpinejs/focus@<version> chart.js@<version>
tar -xzf <package>.tgz
cp package/<source file> twisted/twisted_site/static/vendor/<path>
# then remove the trailing "//# sourceMappingURL=..." line and update the table below
```
