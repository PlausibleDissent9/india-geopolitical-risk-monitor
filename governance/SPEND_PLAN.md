# IGRM spend plan — drafted 2026-08-17

Budget envelope: ₹2,50,000 through 2026-11-01.

Written after the 2026-08-12→17 outage, in which the daily enrichment lane
was red on every scheduled run for five days, the derived plane froze a
week behind its own raw inputs, and nothing told anyone — because
igrm.in looked perfectly current the entire time.

The ordering below is by **risk removed per rupee**, not by cost. Two of
the three highest-value items are free, which is a finding rather than
thrift: the binding constraints on this project right now are a signature
and an API registration, not money.

---

## Tier 0 — free, and higher value than anything paid

### 0.1 Media Cloud API key — ₹0
`src/media_cloud.py` is written, tested and already wired into
`drift.yml` as *"S5 Media Cloud cross-validation"*. It fail-closed skips
because `MEDIACLOUD_API_KEY` is not set. Media Cloud is a non-profit and
the key is free on registration.

**Buys:** a second, independent media-attention source. Today every
approved source in the rights registry is GDELT — three of three. This is
the single cheapest reduction in provider concentration available.

**Action:** register at mediacloud.org, add the key as a repository
secret named `MEDIACLOUD_API_KEY`. ~10 minutes.

### 0.2 Sign the pending source-rights decisions — ₹0
19 sources are registered and 14 fetchers are written, but only **3 are
approved, and all 3 are GDELT**. Sixteen sit at `review_required`: UCDP
conflict data, Wikimedia pageviews, IMF PortWatch, COW militarised
disputes, JODI oil, UN Comtrade, three Indian port-statistics sets, the
GPR datasets, GDELT Events V1 and GKG V2.

**Buys:** the diversification that money is otherwise being asked to
solve. The code already exists for most of these.

**Action:** review the drafted decisions (drafted separately, each with
its terms URL and an explicit "unresolved" field), then sign. The signing
key must only ever exist with the founder.

### 0.3 Zenodo deposit — ₹0
Already built (V7 package). Free DOI, permanent archive.

---

## Tier 1 — small recurring, removes whole failure classes

### 1.1 Dead man's switch — ₹0–600/month
Healthchecks.io (free tier covers this) or Better Stack. The daily lane
pings a URL on success; no ping within 26 hours raises an alert to phone.

**Buys:** the actual defence against what happened. It inverts the
signal — instead of noticing failures you notice the *absence of
success*. It is also the only thing that catches GitHub silently not
firing a cron at all, which this repo has already recorded happening
(2026-07-31, the 11:00 slot never fired).

**Why not just GitHub notifications:** they fire per-failure, they are
easy to filter into a folder and stop seeing, and they cannot detect a
run that never started.

### 1.2 GDELT via BigQuery — ₹0–2,000/month realistically
GCP bills roughly $6.25/TB scanned with 1 TB/month free. The `bq-*`
lanes in this repo already prove access works, and `gdelt_bq_webngrams`
is already an approved source.

**Buys:** removes IP reputation from the equation permanently. The DOC
ArticleList API is throttling GitHub runner IPs (HTTP 429 after six
attempts), which is what stalls V5 multilingual and two of five receipt
channels. BigQuery is not IP-throttled.

**This is the better answer than a VPS** for the throttling class,
because a droplet only moves the problem to a different IP that can also
be throttled later.

### 1.3 DigitalOcean BLR1 droplet — ₹500–1,000/month
Already in the plan. Useful independently of the throttling question: a
publish path that does not depend on GitHub Actions being available, and
a place to run the morning contract if Actions degrades.

**Buys:** removes single-point dependence on GitHub for the 06:00
contract. Keep it for that reason rather than as the throttling fix.

### 1.4 Raw evidence archive — ₹200–500/month
Object storage (Cloudflare R2 has a generous free tier; S3 equivalent)
for the raw acquisition record, independent of the git repository.

**Buys:** the evidence survives a repository accident. The project's
whole claim is receipts; the receipts should not live in exactly one
place.

---

## Tier 2 — conditional, only after a methods decision

### 2.1 ACLED — free (academic) / paid (commercial)
ACLED is **conflict event data**, not media-attention data. It cannot
substitute for GDELT without changing what the index measures, and the
methodology is registered.

Where it genuinely fits: the canonical graph currently emits `event: 0`
and `exposure_edge: 0`, which is the missing 12 points. ACLED is a
credible source for that plane.

**Do not buy until the event-coding methodology decision is made** — that
decision belongs to the methods reviewer. Note ACLED already appears in
this repo as `acled_conflict_index` in the benchmark contract, i.e.
scoped as something to compare *against*, which is the correct role.

---

## Deliberately NOT recommended

**Paying reviewers.** External review is the point of Packets A and B,
and paying for a review of your own index compromises exactly the
independence that makes it worth having. The Rana and Dipak Jain routes
are relationship and merit, not procurement. If a reviewer needs their
costs covered, cover costs — do not pay for an opinion.

**A commercial news API (Event Registry, NewsAPI, etc.).** These have
shallow archives, restrictive redistribution terms, and would introduce a
paid dependency for a construct GDELT already measures on two working
access paths. The DOC API being throttled is not GDELT failing; it is one
of three access paths failing.

**Paid CI minutes.** The lanes are not slow, they were wrong. The daily
lane failing for five days cost nothing in compute.

---

## What money cannot buy here

The deadlock class. Six instances now of the same shape — a gate
asserting the world is already good, and thereby blocking the work that
would make it good. That is a design property, now locked with
mutation-tested checks rather than comments. No amount of spending
prevents the seventh; only the locks do.
