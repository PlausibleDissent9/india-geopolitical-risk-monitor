# Indic-language gradient study (2026-08-08)

Every number in this file is written by `analysis/indic_gradient.py` from the committed stores and the Wikimedia API responses; none is hand-typed. The companion JSON is `analysis/indic_gradient_2026-08-08.json`.

## Question

`docs/data/wiki_hindi.json` (2026-08-07) reports that English Wikipedia tracks this index more closely than Hindi Wikipedia does on 5 of 5 channels, in both levels and day-to-day changes, and reads that one-directional gap as the signature of an Anglophone construct. One comparison language cannot say where Hindi sits, though. This study runs the identical apparatus -- same registered article set, same interlanguage-link resolution, same pageviews source, same correlation code imported from `src.wiki_hindi` -- across 6 Indic languages, and ranks them by how much English leads them.

## Method and floors

- GDELT store: `data/raw/gdelt_volume.csv`, ending 2026-08-06 (3484 daily rows).
- English baseline: `english_comparison()` from `src.wiki_hindi`, on the committed `data/raw/wiki_volume.csv` -- shares against shares, the same statistic as every language row below.
- Correlation refusal: fewer than 180 overlapping days refuses; a channel median below 20 views/day refuses; a language resolving fewer than 15 of 29 registered articles publishes as a negative with its counts.
- `changes_pearson` is the load-bearing figure throughout; levels can correlate through a shared trend alone.

## Coverage: how much of the registered article set exists per language

| language | resolved / registered | missing titles |
|---|---|---|
| Hindi | 23 / 29 | 6 |
| Bengali | 22 / 29 | 7 |
| Urdu | 22 / 29 | 7 |
| Tamil | 21 / 29 | 8 |
| Marathi | 18 / 29 | 11 |
| Telugu | 14 / 29 | 15 |

Titles with no counterpart, by how many of the 6 resolvable languages miss them:

| registered English title | missing in N languages | missing in |
|---|---|---|
| CAATSA | 6 | Hindi, Bengali, Tamil, Urdu, Telugu, Marathi |
| Houthi movement | 6 | Hindi, Bengali, Tamil, Urdu, Telugu, Marathi |
| Sanctions against Iran | 6 | Hindi, Bengali, Tamil, Urdu, Telugu, Marathi |
| Trade policy of the United States | 6 | Hindi, Bengali, Tamil, Urdu, Telugu, Marathi |
| Foreign trade of India | 5 | Bengali, Tamil, Urdu, Telugu, Marathi |
| Energy policy of India | 4 | Hindi, Urdu, Telugu, Marathi |
| Piracy off the coast of Somalia | 4 | Hindi, Tamil, Telugu, Marathi |
| H-1B visa | 3 | Bengali, Urdu, Telugu |
| India–Pakistan relations | 3 | Bengali, Tamil, Telugu |
| Iran–Israel relations | 3 | Tamil, Telugu, Marathi |
| Bab-el-Mandeb | 1 | Marathi |
| Cape of Good Hope | 1 | Telugu |
| China–India relations | 1 | Telugu |
| India–United States relations | 1 | Marathi |
| Inter-Services Intelligence | 1 | Telugu |
| Kashmir conflict | 1 | Marathi |
| OPEC | 1 | Telugu |
| People's Liberation Army | 1 | Telugu |

wiki_hindi found its six Hindi misses were the foreign-policy-apparatus topics (sanctions regimes, maritime security). The table above shows how far that pattern extends: titles missing from most or all of the six languages are evidence about which parts of the construct exist in Indian-language public attention at all.

## English Wikipedia baseline (same statistic)

| channel | n | levels_pearson | levels_spearman | changes_pearson |
|---|---|---|---|---|
| pakistan_west | 3393 | 0.4576 | 0.1096 | 0.2233 |
| china_east | 3393 | 0.4185 | 0.1372 | 0.3403 |
| gulf_energy | 3393 | 0.6107 | -0.0856 | 0.5892 |
| us_trade | 3393 | 0.0796 | -0.1093 | 0.1169 |
| shipping | 3393 | 0.7066 | 0.0539 | 0.5644 |

## Per-language results

### Hindi (hi.wikipedia)

| channel | articles | median views/day | n | levels_pearson | levels_spearman | changes_pearson | refused |
|---|---|---|---|---|---|---|---|
| pakistan_west | 6/6 | 527.0 | 3394 | 0.2977 | 0.159 | 0.1596 | -- |
| china_east | 5/5 | 595.0 | 3394 | 0.3178 | 0.0261 | 0.1315 | -- |
| gulf_energy | 4/6 | 161.0 | 3394 | 0.5006 | -0.2946 | 0.1631 | -- |
| us_trade | 4/6 | 602.0 | 3394 | -0.1363 | -0.2062 | 0.05 | -- |
| shipping | 4/6 | 260.0 | 3395 | 0.2781 | -0.0273 | 0.0296 | -- |

### Bengali (bn.wikipedia)

| channel | articles | median views/day | n | levels_pearson | levels_spearman | changes_pearson | refused |
|---|---|---|---|---|---|---|---|
| pakistan_west | 5/6 | 47.0 | 3395 | 0.2842 | 0.085 | 0.1061 | -- |
| china_east | 5/5 | 52.0 | 3395 | 0.2733 | 0.0031 | 0.1488 | -- |
| gulf_energy | 5/6 | 64.0 | 3395 | 0.2153 | -0.1652 | 0.0735 | -- |
| us_trade | 2/6 | 47.0 | 3395 | -0.1661 | -0.256 | -0.0083 | -- |
| shipping | 5/6 | 76.0 | 3395 | 0.3792 | -0.0041 | 0.1975 | -- |

### Tamil (ta.wikipedia)

| channel | articles | median views/day | n | levels_pearson | levels_spearman | changes_pearson | refused |
|---|---|---|---|---|---|---|---|
| pakistan_west | 5/6 | 7.0 | null | null | null | null | median 7 daily views across the channel's Tamil articles is below the 20 floor; a correlation here would be a statement about Poisson noise, not about attention |
| china_east | 5/5 | 19.0 | null | null | null | null | median 19 daily views across the channel's Tamil articles is below the 20 floor; a correlation here would be a statement about Poisson noise, not about attention |
| gulf_energy | 4/6 | 12.0 | null | null | null | null | median 12 daily views across the channel's Tamil articles is below the 20 floor; a correlation here would be a statement about Poisson noise, not about attention |
| us_trade | 3/6 | 30.0 | 3395 | -0.0462 | -0.1224 | 0.0523 | -- |
| shipping | 4/6 | 19.0 | null | null | null | null | median 19 daily views across the channel's Tamil articles is below the 20 floor; a correlation here would be a statement about Poisson noise, not about attention |

### Urdu (ur.wikipedia)

| channel | articles | median views/day | n | levels_pearson | levels_spearman | changes_pearson | refused |
|---|---|---|---|---|---|---|---|
| pakistan_west | 6/6 | 58.0 | 3395 | 0.2903 | 0.123 | 0.1454 | -- |
| china_east | 5/5 | 6.0 | null | null | null | null | median 6 daily views across the channel's Urdu articles is below the 20 floor; a correlation here would be a statement about Poisson noise, not about attention |
| gulf_energy | 4/6 | 11.0 | null | null | null | null | median 11 daily views across the channel's Urdu articles is below the 20 floor; a correlation here would be a statement about Poisson noise, not about attention |
| us_trade | 2/6 | 2.0 | null | null | null | null | median 2 daily views across the channel's Urdu articles is below the 20 floor; a correlation here would be a statement about Poisson noise, not about attention |
| shipping | 5/6 | 9.0 | null | null | null | null | median 9 daily views across the channel's Urdu articles is below the 20 floor; a correlation here would be a statement about Poisson noise, not about attention |

### Telugu (te.wikipedia)

REFUSED: only 14 of 29 registered articles have a Telugu counterpart, below the 15-article floor; a correlation computed on that sliver would be a statement about the sliver, not about the construct, so the language publishes as a negative

| channel | resolved / registered | missing titles |
|---|---|---|
| pakistan_west | 4 / 6 | India–Pakistan relations, Inter-Services Intelligence |
| china_east | 3 / 5 | China–India relations, People's Liberation Army |
| gulf_energy | 2 / 6 | Iran–Israel relations, Sanctions against Iran, OPEC, Energy policy of India |
| us_trade | 2 / 6 | H-1B visa, CAATSA, Foreign trade of India, Trade policy of the United States |
| shipping | 3 / 6 | Houthi movement, Piracy off the coast of Somalia, Cape of Good Hope |

### Marathi (mr.wikipedia)

| channel | articles | median views/day | n | levels_pearson | levels_spearman | changes_pearson | refused |
|---|---|---|---|---|---|---|---|
| pakistan_west | 5/6 | 10.0 | null | null | null | null | median 10 daily views across the channel's Marathi articles is below the 20 floor; a correlation here would be a statement about Poisson noise, not about attention |
| china_east | 5/5 | 26.0 | 3395 | 0.0504 | -0.0539 | 0.0113 | -- |
| gulf_energy | 3/6 | 15.0 | null | null | null | null | median 15 daily views across the channel's Marathi articles is below the 20 floor; a correlation here would be a statement about Poisson noise, not about attention |
| us_trade | 2/6 | 77.0 | 3395 | -0.1382 | -0.2253 | 0.022 | -- |
| shipping | 3/6 | 13.0 | null | null | null | null | median 13 daily views across the channel's Marathi articles is below the 20 floor; a correlation here would be a statement about Poisson noise, not about attention |

## The gradient

English-lead margin = English correlation minus the language's correlation, per channel, averaged over the channels where both report. Smaller margin = the language tracks the index more like English does. Ranked ascending:

| rank | language | coverage | channels reported | English leads both (levels AND changes) | language leads changes | mean changes margin | mean levels margin |
|---|---|---|---|---|---|---|---|
| 1 | Tamil | 21/29 | 1 | 1/1 | 0/1 | 0.0646 | 0.1258 |
| 2 | Urdu | 22/29 | 1 | 1/1 | 0/1 | 0.0779 | 0.1673 |
| 3 | Marathi | 18/29 | 2 | 2/2 | 0/2 | 0.2119 | 0.2929 |
| 4 | Hindi | 23/29 | 5 | 5/5 | 0/5 | 0.2601 | 0.203 |
| 5 | Bengali | 22/29 | 5 | 5/5 | 0/5 | 0.2633 | 0.2574 |

Not rankable (refused before any correlation): Telugu. Refusal reasons are in the per-language sections above; each is a finding about coverage, not an absence of one.

## Where Hindi sits

Hindi ranks 4 of 5 measurable languages by mean changes margin (0.2601); Tamil, Urdu, Marathi track the index more closely than Hindi does. Hindi is MIDDLE of the gradient, not its ceiling: the wiki_hindi comparison under-stated the best-case Indic agreement, and the single-language reading of the Anglophone gap needs the per-language table above rather than the Hindi row alone.

## What this means for the construct name

Across every language-channel pair that cleared the floors (14 pairs over 5 languages), English leads on both levels and changes in 14, and a language beats English on changes in 0. 4 of 29 registered articles have no counterpart in ANY of the six languages (CAATSA, Houthi movement, Sanctions against Iran, Trade policy of the United States), and the widest misses are the foreign-policy-apparatus titles, extending wiki_hindi's misses finding across the gradient. These are measurements of the instrument, not adjustments to it: the index tracks English-language attention to India better than Indian-language attention in every language measured here, which is the pattern the name 'Anglophone press salience' describes and the name 'Indian salience' does not. Nothing here changes a score.

## Provenance

- Generated: 2026-08-07T20:25:30Z
- Pageviews API: `https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{lang}.wikipedia/all-access/user/{article}/daily/{start}/{end}`
- Langlinks API: `https://en.wikipedia.org/w/api.php` (batched, resolution never hand-picked)
- Request pacing: sequential, 0.12s courtesy gap, unchanged 429 backoff from `src.wiki_hindi`.
- Hindi pageviews served from the committed `data/raw/wiki_hindi_cache`; other languages fetched into `data/raw/wiki_indic_cache/<lang>` (not committed with this analysis).

