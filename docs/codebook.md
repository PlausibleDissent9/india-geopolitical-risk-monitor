# IGRM Codebook

**Purpose.** This document exists so a researcher can reuse IGRM data
without reading the source code or emailing the author: every published
file, every field in it, its units, and its construction, in one place.
Definitions here are column-by-column and mechanical; the *reasoning*
behind each construction choice lives in the
[methodology](methodology.html), and the evidence that the
constructions measure anything lives in [validation](validation.html).
If a published field is not documented here, that is a defect —
[report it](https://github.com/PlausibleDissent9/india-geopolitical-risk-monitor/issues).

## Researcher quick-start

Fetch, cite, and reproduce in five lines. No key, no rate limit, CORS
open; field stability is promised by the
[frozen API contract](data/api_contract.json).

```
# 1. The full daily series, 2017-present (composite + five channels):
curl -s https://igrm.in/data/history.csv -o igrm_history.csv
# 2. Today's finalized scores with metadata:
curl -s https://igrm.in/data/latest.json | python -m json.tool
# 3. The evidence behind today's numbers (per-channel matched articles):
curl -s https://igrm.in/data/receipts.json | python -m json.tool
# 4. The validation record (hit-rate, placebo, robustness, drift):
curl -s https://igrm.in/data/validation.json | python -m json.tool
# 5. Reproduce the index from source (pinned deps, same raw stores):
#    git clone https://github.com/PlausibleDissent9/india-geopolitical-risk-monitor
```

Citation: *Krishna, Ishan (2026). India Geopolitical Risk Monitor.
https://igrm.in/* — data CC BY 4.0, code MIT. A ready-made BibTeX entry
is at [igrm.bib](igrm.bib).

## Upstream data sources and attribution

IGRM's published values are derived data. The CC BY 4.0 licence above
covers IGRM's own derived output; it does not and cannot relicense the
upstream sources, each of which carries its own terms.

**The GDELT Project** — [https://www.gdeltproject.org/](https://www.gdeltproject.org/)

Every channel share, the composite, the event aggregates, the tone and
theme series and the per-channel receipts are derived from datasets
released by The GDELT Project. GDELT makes its datasets available for
unlimited and unrestricted use, on one condition, quoted from its terms:

> any use or redistribution of the data must include a citation to the
> GDELT Project and a link to this website (https://www.gdeltproject.org/)

That condition attaches to **any use**, not only to redistribution, and
this section exists to meet it. Anyone reusing IGRM data that originates
from GDELT inherits the same obligation and should carry this attribution
forward.

Other upstream sources, each under its own terms and cited where used:
IMF PortWatch (chokepoint transits), UCDP Georeferenced Event Dataset
(conflict events), Wikimedia pageviews, Correlates of War MID 5.0, JODI
oil statistics, UN Comtrade, Indian major-port statistics, and the
Caldara–Iacoviello Geopolitical Risk index used as a comparison series.
Their rights positions are recorded per source in
[`governance/source_rights_registry.json`](https://github.com/PlausibleDissent9/india-geopolitical-risk-monitor/blob/main/governance/source_rights_registry.json),
including which are still under review and therefore not yet drawn on.

## data/raw/gdelt_volume.csv

| Column | Definition | Units | Range |
|---|---|---|---|
| `date` | Calendar day, UTC (GDELT's day convention) | ISO date | 2017-01-01 onward |
| `pakistan_west` … `shipping` | Share of all GDELT-monitored articles that day matching the channel's query; where a channel needs two sub-queries (length budget), the SUM of the two shares, a slight upper bound on the union | percent of corpus | ≥ 0, typically ≪ 1 |

## docs/data/episodes.csv

| Column | Definition | Units |
|---|---|---|
| `channel` / `label` | Machine key and display name of the spiking channel | text |
| `start`, `end` | First and last spike day of the cluster | ISO date |
| `peak_date` | Day of maximum raw coverage share inside the episode | ISO date |
| `peak_value` | That maximum share | percent of monitored corpus |
| `n_spike_days` | Spike days in the cluster | count |

## docs/data/event_study.csv

One row per channel × outcome × window. `mean_cum_log_return_pct` is the
mean cumulative log return (percent) over `window_trading_days` after
episode starts; `ci95_lo`/`ci95_hi` bound the bootstrapped 95% interval;
`n_episodes` is the number of episodes with sufficient data;
`descriptive_only` marks configured outcomes (Brent, gold) with no
separable India-specific component. `available_outcomes` and
`unavailable_outcomes` in the JSON disclose what the current source cache
actually supports; an unavailable configured outcome has no CSV rows and is
never described as reported. Association, not causation.

## JSON `_meta` blocks

Every dict-shaped JSON published by the pipeline embeds a `_meta` object
(what the file is, license, citation, codebook link, source URL,
generation date — plus `units` where the payload has a single unit) so a
downloaded file explains itself without this website.

Two payloads are bare JSON arrays with nowhere to carry `_meta`:
`episodes.json` and `notes.json`. Both are written in the same commit as
files that are stamped (`history.json`, `note_latest.json`), so their
provenance is one file away rather than absent.

One dict-shaped exception is deliberate: `ai_gpr_benchmark.json` is served
byte-for-byte as the hash-pinned output promised by its public registration.
Its own `_meta` carries the analysis registration, script and source hashes,
provider citation and raw-value redistribution limit. The generic metadata
stamper skips it because changing even an innocuous envelope field would
break the published result hash.

`public_api_byte_manifest.json` is the second deliberate deterministic
exception. Its `_meta` includes its meaning, licence, citation, codebook and
source URL, but no generation clock: a wall-clock field would churn the bytes
even when none of the 117 hashed endpoints changed. The file hashes one
captured Git candidate index/tree, excludes exactly itself to avoid recursion,
and is skipped by the generic stamper after generation. It is unsigned. An
independently obtained SHA-256 digest of the manifest's own raw bytes is needed
for an external comparison; the file does not authenticate a deployment or
claim that 117 separate hosted requests were served atomically.

*This was a promise before it was a fact.* Until 2026-08-07 the licence,
citation and codebook link appeared in **three** payloads out of
sixty-four, while this paragraph claimed all of them — so most downloads
carried no way to know their own terms or how to cite them. `src/stamp_meta.py`
now stamps the universal fields after every lane has run, without ever
overwriting a field a module set for itself. A test checks the claim
against what is actually served, so the sentence cannot drift from the
files again.

## docs/data/latest.json

| Field | Definition |
|---|---|
| `date` | Last day with a full composite |
| `definition` | The one-line construct definition shown under the headline |
| `composite` | Unweighted mean of the five channel percentiles, 0-100 |
| `channels.<ch>.score` | Channel percentile vs its own trailing 730 days, 0-100 |
| `channels.<ch>.label` | Display name |

## docs/data/history.json

| Field | Definition |
|---|---|
| `dates[i]` | ISO date for position `i` in every parallel array |
| `composite[i]` | Composite percentile that day (null before 180 trailing obs) |
| `channels.<ch>[i]` | Channel percentile that day |
| `labels` | Channel display names |
| `wikipedia.*` | Same structure computed from Wikipedia pageviews (present once the second source is active); levels are never comparable across sources, each is percentile-normalized independently |

## docs/data/episodes.json

Array of episodes, each:

| Field | Definition |
|---|---|
| `channel` / `label` | Which channel spiked |
| `start`, `end` | First and last spike day (raw share > trailing 90-day mean + 2σ, baseline lagged 1 day; days ≤ 3 apart cluster) |
| `peak_date`, `peak_value` | Day and value of the maximum raw share inside the episode; value in percent of corpus |
| `n_spike_days` | Count of spike days in the cluster |

## docs/data/event_ledger.json

The Global Event & Episode Ledger is a count-unit firewall over the current
event substrate. It must not be cited as a global event census. Its current
public artifact is a **value-free refusal state**: GDELT Events, Web NGrams,
IGRM first-party payloads and Natural Earth all remain `review_required` in the
signed source-rights registry, so this endpoint emits no source-derived count,
episode or geometry denominator. Candidate validation can run internally, but
it cannot override that gate. This new compiled-endpoint gate neither licenses
nor silently retracts existing source-specific endpoints; their separate rights
decisions remain `review_required`. The retained GDELT event store also lacks raw rows, stable
`GlobalEventID` values and revision lineage, so deduplicated and canonical
event counts remain unavailable even after rights approval.

| Field | Definition |
|---|---|
| `_meta.artifact_status` | Currently `public_release_blocked_rights_review`; an authorized future value release uses `public_observation_foundation` |
| `rights_gate` | Exact rights-registry and signer-registry hashes, required source IDs and uses, decision states, and blocked IDs |
| `frame` | `null` while blocked. An authorized release separates the 247-member display geometry, India-as-self/not-applicable, mapped members, reason-unresolved non-observations and provider codes that are unmappable |
| `count_units.*.public_available` | Always `false` in the refusal artifact; value is `null`. Candidate computation is not public availability |
| `count_units.aggregate_source_rows` | Future authorized counts use rows that passed the expected layout, not every provider-export row; malformed-row counts are not retained in the legacy store |
| `count_units.deduplicated_source_events` | Unavailable because stable source-event identity and revision lineage were not retained |
| `count_units.canonical_geopolitical_events` | Unavailable until cross-source resolution, rights, method and signed-release gates pass |
| `count_units.detected_salience_episodes` | Rights-gated threshold-defined IGRM channel windows; detector output, not real-world event identity |
| `aggregate_historical_series` | `null` while blocked. An authorized release defaults to India-row share of valid-layout rows; raw levels are secondary and cannot be treated as like-for-like across unregistered provider regimes |
| `episodes` | `null` while blocked. An authorized release uses stable detector-window IDs, `provisional_open_window` until the three-day cluster gap is observed, and `canonical_event_ids: null` |
| `canonical_event_layer` | Target lifecycle vocabulary and the non-negotiable requirements for a future production release |
| `release_lineage` | No public vintage exists while blocked. Every authorized release is predecessor-bound, complete-state hashed, carries a typed date/episode delta and requires a detached Ed25519 signature from a separately pinned release trust root. Source-rights approval alone cannot sign a public vintage; an agent-created key or self-declared role has no authority. CI replays every first-parent commit that ever changed the archive, refuses removal or byte changes to any predecessor and permits only the next sequential vintage, so an innocent tip cannot hide an earlier rewrite. The delta is recomputed from predecessor bytes. `released_at` must follow every bound evidence/knowledge date, increase strictly, and remain within five minutes of the verifier clock |

Authorized release-content and whole-artifact digests use
`igrm-typed-canonical-f64-v1`, not the host runtime's JSON number formatting.
Every number is encoded by its finite IEEE-754 binary64 bits, integers outside
the JavaScript safe range are refused, negative zero is preserved, and strings
and object-key ordering use UTF-8 bytes. Python and browser implementations are
checked against the same fixtures in
`validation/event_ledger_canonicalization.json`, including `1`/`1.0`, `-0.0`,
exponent boundaries, non-BMP Unicode and a release-shaped projection. A
profile mismatch or fixture failure refuses the authorized UI instead of
silently disagreeing about a signed digest.

The current refusal artifact is `partial: true` because values are withheld.
Inside an authorized release, `partial: false` would mean only that the declared
calendar, aggregate-store and display-geometry partitions reconcile. It would
not mean all geopolitical events, provider members, sources or canonical event
states have been observed. The legacy unavailable-day register has no immutable
retrieval receipts; those dates are not described as verified provider outages.

## docs/data/event_study.json

| Field | Definition |
|---|---|
| `windows` | Trading-day windows (1, 5, 20), inclusive of first trading day ≥ episode start |
| `units` | Cumulative log return, percent |
| `descriptive_only` | Configured outcomes with no separable India-specific component (Brent, gold) |
| `available_outcomes` / `unavailable_outcomes` | Which configured series have at least one observation in this release |
| `channels.<ch>.outcomes.<o>.<w>` | `{mean, ci95:[lo,hi], n}` across the channel's episodes; CI from 1,000 episode resamples |
| `per_episode.<ch>[]` | `{start, outcomes.<o>.<w>}` raw window returns for one episode (no CI; n = 1) |

Configured outcomes: `nifty_minus_em` (strips global equity beta),
`defence_minus_nifty`, `energy_omc_minus_nifty`,
`it_services_minus_nifty`, `ports_logistics_minus_nifty`,
`usdinr_minus_dxy` (strips broad dollar moves), `brent_ret`, and
`gold_ret` (descriptive). Consult `available_outcomes` and
`unavailable_outcomes` for the current release: a configured unavailable
outcome has no CSV result rows. Brent and gold remain descriptive-only
whenever available.

## docs/data/validation.json

| Key | Definition |
|---|---|
| `hit_rate` | Pre-registered episode list vs detected episodes, ±3 days; overall and per channel, plus per-episode hit/miss |
| `placebo` | Episodes detected in placebo channels and their overlap with geopolitical episode days |
| `robustness.narrow/.broad` | Correlation of primary percentile scores with narrower/broader dictionary constructions, per channel and composite (2022 onward) |
| `cross_source` | Per-channel correlation of GDELT and Wikipedia percentile scores |
| `drift` | Mean daily monitored corpus by year; sampled domain diversity and top-10 Herfindahl per channel-year; per-channel share-vs-corpus correlation |

## docs/data/alt_specs.json

| Key | Definition |
|---|---|
| `composite_weightings` | Equal (primary) vs trade-/import-exposure composites; correlation with primary |
| `episode_thresholds_sigma` | Episode counts at 1.5σ/2.0σ/2.5σ and episode-day Jaccard overlap vs primary |
| `percentile_windows_days` | Composite and per-channel correlation of 365-/1095-day windows vs the 730-day primary |

## docs/data/seasonality.json

| Key | Definition |
|---|---|
| `channels.<ch>.partial_r2` | Share of detrended log-share variance explained by smoothed day-of-year effects |
| `channels.<ch>.top_recurring_dates` | Calendar dates with the largest positive day-of-year effects (log points) |
| `channels.<ch>.corr_seasonal_vs_deseasonalized` | Correlation between primary and deseasonalized percentile indices |

## docs/data/priced_risk.json

| Key | Definition |
|---|---|
| `gap.dates[i]`, `gap.<ch>[i]` | Attention percentile − India-VIX percentile, shared trading days; positive = press louder than the market |
| `divergence_episodes.press_louder/.market_ahead` | Top-decile |gap| day clusters in each direction: start, end, peak date, peak gap |
| `lead_lag.ccf[]` | `{lag, corr, lo, hi}`: correlation of daily changes at each lag (−10..+10 trading days), moving-block bootstrap 95% bands; positive lag = attention leads |
| `lead_lag.reading` | The associational one-line interpretation |

## data/raw/events_daily.csv

The second measurement modality (V2): counts of recorded events involving
India from the GDELT Events v1 daily archive, one row per day since
2017-01-01. Where the salience series measures how loud the press is,
this series counts what the press recorded happening. An event involves
India when either CAMEO actor is coded IND or the action geography is
India. Events are dated by the file they arrive in, the day GDELT
recorded them, matching the salience series' "when did the world's press
carry this" framing.

| Column | Definition |
|---|---|
| `date` | UTC day of the GDELT v1 daily export file |
| `n_global` | Total events recorded worldwide that day (normalization denominator; GDELT's coverage grows over time, so raw counts drift without it) |
| `n_india` | Events involving India (either actor IND, or action geography India) |
| `n_verbal_conflict` | India events in CAMEO QuadClass 3 (verbal conflict) |
| `n_material_conflict` | India events in CAMEO QuadClass 4 (material conflict) |
| `n_protest` | India events with CAMEO root code 14 (protest) |
| `goldstein_mean` | Mean Goldstein cooperation-conflict score of India events (−10 most conflictual, +10 most cooperative) |
| `mentions_sum` | Total press mentions across India events that day |

## data/raw/events_dyads.csv

The relations layer: India's bilateral event record with every partner
country, one row per (day, partner). A dyad event has India as one CAMEO
actor and the partner as the other; no dictionaries or curation are
involved, only actor codes, so this layer carries no term-selection bias.

| Column | Definition |
|---|---|
| `date` | UTC day of the GDELT v1 daily export file |
| `partner` | CAMEO 3-letter code of the non-India actor (e.g. PAK, CHN, USA) |
| `n` | India-partner events that day |
| `n_coop` | Of those, cooperative (QuadClass 1 verbal / 2 material cooperation) |
| `n_conflict` | Of those, conflictual (QuadClass 3 verbal / 4 material conflict) |
| `goldstein_mean` | Mean Goldstein score of the dyad's events (−10 to +10) |
| `mentions_sum` | Total press mentions across the dyad's events |

## data/raw/events_states.csv

The internal layer: events geolocated to an Indian state, one row per
(day, state). `adm1` is the FIPS ADM1 code (IN01-IN36; IN00 marks
country-level geocoding without a state).

| Column | Definition |
|---|---|
| `date` | UTC day of the GDELT v1 daily export file |
| `adm1` | FIPS ADM1 code of the state the event action was geolocated to |
| `n` | Events located in that state that day |
| `n_conflict` | Of those, QuadClass 3 or 4 |
| `n_protest` | Of those, CAMEO root code 14 |

## data/raw/portwatch_chokepoints.csv

The physical-flow layer (V2): daily ship transits through the four
chokepoints most relevant to India's trade, from IMF PortWatch
(portwatch.imf.org), which derives them from satellite AIS with a
published methodology. Free with attribution; PortWatch publishes with
roughly a five-day lag and revises recent days, so updates re-fetch a
trailing window and revisions win.

| Column | Definition |
|---|---|
| `date` | Calendar day (UTC) |
| `chokepoint` | `suez`, `bab_el_mandeb`, `malacca`, or `hormuz` |
| `n_total` | Ship transit calls that day |
| `n_tanker` | Of those, tankers |
| `n_cargo` | Of those, cargo vessels |
| `capacity` | Total transiting capacity (deadweight tonnage-based, per PortWatch) |

## data/raw/chokepoint_salience.csv

Daily GDELT volume-intensity share per chokepoint sub-dictionary
(`shipping.chokepoints` in `dictionaries.json` v1.1.0), 2019-present.
The 2019 floor matches PortWatch coverage: these series exist only for
the salience-vs-transits comparison and never enter the composite.

| Column | Definition |
|---|---|
| `date` | UTC day |
| `hormuz`, `bab_el_mandeb`, `suez`, `malacca` | Share of all GDELT-monitored articles matching that sub-dictionary (sum of sub-query group shares, as for channels) |

## docs/data/chokepoints.json

Site payload for the analysis-page chokepoint chart: per chokepoint, the
weekly-mean salience and PortWatch `n_total` transits, each ranked as a
percentile of its own full 2019-present weekly history, plus a weekly
Spearman correlation on levels and the latest salience-minus-transits
percentile gap.

## docs/data/ai_gpr_benchmark.json

Static output from the public, code-frozen AI-GPR India benchmark. The
primary statistic is Spearman rho between month-over-month changes in the
monthly mean IGRM daily composite and AI-GPR `India_all`. `sample` publishes
every eligible month and the no-bridging rule; `primary` carries the point
estimate, registered six- and twelve-month moving-block intervals, seed and
mechanically selected decision sentence. `descriptive_primary` contains the
registered level and Pearson checks plus lag-1 autocorrelations.
`exploratory_correlations` is the labelled 6 by 4 matrix;
`episode_month_ranks` is descriptive and deliberately has no AI-GPR hit
rate; `largest_rank_divergences` republishes ranks and IGRM evidence links,
never raw AI-GPR values. The source, IGRM inputs and analysis script are all
SHA-256 pinned in `analysis/ai_gpr_benchmark_registration.json`.

## docs/data/divergence_register.json

Append-only rows documenting large disagreements between IGRM ranks and
independent comparator ranks. Every entry has a stable `id`, publication and
observation periods, register family, the two within-sample ranks, absolute
gap, direction, sample definition, evidence URL, source payload and a claim
limit. Samples differ by family and are never pooled. Rows identify where to
inspect; they do not decide which measure is correct or assign a cause.
Corrections retain the original id and add a dated note rather than silently
removing history.

## docs/data/nowcast.json

PROVISIONAL today-so-far scores, replaced roughly every two hours by
the nowcast workflow. Computed from a partial-day sample of the GDELT
Web NGrams bridge (same machinery and splice calibration as the heal
path), each channel ranked against its trailing 730 days exactly as a
finished day would be. `n_samples` and `n_docs_sampled` disclose the
sample behind the number. Never enters the historical series; the daily
run's finalized score supersedes it, and the site renders it only while
the payload's UTC date is still today.

## docs/data/map_relations.json and map_states.json

Aggregates behind the Maps page, published only once the 2017 events
backfill is complete (`_meta.partial` stays false on anything served).
Relations: per partner country (keyed by the dyad actor code), total
and trailing-365-day event counts, conflict share of classified events
(QuadClass 3-4 vs 1-2), event-weighted Goldstein mean. States: per
Indian state, total and trailing-365-day located events with conflict
(QuadClass 3-4) and protest (root 14) shares. GDELT still emits some
pre-2000 FIPS state codes; they fold into today's boundaries (IN09 into
IN35 Madhya Pradesh, IN33 into IN36 Uttar Pradesh, IN25 into IN22
Tamil Nadu, IN06 into IN52 Dadra and Nagar Haveli and Daman and Diu),
so a pre-2000 parent's counts include its later split-off child.
`IN00` (a country-level geocode) and CAMEO regional actor codes (SAS,
EUR, AFR, ...) are excluded and listed with row counts in each
payload's excluded block.

## docs/geo/world.json and india.json

Self-hosted map geometry, baked once by scripts/prepare_map_geometry.py
from Natural Earth public domain data (110m admin-0; 10m admin-1
filtered to India) and committed; the site fetches no external
geometry. Countries keyed by ADM0_A3, Indian states by FIPS. States too
small for 110m polygons carry a point marker instead of a path.

## docs/data/stress_gauge.json

The experimental India Stress Gauge (methodology section 9): today's 0-100 gauge,
the per-component percentiles behind it (press, events, market,
wikipedia), the pre-registered weights, the hit-rate against the
pre-registered episode list with per-miss detail, and a 365-day
history. `_meta.registered_weights` records the intended four-component
design. `_meta.latest_available_components`, `latest_missing_components`
and `latest_effective_weights` disclose any per-date renormalization;
`_meta.partial` is true when either the events history or a latest-date
component is missing. The current 2/29 validation result is experimental
and the gauge is not eligible as a headline measure. Weights, detection
rule, and missing-component rule live in
`validation/stress_gauge_weights.json`, committed before any hit-rate
was computed.

## docs/data/receipts.json

Per-channel receipts for the latest published day only (not a
historical archive). Three lanes, labeled per article in `lane`:
`"corpus"` articles were matched inside the same sampled ngrams corpus
the day's scores are computed from (the estimator actually counted
them; matcher, anchor, and tokenizer identical to the series);
`"corpus-extended"` articles matched under the identical matcher in
the REST of the day's minute-files, outside the half-hourly scoring
sample (they exist in the day's monitored coverage; the estimator did
not count them); `"artlist"` articles come from GDELT's bounded
relevance search, restoring wire originals whose syndicated copies the
corpus caught. `n_matched_in_corpus`, `n_matched_extended`, and
`n_artlist_supplement` count the lanes before URL dedup;
`n_pool_unique` counts the merged pool after syndication dedup; up to
150 publish per channel. Each article
carries its source tier from `source_tiers.json` (`null` = "unranked",
never assumed into a tier) and a `match` tag (`"headline"` when a
channel phrase is in the title, else `"full-text"`). Ordering is
credibility (tier), then visible aptness, then arrival order.
`spike_quality_tier12_share` is the tier 1-2 share of the published
list. `_meta.method` says which lane(s) produced the file (the
artlist-only fallback publishes when the corpus files are
unavailable). Tiers order presentation only and never enter any score.

## docs/data/receipt_identity.json

An independently retryable source-link surface for the exact completed UTC
D-1 day. It is not a score input and never writes or substitutes for
`receipts.json`, `receipts_archive.json`, the NGram caches, shares, history, or
latest scores. Each of the five exact registered channels is either
`available` with at most five deduplicated `{title,url,domain}` records or
`unavailable` with a typed reason. An empty `articles` array means a completed
request returned zero valid links; an unavailable block is missing evidence,
not zero.

The lane is default-deny. The committed profile remains
`inactive_pending_human_signature`, the GDELT DOC source decision remains
`review_required`, and production signer trust is empty, so the current public
form is a value-free refusal and no source request occurs. Future activation
requires both a trusted human-signed source decision and a separately signed
closed profile authorizing exactly `cite_metadata`, `model_processing`, and
`publish_extract`. It never requests, retains, or republishes article bodies,
snippets, descriptions, bylines, images, story/document identifiers, raw
responses, or full source records. GDELT requires attribution for use of its
datasets. Headlines here identify and link to publisher-controlled works;
GDELT's dataset terms are not presented as a publisher copyright sublicense.

The receipts page renders these links only when `target_date` exactly matches
the current published score date. A stale or future identity payload therefore
cannot masquerade as the score day's evidence. Source or rights failure affects
only this payload and never blocks the aggregate score.

Same-target retries are monotone over the exact regular Git blob at the current
remote parent. Every previously available channel retains its exact ordered
article rows, while later retries may recover additional channels. The check is
repeated against the exact candidate parent immediately before push, so a
rebase cannot silently replace a stronger same-day payload with a weaker or
different one. Only a current rights refusal may withdraw all article values;
that transition emits the closed value-free unavailable state instead.

## docs/data/uncertainty.json

95% sampling bands for sample-estimated daily scores, keyed
`days.<date>.<channel> = [lo, hi]` in percentile-score units (0-100),
plus `days.<date>.composite`. Construction: the day's matched share
(sum of sub-query group shares over `n` sampled documents; the
sum-of-groups construction can count a document under two groups, so
the effective count inherits that convention) gets a Wilson 95%
interval, and both bounds pass through the same splice ratio
(`ngram_calibration.json`) and the same trailing-percentile transform
as the published point value. The composite band is the mean of
channel bounds — an envelope, conservative because channel sampling
errors are independent. The frozen artifact covers exactly
`_meta.first_banded_date` through `_meta.last_banded_date` (currently
2026-06-30 through 2026-08-07). Earlier and later published days carry no
published band; absence is not a zero-width interval or a claim of certainty.

## docs/data/robustness_series.json

The overlay behind the validation page's robustness correlations:
weekly mean percentile scores of the primary index and its registered
narrow/broad dictionary variants (`dictionaries_alt.json`), keyed
`channels.<ch>.{primary,narrow,broad}` aligned to the shared `weeks`
axis, over the window where all three exist (`_meta.window`; the
variants begin 2022-01-01). `null` = the variant store has no data
that week, shown as a gap, never interpolated.

## Conventions

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

## docs/data/expert_shelf.json

Latest publications from the registered think-tank roster
(think_tanks.json), titles and links only, tagged to channels by the
frozen dictionaries; items matching no channel are kept as general.
Institutions without a public feed are carried in the registry with
that status. As of 2026-08-06 the roster includes ReliefWeb (UN
OCHA), India primary-country filter — UN-provenance situation
reports joining the shelf under the same titles-only rule (S4);
ReliefWeb is an evidence shelf source only and, like every
aggregation, never a data input to any score.

## docs/data/precision.json

The standing precision audit: machine labels under the versioned
rubric (auditor/RUBRIC.md), per-channel precision published as found,
never tuned. Marked UNCALIBRATED until the author's independent
labels reach the registered threshold (n=100); the agreement
statistic then publishes with its n. Abstentions counted, not
guessed.

## docs/data/reliability.json

The morning contract's measured record, computed from git commit
timestamps: day D final by 06:30 IST on D+1 (06:00 before 2026-08-11). Pre-contract days appear
as context; misses stay listed forever.

## docs/data/predictions.json

The Prediction Archive's registry: every dated, falsifiable
expectation, registered before outcomes are known, graded at horizon,
append-only.

## docs/data/comparators.json

Four comparator country series (India, Pakistan, Indonesia, Vietnam)
from one registered shared vocabulary (comparators.json at repo root)
anchored per country. `countries.<k>.weeks[]` and `.pct[]` are weekly
means of the trailing-730-day percentile of that country's own
coverage-share history; only complete weeks publish. `latest` repeats
the final complete week's value. Cross-country comparison is
rank-vs-rank; levels reflect Anglophone press attention, disclosed.

## docs/data/predictability.json

Directed lead-lag study on daily changes: for each pair, the R-squared
increment from adding five lags of the candidate leader to five own
lags, with a permutation p-value from time-shifted nulls (300 draws).
Reported as found; predictability in this sense is association across
time, never causality.

## docs/data/episode_actors.json

Per-episode driver decomposition from the dyad layer, keyed
"channel|start": partners whose India-pair event counts in the episode
window most exceed their trailing 90-day baseline, split into the
channel's registered partners (attribution) and other unusually active
dyads (context, never attribution), with cooperation-conflict splits.

## docs/data/api_contract.json

The frozen v2 API contract (`scripts/generate_api_contract.py`,
committed and hand-frozen, never regenerated by the daily pipeline):
every served endpoint's format, description, and top-level "frozen
fields" (JSON keys or CSV columns) promised stable within major
version 2, plus the contract's promise, deprecation policy, and access
terms in `_meta`. Rendered for humans at `docs/api.html`. See
methodology.md section 12 for the versioning rule.

## docs/data/exposure_traversal_demo.json

A deterministic synthetic L0 traversal through the canonical exposure edges in
the shared Max fixture world. It starts from the fixture event, selects only
typed, method-bound paths allowed by the signed synthetic release, retains edge
units and denominators, and carries explicit no-path and missingness semantics.
Its release, object, method, schema, rights and temporal identities are the same
ones certified across the other published Max engine records by
`max_state_join_demo.json`.

This is a fixed conformance vector, not a live lane. It establishes that the
traversal contract composes without cross-world identity drift; it does not
establish a real event, entity, source, right, dependency, exposure,
propagation, forecast, causal relationship, recommendation or adoption.

## docs/data/max_state_join_demo.json

The deterministic shared-world certificate for the synthetic Evidence Output,
Exposure Traversal, Sensor Fusion and Shock Compiler records. It verifies one
release identity, no object identifier bound to competing content digests, one
rights position per source, compatible temporal boundaries and exact declared
coverage denominators. The certificate computes
`evidence_class = synthetic_nonproduction` and `licensed_maturity = L0`.

Agreement is not accuracy. This certificate proves composition of four engine
contracts over one synthetic fixture; it does not re-derive their results or
promote them into real observations, real exposure, production readiness,
external utility or institutional adoption.

## docs/data/public_api_byte_manifest.json

Deterministic byte inventory for every contract endpoint except itself. Each
entry binds the public path, repository path, contract format, Git mode, byte
length and SHA-256 digest. `universe` publishes all three denominators: 120
contract endpoints, 119 hashed endpoints and one exact self-exclusion. The
generator reads one stage-0 Git index or named Git tree; mutable worktree
overlays are not inputs. The generic publisher refreshes it after rebase and
before the committed gate, while the final-publication CAS adds it to both
the rights-authorized final class and the exact value-free refusal class.

This is repository-candidate consistency only. It is not a signature,
deployment attestation, rights decision, source-truth proof, atomic-hosting
claim, penetration test or security certification.

## docs/data/daily_brief.json

**Withdrawn 2026-08-08; stable-shaped null tombstone served during the v2
deprecation window through at least 2026-11-06.** The experimental
language-model brief stated stress-gauge values absent from its supplied
context, interpreted a tier-sorted displayed-source share as pool quality,
called displayed title-key representatives the articles underlying a score,
and eventually paired 2026-08-07 scores with 2026-08-06 receipts. Its
prediction-language lint did not establish factual grounding.

The workflow and module now stop before any model call or prose-payload write.
The endpoint retains its frozen top-level fields, but `composite` and every
channel are null and `_meta.status` is
`withdrawn_factual_grounding_failure`. Generated prose may return only under a
new, versioned design that mechanically ties every numeric and entity claim to
cited payload fields and rejects unsupported text. The failed outputs and
withdrawal are recorded in the corrections ledger; they are not IGRM evidence.

## docs/data/ucdp_context.json

Monthly organized-violence event counts and best-estimate fatalities
located in India, from the UCDP Georeferenced Event Dataset (pinned
annual release, finalized) extended by UCDP Candidate monthlies
(`preliminary: true` per month; replaced when the next annual release
finalizes them). Keyed `india.<YYYY-MM> = {events, deaths_best,
preliminary}`, 2017 on. **Context beside the salience index, never an
input**: IGRM measures press attention, UCDP records violence, and
divergence between them is a documented finding. Cite UCDP for these
numbers, not IGRM. Raw per-event store (id-keyed, revisable):
`data/raw/ucdp_events.csv`.

## docs/data/receipts_archive.json

Available recent receipts archive: per channel and day (up to 7 days from
the committed corpus day-caches), the matched articles assembled
identically to `receipts.json` (same matcher provenance, tier sort,
syndication dedup, lane labels), capped at `_meta.per_day_cap` per
channel-day (`n_matched` still reports the day's full match count).
Today's full list lives in `receipts.json`. `_meta.available_days` and
`complete_window` disclose whether all seven cache days exist. The archive
never implies a complete week when it does not have one, and depth comes
from days, never from padding.

## docs/data/episode_terms.json

Term-level attribution per channel-day: how many matched-article
HEADLINES in the day's corpus cache contain each registered phrase
(`days.<date>.<channel>.term_headline_hits`), plus
`n_matched_titles`. Derived from the same corpus the scores come from;
reproducible from the repo alone. Headline attribution undercounts
body-text phrases (stated), and the record starts at
`_meta.first_day` — earlier episodes carry no attribution rather than
a refetched guess.

## docs/data/aptness.json

Machine aptness labels for every article in the current
`receipts.json`, keyed `channels.<ch>.<url> = "ON"|"OFF"|"ABSTAIN"`,
produced by `claude-haiku-4-5` under the registered rubric
(`auditor/RUBRIC.md`, version in `_meta.rubric_version`) from headline
and domain only. **Display-layer only**: the receipts page collapses
OFF articles behind a visible count with a toggle — nothing is
deleted, and no score is touched anywhere. `_meta.founder_agreement`
publishes the machine's measured agreement with the founder's own
rulings (the human labels remain the calibration gold standard).
`_meta.date` must match `receipts.json`'s date for labels to apply;
on mismatch the site shows unfiltered receipts.

## docs/data/status.json

Operational status, derived entirely from committed files:
`sources[]` — each data source's latest data day (`latest_data`),
its age in days, and the ex-ante freshness window
(`expect_within_days`) it is judged against, with `ok` computed by
rule, plus a `note` when data is absent for an honest reason. A derived
file's build date may appear separately as `output_generated`, but is never
substituted for an unavailable upstream data date;
`lanes[]` — each selected registered operational lane's last write stamp (`last`), its explicit
`measured_day` where one exists, and the file both come from;
`alignments[]` — registered cross-payload measurement-day joins, with
the two evidence files and fields, the observed `day_difference`, one
of `aligned|lagging|ahead|unavailable|invalid`, and the reader-visible
effect of a mismatch; `morning_contract` — the on-time rate summarised from
`reliability.json`. The windows are operational expectations, not
promises: the morning contract is the only promise. A valid older
measurement day is published as state and does not fail publication;
features that require that join must refuse or fall back as stated in
the alignment record. Rendered at
`status.html`, regenerated by the daily run (`src/status_data.py`).

## docs/data/permanence.json

The permanence lane's record (M2): the result of the latest Internet
Archive Save-Page-Now request for each key page (`wayback[]` — url,
HTTP status, `ok`) and the latest Software Heritage save-code-now
registration of the repository (`software_heritage`). Runs twice daily
after the publish slots (`.github/workflows/permanence.yml`),
fail-soft: an archive outage is recorded, never hidden, and never
blocks the pipeline. Captures are browsable at
`web.archive.org/web/*/igrm.in`; the repository's archived history at
`archive.softwareheritage.org`. Citability is designed to survive this
project's own infrastructure.

## docs/data/exposure_sectors.json

The registered sector-to-channel exposure map (`sectors.json` v1.0.0)
with the deterministic weighting rule the exposure page computes with
(`_meta.weight_rule`): shares normalize to 1, each sector's share
divides equally across its registered channels, channel weight sums
across sectors. Per sector: `label`, `channels`, `rationale`,
`nse_index` (null until the measured-sensitivity lane ships).
Retrieval and description only — an exposure profile re-cuts published
numbers by the reader's own frame and adds no new claim, no forecast,
and no risk score. Rendered at `exposure.html`; profiles encode in the
URL (`?s=sector:share,...`), no accounts, nothing stored. Amendments
to the map are dated changelog entries by the founder, never silent.

## docs/data/tone.json

Tone as a second axis (G-track layer 1): per channel per day, the
mean GKG V2Tone of the channel's MATCHED articles — the same articles
the registered dictionaries selected — joined by URL in BigQuery
(`days.<date>.<channel>.mean_tone`, GDELT's conventional roughly
−10..+10 scaling), with the join rate disclosed (`n_tone_found` vs
`n_matched`; GKG does not carry every URL). Tone is an annotation,
never a filter, and enters no score, percentile, or composite
(methodology changelog v1.7.0). Absent without the CI lane's GCP
credentials — fail-closed, the axis is simply missing, never guessed.

## docs/data/spike_breadth.json

Spike breadth (G-track layer 3): per channel per day, the number of
distinct source domains among matched articles
(`days.<date>.<channel>.n_domains`), total matches, and the largest
single domain's share (`top_domain_share`; near 1.0 means a
one-outlet story, low values a broad-based narrative). Computed from
the committed receipt day-caches with the identical union-plus-anchor
arithmetic the day's estimator uses — the registered dictionaries
chose every article counted. Descriptive context beside
spike-quality; breadth enters no score. Depth grows automatically as
extended day-caches accrue.

## docs/data/sector_sensitivity.json

Measured sector sensitivities (E2, on the founder-signed sectors.json
v1.1.0 mapping): for each sector with a signed NSE index, the index's
cumulative return relative to Nifty over 1/5/20 trading days from the
start of each episode in the sector's registered channels
(`sectors.<key>.channels.<ch>.<window>`: `mean`, `ci95`, `p_boot`,
`n`, `bh_significant_10pct`). Seeded bootstrap; Benjamini-Hochberg at
10% across the full grid, same discipline as the event study — on
first computation NO cell survived correction, and that negative
result publishes in `_meta.multiple_comparisons`. Association, never
causation; sensitivities change no weight, score, or exposure
reading. Sectors without a signed index publish nothing. Yahoo prices
are used but not redistributed.

## docs/data/sector_&lt;key&gt;.json (fifteen per-sector feeds)

E4: one machine-consumable feed per registered sector
(`sector_textiles_apparel.json` … `sector_petroleum_refining.json`),
regenerated nightly as a pure re-cut of already-published payloads:
the sector's registered channels with today's score, 95% sampling
band, weight under the registered exposure rule, and a receipts URL
per channel; `measured_sensitivity` appears only where a signed NSE
mapping exists (see sector_sensitivity.json). Nothing is computed
here that is not already published elsewhere; the salience-not-risk
statement travels in every file's `_meta`.

## docs/data/alerts.json

Registered alert events (design/alerts_webhook.md, founder-signed
2026-08-06), Phase 0 poll model: `alerts[]` newest first, 90-day
retention, stable `id`s for consumer dedupe. Types: T1
`band_separated_move` (a channel's 95% sampling band does not overlap
the previous day's — the arithmetic that separates real moves from
sampling noise), T2 `composite_percentile_crossing` (trailing 90th
percentile, 730-day window, and both band edges on the crossing's
side), T3 `integrity_event` (the morning contract's own misses,
because the instrument's failures alert the same channel its
successes do). Every field is a number or the direction of a
completed move; nothing forecasts. Webhook push (Phase 1) follows a
four-week observation period per the signed design.

## docs/data/forecasts.json

The V11 forecast experiment's public record
(`validation/forecast_registration.json`, founder-signed 2026-08-06).
RESEARCH SURFACE ONLY, rendered at `research/forecasts.html` under its
mandatory header: an experiment about the index, not advice, presumed
null until the registered criterion resolves. `questions[]`: weekly
mechanical questions (any spike day within 14 days, the registered
episode rule), each committed before its window opens, with both
arms' probabilities recorded at generation (`p_climatology` —
trailing 104-week frequency; `p_salience` — frozen-coefficient
logistic on two registered inputs,
`validation/forecast_logit_frozen.json`), outcome graded mechanically
at window close, voids counted. `cumulative`: Brier per arm. The fork
criterion is frozen in the registration; there is no third outcome.

## docs/data/back_extension.json

The historical attention proxy, 1979–2019 (M1; registration frozen
before first computation in `analysis/back_extension_memo.md`). A
DIFFERENT construct from the live instrument — monthly shares of
global event-mentions by frozen actor-pair filters from GDELT's 1.0
and 2.0 event streams — never spliced into or drawn with the 2017+
series. `anchor_grades[]`: nine pre-registered episodes graded
top-decile-or-miss against trailing-10-year percentiles (Kargil
100.0; Blue Star's 52.3 miss is the registered construct-edge
finding). `overlap_audit`: raw-share correlation vs the live
instrument over 36 shared months — border channels track (0.893,
0.848); us_trade and gulf_energy fall under the frozen 0.4 threshold
and therefore publish NO historical series (`series` carries only
channels that pass; the refusal is the finding). Shipping is excluded
entirely: chokepoint salience has no actor coding.

## docs/data/cow_mids.json

Correlates of War MID 5.0 aggregates (S12): distinct militarized
interstate disputes involving India by start year and opponent
(`disputes_by_start_year.pakistan/.china`), 1816–2014 —
historian-coded conflict as independent context beside the M1
historical attention proxy. Static dataset, fetched once; only
aggregates publish with attribution (Palmer et al. 2022, Correlates
of War Project). Context only; enters no score.

## docs/data/energy_context.json

India's monthly crude-oil imports in thousand barrels per day, as
reported to JODI (the IEA/OPEC-backed official oil-data exchange;
open annual CSVs, verified endpoints) — official energy statistics as
context beside the gulf_energy channel (S3). Trailing 48 months;
`latest` names the latest *reported* month, because JODI reporting
lags one-to-three months and recent values revise. Attribution in
`_meta`; context only; enters no score.

## docs/data/shares.csv and shares.json

**The quantity, not the transform.** Each channel's daily share of the
GDELT-monitored article corpus, in percent — the input from which the
published percentile series is computed. Promoted to a first-class
artifact so a reader who disagrees with the normalization can apply
their own and recompute everything. `shares.json` carries the
metadata, including `known_gaps`: the days absent from the store
entirely (21 as of 2026-08-07), listed rather than interpolated,
because a user computing monthly means deserves to know which months
are short. Shares are commensurable across channels and across years;
percentiles are not (they are within-channel ranks against each
channel's own trailing two years), and percentiles saturate during
sustained crises where shares do not — see methodology v1.9.0.
The `source` column names the instrument that measured each day:
`doc_api` for GDELT DOC API counts (3,446 days) and `ngram_bridge` for
days measured by the Web NGrams feed and divided by an estimated
per-channel splice ratio to reach the API's scale (38 days, 2026-06-30
onward). **These are two instruments, not one series.** Any statistic
computed across the boundary inherits the linking constant's
uncertainty, so the label travels in the data rather than in a
footnote; `shares.json._meta.instrument_is_not_constant` carries the
splice ratios, the recorded-versus-reconstructed basis of each label,
and the bound on reconstruction impurity.

## docs/data/syndication.json

**Was that spike more newsrooms, or more copies?** Per channel per day,
articles divided by distinct normalized headlines among them — the
multiplier by which republication inflates a channel's article count.
The index counts articles, so one wire story carried by two hundred
outlets moves a channel exactly as far as two hundred newsrooms
independently reacting; this is the measurement of how often that
happens. On 2026-08-05, `pakistan_west` ran 160 articles across 46
distinct stories (×3.478) while `china_east` ran 17 articles across 17
stories (×1.000). **It corrects nothing** — republication is a real
editorial decision, not noise, and no defensible deflation exists;
nothing here enters a score. The estimator is biased downward at small
samples, because a duplicate is visible only when both copies land in
the scan: the same channel-day reads 1.923 at 28,575 documents sampled
and 3.478 at 119,349, so only scans of at least 60,000 documents enter
the history and `n_docs_sampled` travels with every row. A companion
and deliberately non-identical measure, `articles_sum / sources_sum`,
is computed over the whole GDELT event population in
`data/raw/events_daily.csv`; the two are reported separately and never
averaged, because dividing by sources also counts one outlet running
several distinct pieces on the same event.

## docs/data/freshness.json

**Is every number on this site actually current?** For every non-exempt
JSON payload, the audit publishes the write date (`generated`, with additive aliases
`written_date`/`write_age_days`) and any explicitly declared measurement
day (`measured_date`/`measured_age_days`). A file rewritten today can still
describe yesterday; those clocks are never treated as synonyms. Dated CSVs
carry their last measured row but no embedded write timestamp, recorded as
`write_time_status: not_embedded_in_csv`. Every exemption remains listed
with its reason. The write-time age is checked
against the cadence its lane is supposed to run at.
A lane that stops writing does not break — it keeps serving its last
value, and a stale number is quoted exactly as confidently as a fresh
one. `status.json` watches upstream *sources*; this watches every payload
enumerated in `freshness.json`, which is where the silence actually lives.

**A payload with no `_meta.generated` counts as a failure, not a pass.**
Three payloads (`alt_specs`, `seasonality`, `priced_risk`) had no
timestamp at all when this was built, and `validation.json` — the
credibility payload — had none either, because it is assembled block by
block and no block owned the file. All four now carry one. An auditor
that silently skips what it cannot read is worse than no auditor,
because it reports green.

Exemptions are listed with a written reason each: the frozen API
contract, the author-paced notes, the append-only Prediction Archive,
`episodes.json` (a bare array with nowhere to put `_meta`, written in
the same commit as `history.json`), and this file itself. The audit
fails the enrichment run when anything is stale or undatable — never
the 06:00 contract lane, because a staleness report must not be able to
stop a publish. A valid but older measurement day is not itself a crash;
`status.json.alignments[]` publishes whether it can safely join to the
current reference day and what the affected reader surface does instead.

## docs/data/vintages.json

**What did the index say on the day it said it?** Every daily publish is
a commit, so `docs/data/history.csv` at a given SHA is exactly what the
site served that morning. This file diffs every such vintage against
what is served today, across the composite and all five channels on
their overlapping dates — the question that decides whether a backtest
built on the current file carries look-ahead bias.

**Finding: 23 of 25 vintages show zero changed values.** The series is
append-only in practice — days are added, not rewritten. The single
revision episode is the two 2026-07-27 vintages (101 values across 17
days, max 99.4 percentile points), and it sits exactly on methodology
v1.0.1 of 2026-07-29, which changed the percentile computation and is
recorded in the changelog. *A revision with a dated published cause is a
version; a revision without one is a defect.*

It is also a **tripwire**, which is the real reason it runs nightly. Any
vintage that differs without its date appearing in
`REGISTERED_REVISIONS` fails the build, so a future silent rewrite — a
rebuilt store, a dictionary applied retroactively, a splice ratio
quietly adopted — surfaces the next morning instead of being found by a
user whose results stopped replicating.

Retrieve any vintage yourself, with no tooling and no cooperation from
this project:

```
git log --format='%H %ad' --date=short -- docs/data/history.csv
git show <SHA>:docs/data/history.csv > history_as_of_that_day.csv
```

## docs/data/detector_blindness.json

**The detector cannot see a second crisis for about three months.**
Episode detection fires when a channel's share exceeds its trailing
90-day mean plus 2σ. A crisis therefore enters the very window its own
future threshold is computed from: the mean rises, the standard
deviation rises faster, and the bar climbs for ninety days — peaking
*after* the crisis is over in 521 of 523 analysed episodes. The payload's
`excluded_episodes` lists any detected episode the diagnostic cannot
evaluate and gives the reason; the current one-row exclusion is caused by
an absent pre-episode source day rather than being silently dropped.

Worked example, `pakistan_west` through Pahalgam and Sindoor: the
threshold was 0.0244 on 2025-04-21, and 0.6912 on 2025-07-20 — a **28×**
higher bar. On 2025-05-20 the channel's share was 0.1340, five and a
half times the pre-crisis threshold and an unambiguous spike by the
standard that applied three weeks earlier, and the detector stayed
silent.

`n_days_suppressed` counts days after an episode whose share cleared the
threshold in force the day *before* that episode began but not the live
one — days a pre-crisis detector would have flagged and this one did
not. Across the whole series that is **2,158 distinct channel-days,
12.4% of all channel-days**, deduplicated because episode windows
overlap (summing per-episode counts would exceed the length of the
series). Read `largest_episodes_by_peak_share`, not the median: small
blips barely move the bar, so the median multiple is ~1.4, and the
damage is entirely in the tail — the detector is least able to see a
second event exactly when the first was most serious.

**The registered rule is not changed**, because every obvious fix is
worse: excluding spike days from the baseline makes the analyst define
spikes before measuring them, a fixed threshold abandons the
per-channel adaptivity that makes five channels comparable, and a longer
window delays first detection, which is what the detector is for. The
cost is now measured rather than inferred.

## docs/data/wiki_hindi.json

**Does this measure Indian attention, or Anglophone attention about
India?** The index is built from an English corpus and was
cross-validated against English Wikipedia, so every leg of the apparatus
was Anglophone and none of it could tell those two apart. This file is
the test that can: the same registered article set read on Hindi
Wikipedia — titles resolved through Wikipedia's own interlanguage links,
never chosen by hand — correlated against the same daily shares over
3,394 overlapping days. `english_wikipedia_same_statistic` carries the
identical computation in English, because the Hindi numbers are
uninterpretable without it.

**Finding: English leads on 5 of 5 channels, in both levels and
changes, with no channel where Hindi leads.** Day-to-day changes fall
from 0.223/0.340/0.589/0.117/0.564 (English) to
0.160/0.132/0.163/0.050/0.030 (Hindi). `us_trade` is the study's only
negative level correlation (−0.136). The thin-traffic objection fails
on the project's own data: `us_trade` has the highest median Hindi
traffic and the worst agreement, `gulf_energy` the lowest and the best.

Six registered articles have no Hindi counterpart (`missing_english_titles`)
and are reported, never substituted; they are the
foreign-policy-apparatus topics, while the two India-adjacent channels
resolve completely. `changes_pearson` is the load-bearing figure — levels
can correlate through a shared trend alone. Undefined correlations
publish as null rather than NaN. **Nothing here adjusts a score**; it is
evidence about what the index measures, and anyone citing this as a
measure of *Indian public* salience should read it first.

## docs/data/monthly.csv and monthly.json

**The series at the frequency economists actually work in.** One row per
calendar month: `share_<channel>` are means of the daily
percent-of-corpus shares, `composite_mean_of_ranks` is the mean of the
daily composite percentiles. It ships because twenty users aggregating
this themselves would make twenty different silent decisions about the
same three traps, and their results would stop being comparable.

*Short months.* `coverage` is share-data days present over days expected (for the
current month, over days elapsed). A month below 80% publishes its row
with **null values** and a stated `refused_reason` rather than a mean
over the survivors — 2025-06 has 14 of 30 days and is the case that
forces the rule. The row is never silently absent: a gap you can see is
a limitation, a gap you cannot see is an error.

*Mixed instruments.* `mixed_instruments`, with `n_days_doc_api` and
`n_days_ngram_bridge`, marks months spanning the DOC API/NGrams-bridge
boundary, where the mean crosses two instruments joined by an estimated
splice ratio. 2026-06 is the first such month. Users who need one
instrument can drop these rather than discover them.

*Averaging ranks.* `composite_mean_of_ranks` is the mean of daily
percentiles, which is **not** the percentile of the monthly mean; the
two diverge most in skewed months, which are the months of interest.
Both are published so the difference is visible rather than resolved by
whoever aggregates first. The `share_*` columns mean the same thing in
every year and are the recommended input to anything estimated;
percentiles are ranks against a moving two-year window and are offered
as convenience. `n_days_composite_present` and `composite_coverage`
separately report how many ranked daily composite scores exist; a monthly
composite below the same 80% floor is null with a
`composite_refused_reason`. JSON uses `null` for missing numeric values;
CSV represents the same values as blank cells.

## docs/data/episode_themes.json

Narrative composition (G4): per channel per day, the GKG theme codes
carried by the day's MATCHED articles — the registered dictionaries
choose every article and BigQuery only reads its `V2Themes`, so themes
are an annotation, never a filter, and enter no score. `top_themes[]`
gives each code with the share of themed matched articles carrying it;
codes stay raw GDELT identifiers for auditability. `n_themed` vs
`n_matched` discloses the join rate. Trailing 30 days.

## docs/data/historical_intelligence.json {#historical-intelligence}

Registered readings of the 1979–2019 back-extension
(`back_extension.json`), and of nothing else. **The archive is a different
construct from the live 2017+ index and is never spliced to it**: it counts
actor-pair event mentions, not press salience, so no statistic here is
comparable to a published IGRM score. Eligibility is inherited from the
source payload's `overlap_audit` verdicts, not re-decided here:
`pakistan_west` (r = 0.893 over 36 overlap months) and `china_east`
(r = 0.848) are marked `tracks`; `us_trade` (r = 0.216) and `gulf_energy`
(r = 0.153) carry the verdict `DOES NOT PUBLISH (negative finding)`, and
`shipping` was excluded at registration for having no defensible historical
event analog for its construct. Each refusal is published in
`channel_eligibility.refused` with its reason rather than omitted. Frozen:
the archive ends 2019-12, and the payload is exempt from the freshness clock
for that reason, not because it is unmaintained.

`regime_baselines.rows[]` — mean, median, p90, min and max per channel,
series and registered period. **Periods are the four calendar decades
1979-1989, 1990-1999, 2000-2009 and 2010-2019 and are explicitly not
political regimes**; the word names a slice of the calendar. Every row
carries its own denominators: `n_months_in_period` (calendar count),
`n_observed` (non-null count) and `coverage_fraction` = `n_observed` /
`n_months_in_period`. A period with fewer than `min_observed_months` (24)
observations is refused — `available: false` with `unavailable_reason` —
never computed over whatever happened to be there.
`regime_baselines.non_comparability` carries three standing warnings,
including that `pctl_10y` is undefined for the archive's first 120 months
and that cross-channel comparison of `raw_share` is not meaningful, each
channel's share being relative to its own filter rather than a shared
denominator.

`structural_breaks.rows[]` — a **descriptive scan, not a change-point
model**. Every split with at least `min_segment_months` on both sides is
scored by the absolute Welch *t* between segment means, and the largest is
reported as the single candidate. The null is a seeded permutation
(`n_permutations` 2000, `seed` 20260809, deterministic): values are shuffled
without replacement, which destroys time ordering while preserving the value
distribution, and `p_value` is the fraction of permutations whose maximum
statistic met or exceeded the observed one. `sensitivity_sweep[]` repeats
the scan at minimum segment lengths 12, 24, 36 and 48;
`stable_across_all_settings` and `distinct_candidates_across_settings`
report whether the answer survives the setting. It frequently does not —
`pakistan_west` returns 1980-01 and 1984-01 across the sweep and is
published as unstable. `structural_breaks.language_rule` binds the prose: a
result is a candidate break in the measured series, never a historical
cause, a turning point, a regime change, or an explanation of any event. The
series measures attention, so a break is a break in attention and nothing
more.

`analog_retrieval.by_channel.<ch>.<YYYY-MM>` — the nearest other months in
the same channel by Euclidean distance over standardised registered features
(`level_pctl_10y`, `change_12m_raw_share`, `volatility_12m_raw_share`),
excluding a ±`exclusion_window_months` (6) neighbourhood of the query so
adjacency is not mistaken for similarity. **Missingness is named, never
filled**: a feature null on either side of a pair is dropped from that pair's
distance, reported in `features_excluded_as_null`, and counted in
`n_features_used`; a pair sharing fewer than `min_features_for_match` (2)
usable features is refused rather than distance-imputed. No null is ever
replaced by zero or by a mean. Retrieval is a similarity lookup over one
measured series: it carries no claim that similar months share causes, and
no claim about what follows them.

`event_archetypes.rows[]` — an archetype is attached to a month only where a
**human-authored** registered anchor exists in the source payload's
`anchor_grades`. `machine_generated_permitted` is `false`; a month with no
registered anchor reports `available: false` with reason
`no_registered_human_authored_archetype` and is never given an inferred one.
A knowledge-cutoff rule (`_meta.knowledge_cutoff`, `archive_end` 2019-12)
refuses any label, annotation or category whose evidence postdates the
archive, and publishes the refusal rather than dropping it silently, so
present-day categories cannot leak backwards into a historical view.

`_meta` carries `contract_sha256`, `source_sha256` and
`implementation_sha256`, so a citation can pin the registration, the input
and the code that produced the numbers. Regeneration is byte-identical and
CI asserts it. Rendered for humans at `docs/history-lab.html`; flat
downloads at `downloads/igrm-historical-regime-baselines.csv` and
`downloads/igrm-historical-analogs.csv`. Registered in
`governance/historical_intelligence_contract.json`. Nothing in this payload
is a forecast, and no field states or implies what happens next.
