# Blind-audit v2 invalidated before coding

**Status: INVALID FOR PRODUCTION PRECISION. DO NOT FIELD, LABEL OR SCORE.**

Discovered 2026-08-08, before any external or pilot label existed. This note
does not alter the frozen v2 registration, sheets or hashes; it records why
those bytes no longer license the study described in the registration.

## Frame defect

The registration describes 11 complete production score-days, each with 48
sampled Web NGrams snapshots. Ten registered receipt caches match their
same-day production score cache on sampled-snapshot and English-document
counts. The registered 2026-08-05 receipt cache does not:

| 2026-08-05 artifact | snapshots | English documents | SHA-256 |
|---|---:|---:|---|
| production score cache, `data/raw/ngram_days/2026-08-05.json` | 48 | 33,961 | `e426cd544daa8ad9d7b662ddee59eaf6ef518d6cf4e2f4780fe01b570e2d1458` |
| registered v2 receipt cache, `data/raw/receipt_days/2026-08-05.json` | 39 | 28,575 | `e78aeb3bc47b1980b6f05577a87487c72cd53fb1eaa055d28ddb26bd747abd55` |

The receipt frame therefore omits 5,386 documents from that day's production
scoring corpus. Forty-nine of the 500 scored rows come from the deficient
cache: 40 article-instance rows and nine title-cluster rows. By channel, those
rows are Pakistan/western border 10, China/eastern border 8, Gulf/energy 17,
US/trade 10 and shipping/chokepoints 4.

There is a second estimand defect. Production adds sub-query group shares, so a
document matching two groups contributes twice to the effective channel
numerator. V2 unions document keys before sampling and represents each such
document once. Across the registered sources, Pakistan has 287 group-qualified
contributions but 264 eligible unioned document keys, and Gulf has 8,178
contributions but 8,156 eligible unioned keys. Nine sampled article-instance
rows are multi-group documents. V2 can describe unique-document judgments in
its retained cache, but not precision for the exact quantity entering the
score.

## Consequence

The v2 package remains a reproducible record of its retained-cache draw, but it
is not a production-frame precision study and must not be sent to coders. No v2
row or future label may be reported as IGRM production precision, merged into a
later study or used to pass a quality gate. The adjacent registration remains
immutable evidence of what was frozen; this dated note supersedes its study
status and frame interpretation.

## Requirements for v3

A replacement may be frozen only after all of the following hold:

1. every source day is linked byte-for-byte to the exact cache used to produce
   that published score, with day, matcher, dictionary, located/loaded snapshot
   counts and missing snapshot IDs recorded;
2. the complete source frame passes exact cache/hash and denominator parity
   before sampling;
3. the primary score-contribution estimand samples group-qualified contribution
   instances with multiplicity, or a separately named unique-document estimand
   is reported without claiming it is the production numerator;
4. sample generation, coder packets and scoring are rebuilt from the frozen
   source snapshot in a clean environment and independently verified; and
5. the new registration, seed and all hashes are locked before any coder sees a
   pilot or scored row.

Until then, the only public precision artifact is the explicitly uncalibrated
machine/founder diagnostic in `docs/data/precision.json`; no independent human
precision result exists.
