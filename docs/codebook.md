# IGRM Codebook

Column-by-column definitions for every published file. Units and
construction; the reasoning lives in [methodology.md](../methodology.md).

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

## Conventions

- Every percentile is computed against the series' own trailing 730 days,
  minimum 180 observations, never using future data.
- GDELT days are UTC; market data uses exchange trading days (IST for NSE).
- All return language is associational. Nothing here is investment advice.
