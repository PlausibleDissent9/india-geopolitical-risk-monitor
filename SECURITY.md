# Security policy

IGRM's analytical surface is a static GitHub Pages site. It has no public
account system or server-side application runtime. That reduces one class of
attack surface; it does not make the project secure by declaration.

The machine-verifiable repository baseline is registered in
`governance/security_integrity_registry.json` and published, with explicit
limitations, at `docs/data/security_integrity.json`:

- **Workflow supply chain:** external actions use reviewed, immutable commit
  identities rather than moving version tags.
- **History and evidence:** every workflow checkout fetches the history needed
  to verify frozen registrations.
- **Token scope:** each workflow declares top-level permissions; only a small,
  registered set of dispatching lanes may request `actions: write`.
- **Publisher parity:** every publishing lane installs both pinned runtime and
  development requirements.
- **Credential isolation:** checkout does not persist a Git credential. The
  repository write token is passed only to the final publication step and is
  removed from the environment before repository code or the candidate gate
  executes.
- **Exact-candidate gate:** after every rebase and before every bot push, the
  shared publisher runs the full committed CI gate against the exact candidate
  commit. A red candidate is refused even when that loses a scheduled update.
- **Browser boundary:** pages carry a Content Security Policy; the project does
  not intentionally include third-party behavioral analytics or ad trackers.

These are repository controls, not a penetration test, security audit,
certification, availability guarantee, verification of founder-device or
GitHub-account security, or proof of branch/MFA/environment settings. See
`design/security_integrity_plane.md` for the threat boundary and next gates.

## Reporting

Found something? Email ishankrishna9@gmail.com with reproduction details and
the affected URL or commit. Good-faith reports are welcome. No response-time
SLA is claimed yet; acknowledgements and remediation timing will be measured
before any public service commitment is adopted.
