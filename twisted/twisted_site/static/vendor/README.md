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

Licenses: marked (MIT), dompurify (MPL-2.0 or Apache-2.0), chart.js (MIT), Alpine.js and
its plugins (MIT) — license files are kept next to each vendored file where the package
ships one. Alpine's npm tarballs do not include a license file; the builds carry the MIT
attribution inline.

`htmx` is not vendored here: admin pages use `{% htmx_script %}` from `django-htmx`,
which serves the htmx build bundled with that package. The client pages do not use htmx.

## Updating

```bash
mkdir -p /tmp/vendorpack && cd /tmp/vendorpack
npm pack marked@<version> dompurify@<version> alpinejs@<version> \
    @alpinejs/collapse@<version> @alpinejs/focus@<version> chart.js@<version>
tar -xzf <package>.tgz
cp package/<source file> twisted/twisted_site/static/vendor/<path>
```

Then update the table above.
