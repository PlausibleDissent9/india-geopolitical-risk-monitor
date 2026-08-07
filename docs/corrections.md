# Corrections and incident ledger

Every error this project has caught, dated, with what would have been
published had the gates not held, and what changed so the class cannot
recur. An institution that hides its errors gets caught; one that
accounts for them gets cited. Newest first. Entries are append-only.

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
yesterday's final is unpublished past 00:30 UTC.
