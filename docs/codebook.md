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
`descriptive_only` marks outcomes (Brent, gold) with no separable
India-specific component. Association, not causation.

## JSON `_meta` blocks

Every dict-shaped JSON published by the pipeline embeds a `_meta` object
(what the file is, units, license, citation, codebook link, generation
date) so a downloaded file explains itself without this website.

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

## docs/data/event_study.json

| Field | Definition |
|---|---|
| `windows` | Trading-day windows (1, 5, 20), inclusive of first trading day ≥ episode start |
| `units` | Cumulative log return, percent |
| `descriptive_only` | Outcomes with no separable India-specific component (Brent, gold) |
| `channels.<ch>.outcomes.<o>.<w>` | `{mean, ci95:[lo,hi], n}` across the channel's episodes; CI from 1,000 episode resamples |
| `per_episode.<ch>[]` | `{start, outcomes.<o>.<w>}` raw window returns for one episode (no CI; n = 1) |

Outcomes: `nifty_minus_em` (strips global equity beta), `defence_minus_nifty`
(the India-specific hypothesis), `usdinr_minus_dxy` (strips broad dollar
moves), `brent_ret`, `gold_ret` (descriptive).

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

The India Stress Gauge (methodology section 9): today's 0-100 gauge,
the per-component percentiles behind it (press, events, market,
wikipedia), the pre-registered weights, the hit-rate against the
pre-registered episode list with per-miss detail, and a 365-day
history. Publishes only once the events history is complete
(`_meta.partial` stays false on anything served). Weights, detection
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
errors are independent. Days before `_meta.first_banded_date` were
computed over the full monitored corpus and carry no band; absence of
a band is a statement about the estimation design, not missing data.

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
- GDELT days are UTC; market data uses exchange trading days (IST for NSE).
- All return language is associational. Nothing here is investment advice.

## docs/data/expert_shelf.json

Latest publications from the registered think-tank roster
(think_tanks.json), titles and links only, tagged to channels by the
frozen dictionaries; items matching no channel are kept as general.
Institutions without a public feed are carried in the registry with
that status.

## docs/data/precision.json

The standing precision audit: machine labels under the versioned
rubric (auditor/RUBRIC.md), per-channel precision published as found,
never tuned. Marked UNCALIBRATED until the author's independent
labels reach the registered threshold (n=100); the agreement
statistic then publishes with its n. Abstentions counted, not
guessed.

## docs/data/reliability.json

The morning contract's measured record, computed from git commit
timestamps: day D final by 06:00 IST on D+1. Pre-contract days appear
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

The frozen v1 API contract (`scripts/generate_api_contract.py`,
committed and hand-frozen, never regenerated by the daily pipeline):
every served endpoint's format, description, and top-level "frozen
fields" (JSON keys or CSV columns) promised stable within major
version 1, plus the contract's promise, deprecation policy, and access
terms in `_meta`. Rendered for humans at `docs/api.html`. See
methodology.md section 12 for the versioning rule.

## docs/data/daily_brief.json

Machine-written daily brief: one short paragraph per channel plus a
composite line, generated once per day by a language model
(claude-opus-5) from payloads this site already publishes (latest
scores, receipts evidence, stress gauge). It is labeled
machine-written everywhere it appears and is never the author's
voice. The generating prompt is a registered instrument
(prompts/daily_brief.md, versioned, append-only changelog), and a
measurement-language lint drops any brief that crosses into
prediction; a dropped channel is null and listed in
`_meta.lint_dropped` rather than softened. Absent entirely on days
the generation did not run (no API key, model refusal): fail-closed
by design. Approved by the author 2026-08-04 (NOTES 0.10 option b).

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

Trailing-week receipts archive: per channel and day (up to 7 days from
the committed corpus day-caches), the matched articles assembled
identically to `receipts.json` (same matcher provenance, tier sort,
syndication dedup, lane labels), capped at `_meta.per_day_cap` per
channel-day (`n_matched` still reports the day's full match count).
Today's full list lives in `receipts.json`; this file exists so a
channel page always carries a week of enumerable, dated evidence.
Depth comes from days, never from padding.

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
rule, plus a `note` when data is absent for an honest reason;
`lanes[]` — each pipeline lane's last evidence stamp and the file it
comes from; `morning_contract` — the on-time rate summarised from
`reliability.json`. The windows are operational expectations, not
promises: the morning contract is the only promise. Rendered at
`status.html`, regenerated by the daily run (`src/status_data.py`).
