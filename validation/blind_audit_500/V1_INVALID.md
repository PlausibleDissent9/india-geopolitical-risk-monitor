# Blind-audit v1 is invalid — do not label or score it

Invalidated on 2026-08-07 before any external or pilot label existed.

The v1 sampler drew from the union of raw phrase matches. Production applies an
India anchor per document for Pakistan, China and US Trade before an article
enters a channel numerator. Because v1 omitted that step, some of its rows were
not eligible to be counted by the index and the draw could not estimate the
registered production matched-item precision.

Consequences:

- Never send a v1 sheet to a coder.
- Never merge v1 labels into v2.
- Never score or publish a result from v1.
- The original registration and files remain recoverable in git history for a
  complete correction trail.

`registration_v1_989c43f.json.ots` is retained only as historical evidence for
the invalid v1 registration (SHA-256
`a394918644686635443d424367e5806b863127987c6deb54d17b600d1ee25255`). It
does **not** timestamp or authenticate the adjacent v2 `registration.json`.
The adjacent `registration.json.ots` now stamps the exact v2 registration
(SHA-256 `c313c7a557be3788aea2724796c23ce7fa36a59fd0f381a395bf4a5c924a9b87`).
The v2 registration is also anchored by its full Git base commit and rebuilt
from those exact registered blobs by `scripts/verify_blind_audit_v2.py`; the
study itself is separately invalidated in `V2_INVALID.md`.

The replacement package was v2: its seed, input hashes and output hashes remain
frozen in `registration.json`. Tests independently reconstruct its retained
document-key frame, reject any sampled item outside it, and reject
URL deduplication as a substitute for the document instances the index counts.
