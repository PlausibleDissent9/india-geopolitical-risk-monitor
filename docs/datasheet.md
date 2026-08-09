# Datasheet: India Geopolitical Risk Monitor (IGRM)

This datasheet follows the structure of Gebru et al., "Datasheets for Datasets" (2018).
Every answer is extracted verbatim from committed repository sources by
`scripts/generate_openapi.py`; a question with no committed answer says so rather than
inventing one. Regenerate with: `python -m scripts.generate_openapi`.

Contract version 2.3.0, frozen 2026-08-09. Machine-readable API description: https://igrm.in/openapi.json

## Motivation

### For what purpose was the dataset created?

A daily, category-decomposed index of geopolitical press salience for India-relevant topics, distinct from the Caldara-Iacoviello GPR family: five channels built from frozen, ex-ante term dictionaries over GDELT coverage shares, normalized to trailing 730-day percentiles, with episode detection, pre-registered validation, placebo channels, dictionary-robustness checks, and an event-study layer on India-specific relative returns. Measures attention, not event probability or severity; reports associations, not causes.

*Source: CITATION.cff, abstract*

### Who created the dataset and on behalf of which entity?

**The founder** (Ishan Krishna) owns every measurement choice: channel
constructs, dictionary terms, weights, thresholds, comparator rosters,
calibration labels, and every public claim the project makes. A
construct choice becomes real only through his signature — moving a
`*_DRAFT` file to registered status with a `frozen_on` date, or an
explicit signed entry. Calibration rulings must be his personally; a
machine supplying them would fabricate the instrument's ground truth.

**Machine lanes** (CI, the VPS cron, agent sessions) implement, fetch,
draft, test, and publish what is already registered. They may propose
anything and decide nothing constructal. Drafts are labeled as drafts.
Machine lanes commit as `igrm-bot <actions@github.com>`; the founder's
own lane commits under his name.

*Source: GOVERNANCE.md, section "Roles"*

### Who funded the creation of the dataset?

Not documented in the repository as of this generation.

## Composition

### What do the instances that comprise the dataset represent?

The index measures **press salience**: for each of five channels, the share
of all articles GDELT monitors globally that match the channel's term set,
expressed as a percentile against that channel's own trailing 730 days. A
composite score of 79 means exactly this: *today's matching-coverage share,
averaged across the five channels' percentiles, is higher than it has been
on 79% of days over roughly the past two years.* Nothing more.

IGRM keeps its established name, but the construct is **geopolitical
salience**, not the probability or severity of geopolitical events. It is
distinct from the Caldara-Iacoviello GPR family. The standing comparison
uses their monthly India series, `GPRC_IND`, over the 110 months shared by
the two instruments. A separate, code-frozen benchmark against the newer
AI-GPR `India_all` series finds Spearman rho 0.256 in 106 month-over-month
changes, with a registered six-month moving-block 95% interval of
[0.050, 0.407]. The registered interpretation is that the measures share a
common component but are far from redundant. This does not establish that
either is more accurate. The two constructs can diverge for ordinary reasons: an under-covered
crisis scores low in IGRM, an anniversary retrospective scores high (§7),
and editorial fashion can move the series with no change in the world. The
index answers "how much is the press writing about this?", never "how
dangerous is this?". It is not a forecast and not investment advice. See
the [standing comparison](vs-gpr.html).

*Source: methodology.md, section "1. What the index measures (and what it does not)"*

### How many instances are there in total?

The API contract (data/api_contract.json, version 2.3.0, frozen 2026-08-09) lists 116 endpoints: 110 JSON, 5 CSV, 1 RSS. The machine-readable OpenAPI 3.1 description is served at https://igrm.in/openapi.json.

*Source: docs/data/api_contract.json (counts computed at generation)*

### Does the dataset rely on external resources (e.g., websites, other datasets)?

External dependencies, in full: GDELT (DOC API + Web NGrams v5 on
public GCS), UCDP bulk CSVs, IMF PortWatch, Yahoo Finance (prices;
not redistributed), GitHub (repo, CI, Pages), one VPS, the domain
`igrm.in`, and optionally the Anthropic API for display-layer labels
(fail-closed without it). No aggregator or third-party index is ever
a data input.

Everything needed to rebuild the site exists in this repository plus
those public sources; `REPLICATION.md` is the proof procedure. Keys
(GitHub secrets, VPS access, domain registrar) are held by the founder
alone. If the project goes unmaintained, the last published data,
methodology, and this governance record remain valid as a dated
instrument — the archive-mirror preparation (V14) exists so that even
the hosting is not a single point of failure.

*Source: GOVERNANCE.md, section "Dependencies and bus factor"*

## Collection process

### How was the data associated with each instance acquired?

```
GDELT DOC API ──┐
                ├─> build_index.py ──> docs/data/{latest,history,episodes}
Yahoo Finance ──┘         │
                          └─> event_study.py ──> docs/data/event_study.json
GitHub Actions (daily 18:00 IST) commits outputs; GitHub Pages serves docs/
notes/*.md (author-written) ──> published to the site weekly
```

*Source: README.md, section "Architecture"*

### What mechanisms or procedures were used to collect the data?

- **Daily (automatic).** `daily-update` runs at 18:00 IST: the ngram
  bridge heals recent days, the pipeline rebuilds scores/episodes/event
  study, and outputs commit to `docs/`. It refuses to publish stale or
  partial data (fail-loud gate).
- **Validation.** `validate-and-analyze` (Actions) re-runs the full
  battery; hit-rate/seasonality/alt-specs are offline, the
  GDELT-dependent checks retry when the API allows.
- **Dictionaries are frozen.** Any change goes through the methodology
  changelog; CI enforces the ex-ante rule (no retrospective event names)
  and the query grammar across all term lists.
- **Weekly note.** Friday's run drops `notes-inbox/datapack_YYYY-Www.md`;
  write ~250 words to `notes/YYYY-Www.md` (the site footer's
  "write this week's note" link opens the editor), the next run
  publishes it to the site and RSS.

*Source: README.md, section "Operations"*

### Over what timeframe was the data collected?

Live at https://plausibledissent9.github.io/india-geopolitical-risk-monitor/
with daily data since 2017-01-01, frozen v1.0.0 dictionaries, and a
registered corresponding-channel episode-detection record of **24/29**:
18/21 in the original pre-registered tranche and 6/8 in the later registered
tranche. Strict-start, naive and chance baselines publish beside that result.
During the July 2026 DOC-API disruption the recent tail is computed from
GDELT's Web NGrams feed at the maintainer's direction, ratio-spliced on
overlap days (methodology changelog v1.0.1).

*Source: README.md, section "Status"*

## Preprocessing, cleaning, labeling

### Was any preprocessing/cleaning/labeling of the data done?

- Every percentile is computed against the series' own trailing 730 days,
  minimum 180 observations, never using future data.
- **The window is 730 calendar days**, ending on and including the day being
  scored, not the last 730 observations. The distinction is real because the
  series has genuine gaps, so the two readings select different windows on
  either side of a gap.
- **The percentile is the share of that window at or below the day's value**,
  times 100. Ties count as at-or-below, not strictly below and not half-credit.
- **Published values are rounded half-to-even** (Python's `round`). Values
  exactly half-way therefore round to the nearest even final digit.
- GDELT days are UTC; market data uses exchange trading days (IST for NSE).
- All return language is associational. Nothing here is investment advice.

Those conventions are sufficient for `src/blind_replicator.py` to rebuild
the series from this codebook and the published `shares.csv` without importing
the pipeline. Every published daily channel and composite score cell must match,
and missing reconstructed cells count as failures rather than disappearing from
the denominator. The current cell count and exact result are recomputed nightly at
[`data/replication.json`](data/replication.json); a methodology change that is
not reflected here breaks the exact-agreement test.

*Source: docs/codebook.md, section "Conventions"*

### Is the software that was used to preprocess/clean/label the data available?

The pipeline is pip-installable from a checkout (`pip install .`,
package name `igrm`; the import package stays `src` until the 1.0
restructure, and there is deliberately no PyPI upload — data files
live in the repository, so a checkout is the unit of reproduction).
For development:

```
pip install -r requirements.txt
pytest -q
python -m src.run_daily --backfill     # first time
python -m src.run_daily                # daily incremental
python -m src.make_datapack            # weekly note inputs
python -m src.validate hit-rate        # pre-registered episode detection
python -m src.validate placebo         # placebo channels (layer 4d)
python -m src.validate robustness      # broad/narrow dictionary variants
```

To verify the published numbers independently, see
[REPLICATION.md](REPLICATION.md). The public clean-room command reconstructs
every published daily channel/composite score cell and fails on missing cells;
the document separately identifies pipeline lanes that need non-redistributed
source caches.
Decision rules, append-only surfaces, and the deprecation policy live
in [GOVERNANCE.md](GOVERNANCE.md); adding a country monitor follows
[countries/RECIPE.md](countries/RECIPE.md).

*Source: README.md, section "Local run"*

## Uses

### Has the dataset been used for any tasks already?

Static, code-frozen comparison of monthly IGRM salience with Iacoviello-Tong AI-GPR India_all: registered primary and descriptive correlations, moving-block intervals, full eligible-month list, exploratory matrix, event-month ranks and largest rank divergences. Aggregates and ranks only; no raw AI-GPR values are redistributed.

*Source: docs/data/api_contract.json, description of data/ai_gpr_benchmark.json*

### Are there tasks for which the dataset should not be used?

Named here before a reader must raise them. Each with its mitigation and
its residual.

1. **Salience ≠ risk.** The permanent one. Mitigation: this page, §1, and a
   definition line under the headline number. Residual: total, the index
   never becomes a risk measure; it measures attention.
2. **No causal identification.** No natural experiment or instrument exists
   in this design. Mitigation: association-only language, enforced by
   review. Residual: total, at any level of statistical sophistication.
3. **Thin sample.** India has had tens of geopolitical episodes since 2022,
   not thousands. Mitigation: bootstrapped intervals reported everywhere;
   the series and event backfill now extend to 2017. Residual: intervals stay wide
   forever; findings stay descriptive.
4. **Single-source dependency.** The score rests on GDELT's
   corpus and its English-language, Western-outlet skew. Mitigation:
   Wikipedia-pageview cross-validation now publishes beside it but never
   enters the score. Residual: agreement
   between two biased attention measures is not unbiasedness.
5. **Hindsight in dictionary construction.** The dictionaries were written
   in 2026 by people who know 2022-26 history. Mitigation: the ex-ante
   structural-terms rule bounds the leak, no event names, only vocabulary
   that predates and outlives specific events, and the robustness harness
   (§8) shows results survive reasonable re-wordings. Residual: bounded,
   not eliminated; disclosed.
6. **Anniversary and editorial-cycle effects.** Retrospectives count as
   salience by construction. Arguably a feature (attention is attention);
   either way, planned work quantifies it with day-of-year effects.
7. **Coverage-drift.** GDELT's source list itself evolves; a step-change in
   monitored outlets can move shares with no change in the world. Partially
   absorbed by the share denominator and the trailing percentile; residual
   disclosed.
8. **Timezone convention.** GDELT days are UTC; Indian market days are IST;
   the daily run, final by 6:00 AM IST, treats "today" as the UTC date. A same-day
   Indian-evening event lands on the correct UTC day but after the NSE
   close, event-study windows therefore start at the first trading day on
   or after the episode start, never before.
9. **Composite arbitrariness.** §4. Mitigation: labelled a convention;
   components published. Residual: no weighting is privileged.
10. **Phrase brittleness.** Exact-phrase matching misses paraphrase
    ("infiltration attempt" vs "infiltration bid") and non-English coverage
    entirely. Mitigation: doctrine terms chosen from wire-service
    vocabulary; robustness harness. Residual: recall is partial and skewed
    toward English-language convention.

Association, not causation. Salience, not ground truth, anniversary
coverage counts by construction (disclosed in methodology §7). GDELT
reaches back to Jan 2017 only. Not investment advice.

*Source: methodology.md, section "7. Known limitations"; README.md, section "Honest limitations"*

## Distribution

### How will the dataset be distributed?

Base URL: https://igrm.in/

- auth: none
- cors: Access-Control-Allow-Origin: *
- rate_limit: none stated; ordinary politeness (poll daily, not per-request)
- refresh: daily by 06:00 IST (00:30 UTC) for the final day; nowcast.json refreshes about every two hours after and is excluded from this freeze (payload shape may still change, disclosed in its own _meta)

*Source: docs/data/api_contract.json, _meta.base_url and _meta.access*

### Will the dataset be distributed under a copyright or other intellectual property (IP) license?

License: CC BY 4.0

Citation: Krishna, Ishan (2026). India Geopolitical Risk Monitor. https://igrm.in/

*Source: the universal _meta fields stamped on every published payload (src/stamp_meta.py)*

## Maintenance

### Who will be supporting/hosting/maintaining the dataset? How can the owner/curator/manager be contacted?

Citation: Krishna, Ishan (2026). India Geopolitical Risk Monitor. https://igrm.in/

Repository: https://github.com/PlausibleDissent9/india-geopolitical-risk-monitor

Contact: ishankrishna9@gmail.com

*Source: the universal _meta citation and CITATION.cff*

### Will the dataset be updated? How often?

Refresh: daily by 06:00 IST (00:30 UTC) for the final day; nowcast.json refreshes about every two hours after and is excluded from this freeze (payload shape may still change, disclosed in its own _meta)

Frozen fields are never removed, renamed, or repurposed to a different meaning within major version 2. New fields may be added to any payload at any time without a version bump. Any removal, rename, or type change requires a major version bump, announced here and in methodology.md's changelog before it ships.

An analytical field or endpoint marked deprecated stays live and unchanged in meaning for at least 90 days after the date recorded here, before removal in the next major version. Operational or personal material served by mistake may be withdrawn immediately, with the removal recorded here.

*Source: docs/data/api_contract.json, _meta.access.refresh, _meta.promise and _meta.deprecation_policy*

### Will older versions of the dataset continue to be supported/hosted/maintained?

The API contract (methodology §12) governs payload fields. Above that:

- **A payload, page, or channel is retired, never deleted.** Retirement
  requires: a changelog entry announcing it at least 30 days before
  removal, a major contract version bump if any frozen field goes, and
  a tombstone (the page states what stood there and why it went, with
  the last-served data downloadable). History files keep the retired
  series' past values.
- **A methodology section is superseded, not erased**: the old text
  stays reachable through git history and the changelog names the
  commit.
- Nothing has been deprecated as of 2026-08-06.

*Source: GOVERNANCE.md, section "Deprecation policy (project level)"*

### If errors are found, what is the mechanism for communicating them?

Failures publish. A missed morning contract, a red audit, a wrong
number — each gets a corrections entry with the cause, in plain
language, kept forever. Negative results (a validation that fails, a
forecast experiment that loses to climatology) publish with the same
prominence their positive versions would have had. The site's honesty
surfaces (corrections, limitations, uncertainty bands, reliability
record) are load-bearing product, and no lane may sanitize them.

*Source: GOVERNANCE.md, section "Failure policy"*

## Known limitations: the negative-results register

Quoted verbatim from docs/data/negative_results.json (the register's own description first):

> Every number that did not go this project's way, compiled from the payloads where each lives. Read live from those payloads at build time, never hand-typed, so a row that stops being true stops being published.
>
> Anyone can publish good numbers. The reason to believe the flattering ones is that the unflattering ones are computed by the same pipeline on the same schedule -- and this file is where they stand together instead of being scattered across 8 payloads.

### Fusing four sources made detection worse, not better

- Number: 2 of 29 episodes detected (hit rate 0.069) vs 24 of 29 for the corresponding-channel press criterion across five channels
- Reading: the pre-registered four-source gauge detects a fraction of what the channel-level press detector does; adding modalities did not improve this registered diagnostic
- Source: data/stress_gauge.json (via docs/data/negative_results.json)

### Placebo channels overlap real episodes far above zero

- Number: 52 of 115 placebo episodes (45.2%) overlap real ones; duration-preserving random placement expects 35.6%
- Reading: part of every channel's signal is general news volume, and the excess over chance is 9.6 points, not the full observed rate
- Source: data/detection_baselines.json (via docs/data/negative_results.json)

### A naive any-channel detector nearly matches the registered hit rate

- Number: naive 26 of 29 vs registered 24 of 29; chance 6.8
- Reading: detection alone is cheap; the channel attribution is what the apparatus actually contributes
- Source: data/detection_baselines.json (via docs/data/negative_results.json)

### The 7-day headline barely beats chance as a detector

- Number: composite7 detects 8 of 28 evaluable events on the registered threshold rule; chance is 6.4
- Reading: the headline is a summary statistic, not the detector; detection lives in the per-channel series, and the two famous headline anecdotes were anecdotes
- Source: data/detection_baselines.json (via docs/data/negative_results.json)

### The index tracks English-language attention, not Indian-language attention

- Number: English Wikipedia leads Hindi on 5 of 5 channels, in both levels and changes, with no channel in the other direction
- Reading: the construct is Anglophone press salience of India; the name understates the qualifier
- Source: data/wiki_hindi.json (via docs/data/negative_results.json)

### 2 of 4 historical channels failed their own pre-registered test and were withheld

- Number: gulf_energy r=0.153, us_trade r=0.216 against the registered floors: below 0.6 a series is not published clean, below 0.4 not at all
- Reading: the withholding rule is the contribution; publishing them anyway would have retracted it
- Source: data/back_extension.json (via docs/data/negative_results.json)

### No sector shows a return sensitivity that survives multiple-comparison correction

- Number: Benjamini-Hochberg FDR at 10% across the full cell grid, same discipline as the main event study; bh_significant_10pct per cell. On the first computation (2026-08-06, 39 cells) NO cell survived correction
- Reading: with this episode set, sector sensitivity to salience episodes is indistinguishable from zero once the search is paid for
- Source: data/sector_sensitivity.json (via docs/data/negative_results.json)

### The largest lead-lag association places the market first

- Number: largest association at lag -8: VIX-percentile changes tend to precede attention changes (association, not causation)
- Reading: this index is not an early-warning system for anything priced; whatever it is for, it is not that
- Source: data/priced_risk.json (via docs/data/negative_results.json)

### Machine-labelled on-topic shares are uncalibrated and low on two channels

- Number: author labels 16 of 100; machine agreement 0.875 on n=16
- Reading: precision claims wait for the human calibration to reach its registered threshold
- Source: data/precision.json (via docs/data/negative_results.json)

### The headline is sensitive to a calibration constant on one channel

- Number: china_east 7-day score moves up to 25.63 points across defensible splice ratios
- Reading: the primary series is frozen while the founder decides; the sensitivity is published rather than absorbed
- Source: data/splice_sensitivity.json (via docs/data/negative_results.json)
