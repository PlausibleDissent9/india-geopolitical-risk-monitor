# Corrections and incident ledger

Every error this project has caught, dated, with what would have been
published had the gates not held, and what changed so the class cannot
recur. An institution that hides its errors gets caught; one that
accounts for them gets cited. Newest first. Entries are append-only.

## 2026-08-08: the nightly publish died on its linter, and the morning contract was next

daily-update #100 failed at its first step in two minutes sixteen,
having computed nothing. A dependency check added that afternoon
asserted that the pins from both `requirements.txt` and
`requirements-dev.txt` were installed. CI installs both; `daily.yml` and
`morning.yml` install the runtime set alone and then gate on that same
suite. The nightly publish was therefore reported broken because ruff
and mypy were missing from environments deliberately built without them,
and the 05:37 IST morning contract would have failed in the same place.
Reproduced in a virtualenv holding `requirements.txt` and nothing else
before anything was changed. Fixed by requiring runtime pins everywhere
and gate pins only where a gate runs, with a version that drifts or a
partially installed gate environment still a failure. A separate
workflow now runs the publishing lanes' exact commands in the
environment those lanes use, because ordinary CI was green on the commit
that broke them.
Public exposure: the site served the previous completed day, correctly
labeled, overnight. No wrong numbers. One scheduled refresh was lost.

## 2026-08-08: the site described a guard that was passing everything

`products.html` told readers that the machine-readable protected route
list was append-only, and that removing a capability required a dated
public deprecation rather than deleting its link. The check behind that
sentence chose which revision to compare against by re-serializing the
committed catalog and comparing bytes. The catalog is hand-formatted one
route per line, so the comparison was never equal, and every commit was
compared against itself. Deleting the Atlas maps route with an empty
removal ledger returned `{"status": "pass"}` and exit 0. Reproduced
before the fix, and again afterwards where it refuses with
`catalog_route_removed_without_prior_notice`. Fixed by comparing the
parsed documents, and pinned by a test asserting which revision the
floor reports comparing against, since every existing test of the floor
supplied the prior catalog itself and so could not see this.
Public exposure: the sentence was live and unsupported for about
eighteen minutes, measured deploy to deploy. No route was removed in
that window and no published capability was affected.

## 2026-08-08: the brief withdrawal's own account was wrong about the mechanism

The entry below states that nine briefs cited a stress-gauge value "even
though the generator never supplied that gauge to the model." Recomputed
against git history, both halves are wrong. Eight brief versions cited a
gauge value, not nine. For seven of those eight the generator did supply
it: `build_context()` read `stress_gauge.json` from the feature's first
commit, and each of those seven cited exactly the value in the
`stress_gauge.json` committed in its own tree (65.1, 65.1, 60.5, 65.7,
65.7, 65.7, 65.7). The model copied its input correctly.

Exactly one citation is unsupported, and it is worse than the entry
described. The gauge field was removed from `build_context()` on
2026-08-07 inside an unrelated commit, with no check of the prose already
published against it. The next brief generated after that removal cited
"the stress gauge at 65.7" with no gauge in its input at all, while the
gauge payload committed beside it read 57.2 -- a sentence invented whole,
carrying a stale value the model could not see.

The withdrawal stands: an experiment that produced one fabricated
sentence in eight is withdrawn on its merits, and the other three
confirmed failures in the entry below (display share read as pool
quality, displayed count read as score denominator, 2026-08-07 scores
joined to 2026-08-06 receipts) recompute as stated. What changes is the
diagnosis, and the diagnosis is the part a reader learns from: the fault
was not a model inventing numbers it was never given, it was an input
silently removed mid-experiment while the published prose that depended
on it was left standing. Found by routine cross-review of the withdrawal
commit, three hours after it published.

## 2026-08-08: machine-brief experiment withdrawn after factual-grounding failures

The public language-model brief had a prediction-word deny-list, but no
mechanical check that its numbers, denominators, dates or entity claims were
supported by the supplied JSON. Ten committed brief versions covered five
completed news days (2026-08-03 through 2026-08-07). Nine stated a stress-gauge
value even though the generator never supplied that gauge to the model.

The channel prose also called the number of displayed, title-key-deduplicated
receipt representatives the number of articles underlying the score and
interpreted a tier-first, capped display share as source-pool quality. The last
version combined 2026-08-07 scores with the still-current 2026-08-06 receipt
sample. These were factual-grounding failures, not stylistic defects.

All generated prose is withdrawn and must not be cited. The API path now serves
a stable-shaped null tombstone through at least 2026-11-06; the module has no
model-call or payload-write branch; and the daily workflow no longer receives
the model API key. Generated prose may return only under a new versioned design
with exact score/receipt date alignment and machine-verifiable provenance for
every numeric and entity claim. The full incident record is
[`analysis/daily_brief_incident_2026-08-08.md`](https://github.com/PlausibleDissent9/india-geopolitical-risk-monitor/blob/main/analysis/daily_brief_incident_2026-08-08.md).

## 2026-08-08: blind-audit v2 did not match the production scoring frame, invalidated before coding

The frozen v2 external-coder package was byte-reproducible, but a later
source-frame audit found that its registered 2026-08-05 receipt cache covered
39 sampled snapshots and 28,575 English documents while the cache used to
produce that day's score covered 48 snapshots and 33,961 documents. Forty-nine
of the 500 sampled rows came from the deficient cache.

The audit also sampled unique document keys, while production adds sub-query
group shares; a document matching two groups contributes twice to the effective
score numerator but only once to v2's frame. The registered study therefore did
not estimate precision for the production scoring quantity it claimed.

No external or pilot label had been collected. V2 is invalidated before coding
and must not be fielded, scored, merged into a later study, or cited as a
precision result. A v3 may be frozen only after exact score-cache lineage,
denominator parity and a contribution-level estimand are verified before
sampling. The frozen v2 bytes remain available solely as correction evidence;
the complete diagnosis is in
[`validation/blind_audit_500/V2_INVALID.md`](https://github.com/PlausibleDissent9/india-geopolitical-risk-monitor/blob/main/validation/blind_audit_500/V2_INVALID.md).

## 2026-08-07: circular splice-stability result, caught pre-publish

The first stability check appeared to expand the splice calibration from
one or five overlap days to 38 and found that no ratio moved by more than
1.1%. That result was circular. On 37 of the 38 dates, the live-store
denominator had already been constructed from the cached NGrams numerator
and the production ratio, so the calculation was mostly recovering its
own input.

The result was stopped before publication. The independent audit now uses
the last pre-bridge DOC-API store preserved in git and finds materially
different ratios for Pakistan (+26.0%) and China (-19.7%), a small change
for Gulf (+1.0%), and no additional independent overlap for US Trade or
Shipping. The methodology publishes the full table and keeps the frozen
production values unchanged. A regression test now requires the audit to
use the preserved pre-bridge snapshot. No public exposure to the rejected
38-day claim.

## 2026-08-01: unverifiable source-tier accusations, caught pre-publish

The first draft of `source_tiers.json` designated four broadcast
outlets tier 4 with specific fabrication claims the project could not
cite. Caught at the gate before commit. Published version holds those
outlets at tier 3 pending citations; tier-4 designations now require
evidence the project itself can produce or cite. No public exposure.

## 2026-08-01: channel-agnostic episode attribution, caught in spot-check

The first run of the episode-actors decomposition ranked any busy
India dyad as an episode "driver": a Pakistan-channel episode showed
Ukraine as its top driver. Caught by the too-weird sanity rule before
push. Fixed with registered channel-partner lists; unrelated active
dyads now appear only as labeled context. No public exposure.

## 2026-08-01: partial week published as complete, caught at the gate

The comparator publisher's first output labeled a half-finished week
with a complete week's date; India's "latest" read 10.8 where the true
complete-week value was 42.4. Caught in pre-push verification. The
publisher now drops any trailing week whose label postdates the data.
No public exposure.

## 2026-07-31: gauge validation scored 1 of 21, published as registered

Not an error, recorded here as precedent: the stress gauge's
pre-registered detection rule scored 1 of 21 episodes and was
published unchanged. Registrations bind; low numbers are findings.

## 2026-07-31: map geometry collapse, caught in verification

The first geometry bake produced zero countries: Douglas-Peucker on
closed rings degenerates (start equals end) and collapsed every
polygon to two points. Caught in browser verification before commit.
Fixed with a farthest-point anchor. No public exposure.

## 2026-07-31: analysis charts broken on the live site, found and fixed

Pre-existing defect found during verification: the analysis page's
chart code read CSS variables its stylesheet never defined; the
attention-pricing-gap chart had never rendered for any visitor and
every other analysis chart drew in fallback grey. Fixed the same hour
with the palette added and cache-busters bumped. Public exposure:
cosmetic-to-broken charts, no wrong numbers.

## 2026-07-31: computed day lost to a swallowed push race, fixed

The daily pipeline computed 2026-07-30 correctly and lost the final
push to a race with the backfill chain; a conflicted rebase swallowed
by an error guard discarded the day while every step reported green.
Fixed with fail-loud push retries and single-writer file ownership.
Public exposure: the site showed the previous day's data, correctly
labeled, for several hours. No wrong numbers.

## 2026-07-24: query-list circularity, caught in review

"Galwan River" sat in the china_east Wikipedia list while the Galwan
clash is a validation episode, which would have made that detection
circular. Caught in review; the ex-ante CI test now covers every
query list in the repository. No public exposure.

## Precedent: the 53 fake significances

Before this ledger existed, a misaligned market window once produced
53 statistically significant event-study results from real data. The
too-good-to-be-true sanity gate caught it before publication. That
incident is why every result that flatters the project is treated as
a bug until independently recomputed.

## 2026-08-02: published map totals exceeded the committed store, caught by the first automated audit

The daily workflow updated the events store in its workspace and
published map aggregates from it, while a stale exclusion (left over
from the finished backfill chain's race protection) kept the updated
store files out of the commit. Published partner totals exceeded the
committed store by 29 to 65 events for about a day; derived shares
were correct for the data used, but the published numbers were not
reproducible from the committed raw files. Caught by the first run of
the dual-computation audit module, the same day it was written. Fixed:
the exclusion is removed, and the audit now runs inside the daily
workflow before any commit. Public exposure: map totals ~0.03% high
relative to the reproducible store, one day.

## 2026-08-03: audit tolerance blocked three green days, fixed with the arithmetic documented

The dual-computation audit's gauge check compared two independently
rounded published values under a 0.051 tolerance, but rounded-inputs
arithmetic can honestly differ by up to about 0.10, so the audit
false-positived (54.9 vs 54.85) and failed three daily runs across
2026-08-02 and 08-03. By design the failure was loud and the site
served stale-but-labeled data, never wrong data; the availability cost
was real. Tolerance corrected to 0.101 for that one check with the
derivation in a comment. Also armored the same day: the daily
schedule's crons have never fired on time in this repository, so the
reliably-firing nowcast workflow now dispatches the daily run whenever
yesterday's final is unpublished past 01:00 UTC.

## 2026-08-09: the status page could not have reported the stall it existed to report

This page states that everything on it derives from committed files and
that a stale source shows as stale by rule. For one failure mode, the
one that matters most, the second half of that was not true.

Every source's age and within-window verdict was computed when
`status.json` was written, and that payload is regenerated by the daily
run. So when the daily lane stopped publishing after 2026-08-07, the
status table froze at its last healthy reading and kept serving it. The
page was structurally incapable of reporting staleness caused by the
pipeline stopping: the numbers that measure the delay are produced by
the process that had stopped, so they could not move no matter how long
the stall lasted. It was calmest exactly when it should have been
loudest.

What was actually wrong on the page, stated precisely: from 2026-08-08
16:56 IST, when the last successful run wrote the payload, until the fix
deployed 2026-08-09 10:25 IST -- about 17.5 hours -- every listed age
was understated by one day. The GDELT salience store showed 1 day old
when it was 2. No source's within-window verdict was wrong during that
window; each was genuinely inside its stated window even at its true
age. Recomputed at the time of the fix, all ten rows held. The defect
was the mechanism, not a published false verdict, and it would have
become one had the stall continued.

Fixed: ages are now recomputed in the reader's browser from each
source's `latest_data` against the reader's own date, and the footer
states how long it has been since the payload was regenerated whenever
that is a day or more. The recomputation may only ever downgrade a row.
A verdict stays negative whenever the generator said negative, because
the generator knows things the browser cannot -- the market-input row
carries a negative verdict for an input date absent from committed
evidence, which no client-side date arithmetic could infer. Where the
live age differs from the written one, the written value is shown beside
it rather than quietly replaced.

Public exposure: source ages understated by one day for about 17.5
hours; no incorrect within-window verdict served; no published score
affected.

> Derived from datasets released by [The GDELT Project](https://www.gdeltproject.org/).
> GDELT grants unlimited use on one condition — that any use of the data cite
> the GDELT Project and link https://www.gdeltproject.org/ — and this notice
> exists to meet it. Full upstream attribution is in the [codebook](codebook.html).
