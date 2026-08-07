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

The valid package is v2: its seed, input hashes and output hashes are frozen in
`registration.json`. Tests independently reconstruct each channel's exact
production document-key frame, reject any sampled item outside it, and reject
URL deduplication as a substitute for the document instances the index counts.
