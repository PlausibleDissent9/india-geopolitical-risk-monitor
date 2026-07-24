# IGRM Codebook

Column-by-column definitions for every published file. Units and
construction; the reasoning lives in [methodology.md](../methodology.md).

## data/raw/gdelt_volume.csv

| Column | Definition | Units | Range |
|---|---|---|---|
| `date` | Calendar day, UTC (GDELT's day convention) | ISO date | 2017-01-01 onward |
| `pakistan_west` … `shipping` | Share of all GDELT-monitored articles that day matching the channel's query; where a channel needs two sub-queries (length budget), the SUM of the two shares — a slight upper bound on the union | percent of corpus | ≥ 0, typically ≪ 1 |

## docs/data/latest.json

| Field | Definition |
|---|---|
| `date` | Last day with a full composite |
| `definition` | The one-line construct definition shown under the headline |
| `composite` | Unweighted mean of the five channel percentiles, 0–100 |
| `channels.<ch>.score` | Channel percentile vs its own trailing 730 days, 0–100 |
| `channels.<ch>.label` | Display name |

## docs/data/history.json

| Field | Definition |
|---|---|
| `dates[i]` | ISO date for position `i` in every parallel array |
| `composite[i]` | Composite percentile that day (null before 180 trailing obs) |
| `channels.<ch>[i]` | Channel percentile that day |
| `labels` | Channel display names |
| `wikipedia.*` | Same structure computed from Wikipedia pageviews (present once the second source is active); levels are never comparable across sources — each is percentile-normalized independently |

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

## Conventions

- Every percentile is computed against the series' own trailing 730 days,
  minimum 180 observations, never using future data.
- GDELT days are UTC; market data uses exchange trading days (IST for NSE).
- All return language is associational. Nothing here is investment advice.
