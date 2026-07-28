# Security policy

IGRM is a static open-data site (GitHub Pages) with a read-only public
surface: no accounts, no cookies, no server-side code, no collection of
visitor data. The attack surface is correspondingly small, and is kept
that way deliberately:

- **Transport:** HTTPS only (GitHub Pages TLS).
- **Content Security Policy** on every page: scripts restricted to
  same-origin plus cdnjs (Chart.js, pinned with a subresource-integrity
  hash); no third-party analytics or trackers of any kind.
- **Write access:** all authoring flows go through GitHub's own
  authentication (2FA-capable, fully audited); the site itself has no
  login surface to attack.
- **Supply chain:** Python dependencies are pinned exactly and updated
  via Dependabot; CI (ruff, mypy, pytest) gates every change.
- **Data integrity:** the pipeline refuses to publish stale or partial
  data, and every published file embeds its generation date.

## Reporting

Found something anyway? Email ishankrishna9@gmail.com with details.
Good-faith reports are welcome and will be acknowledged.
