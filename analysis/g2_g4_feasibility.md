# G2/G4 feasibility note (2026-08-06)

## G2 — front-page share (Frontpage Graph)

**Verified: the GFG exists in BigQuery as `gdelt-bq.gdeltv2.gfg_partitioned`**
(GDELT's own announcement and BigQuery posts; 50,000 homepages scanned
hourly; 100B+ outlinks in year one, 4.6TB then and growing — GDELT's
own guidance: "make absolutely certain to use table decorators").

Design implication, from the scale numbers: a naive per-day scan is
NOT free-tier-compatible. One day of GFG is on the order of hundreds
of millions of rows; even two-column partition-scoped scans plausibly
run 10–50GB per query-day, versus the 3GB cap the tone lane runs
under and a 1TB/month free tier. The honest build order:

1. **One capped probe query first** (CI lane, `maximum_bytes_billed`
   at 5GB, dry-run estimate logged): measure the real bytes for one
   day's join of our matched URLs against `LinkID`. Numbers before
   design.
2. If the probe passes: G2 runs **on spike days only** (episode
   detection already names them), not daily — front-page placement is
   an episode-anatomy question, and per-episode queries keep the
   annual cost bounded and reported.
3. If it fails the cap: G2 publishes as "measured infeasible under
   the stated budget discipline" in this note, which is a finding.

## G4 — narrative composition (GKG themes)

Same shape as the shipped tone lane (G1): partition-scoped
`gkg_partitioned`, `V2Themes` column, URL-join against the day's
matched articles — no new selection, themes as annotation. Affordable
per-episode by construction (same cap as G1). Build order: after G2's
probe establishes the query-cost baseline, G4 reuses the identical
join with one more column. Theme decomposition publishes per episode
beside the V6 term attribution, descriptive only, entering no score.

## What this note refuses

Guessed table names, unmeasured cost claims, and any daily-cadence
design for a 100-billion-row table. The probe's measured bytes go in
this file when it runs.

## S8 verification note (2026-08-06, appended)

MEA's press-release RSS resolves (after redirects) to an empty feed;
PIB's per-ministry RSS system responds but its feed directory
(AllRss.aspx) serves a ~166-character stub to both curl and a real
browser session from this environment — the External Affairs ministry
feed id could not be verified. Per the source discipline (only
verified feeds register), S8 registers NOTHING today. Next honest
step: the founder opens pib.gov.in's RSS directory from his own
browser and pastes the External Affairs feed URL; verification and
registration then take minutes. No guessed feed ids.
