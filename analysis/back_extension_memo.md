# Decision memo: the 1979–2016 back-extension (M1) — SIGNED 2026-08-06

Status: SIGNED by the founder in chat 2026-08-06 ("sign
back-extensions"). The four-channel roster, the nine validation
anchors, and the overlap thresholds below are now FROZEN — registered
before the first computation, which may now begin. Amendments are
dated and append-only. This is a construct-level
decision because it creates a new historical series that readers will
inevitably compare to the live instrument; every boundary choice
below changes what that comparison means.

## What is actually possible, stated plainly

The live instrument (2017–) measures **phrase-dictionary share of an
English article corpus**. No such corpus exists before ~2015. What
exists earlier is GDELT 1.0's **coded event stream back to 1979**:
events with actors, geography, and mention counts. A back-extension
therefore measures a *different construct* — the share of global
event-mentions involving India-relevant actor/geography pairs — that
correlates with, but is not, press salience. The memo's first
commitment: the historical series is named a **historical attention
proxy**, is published on its own page with its own payload, and is
NEVER spliced into, averaged with, or drawn on the same axis as the
2017+ instrument. "IGRM before 2017" is a phrase this project will
never print.

## Generation boundaries (decision A)

| Segment | Source | Native measure |
|---|---|---|
| 1979-01 – 2015-02 | GDELT 1.0 events (BigQuery `gdelt-bq.full.events`) | daily event-mention share by actor/geo filter |
| 2015-02 – 2016-12 | GDELT 2.0 events (`gdeltv2.events`) | same filters, richer coding |
| 2017- | the live instrument | phrase-dictionary corpus share (not part of this study) |

Proposed handling: normalize each segment against its own trailing
window (the instrument's own transform), report the 1.0→2.0 boundary
as a dated vertical line on every chart, and publish the raw shares
beside the percentiles so the seam is inspectable.

## Channel mapping (decision B)

Only channels with defensible event-analogs run:

- **pakistan_west** → events with actor1/actor2 country codes {IND, PAK}
  paired, or geography in the border states. Defensible.
- **china_east** → {IND, CHN} pairs. Defensible.
- **us_trade** → {IND, USA} pairs restricted to CAMEO economic
  cooperation/conflict roots. Weaker: trade *policy* salience and
  event coding diverge. Runs, flagged.
- **gulf_energy** → {IND} × {SAU, IRN, ARE, QAT, KWT, IRQ} pairs.
  Weaker still: energy-security salience is not bilateral events.
  Runs, flagged.
- **shipping** → NO defensible analog (chokepoint salience has no
  actor coding). **Excluded**, stated on the page. Four channels, not
  five, is the honest roster.

## Validation anchors, registered ex-ante (decision C)

Before any series is drawn, this list freezes. The reconstructed
proxy must place each anchor's month in its channel's **top decile**
(trailing-10-year basis) or the miss is published with the series:

| Anchor | Date | Channel |
|---|---|---|
| Operation Blue Star + aftermath | 1984-06 | pakistan_west* |
| Brasstacks crisis | 1987-01 | pakistan_west |
| Pokhran-II tests + sanctions | 1998-05 | pakistan_west, us_trade |
| Kargil war | 1999-05..07 | pakistan_west |
| Parliament attack + Op. Parakram | 2001-12 | pakistan_west |
| Mumbai 26/11 | 2008-11 | pakistan_west |
| Nathu La / Cho La reference check | 1967 — out of range; excluded | — |
| Sumdorong Chu standoff | 1986-10 | china_east |
| Doklam | 2017-06 — overlap check vs live instrument | china_east |

*1984 is a domestic episode with cross-border coverage dynamics; it
is retained as an anchor deliberately BECAUSE it stress-tests the
actor-pair filter's construct edge — if it spikes, the memo's
construct caveat gets a worked example; if it does not, that is
evidence the filter is truly bilateral.

## Overlap audit (decision D)

2015-02 – 2019-12: the event proxy and (from 2017) the live
instrument run in parallel. Publish the correlation per channel over
the 2017–2019 overlap. Registered interpretation thresholds, ex-ante:
r ≥ 0.6 = the proxy tracks salience usefully; 0.4–0.6 = publishable
with prominent caveat; < 0.4 = the channel's historical series does
NOT publish, and that negative result is the published finding.

## Cost and lane

BigQuery, partition-scoped, `maximum_bytes_billed` capped per query
(the bq-smoke lane proves the cap is honored). Monthly aggregates
only — no article fetching, no rate-limit exposure. Estimated well
inside the free tier; the exact bytes-billed number publishes in the
study's methods section.

## What signing this authorizes

1. The four-channel roster and filters above, frozen.
2. The anchor list above, frozen before first computation.
3. The overlap thresholds above, frozen.
4. Publication as a separate research page ("historical attention
   proxy, 1979–2016") with the construct caveat in the first
   paragraph and the shipping exclusion stated.

To sign: reply "sign back-extension" (with any strikes or edits —
striking anchors before computation is what the process is for).
Second-or-third-paper material per the founder's own read.
