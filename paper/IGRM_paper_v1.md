# Measuring Geopolitical Salience: A Daily, Channel-Decomposed Press Index for India (IGRM)

**Ishan Krishna**
Independent researcher · igrm.in

*Draft v1, assembled 2026-08-06. Every number below is read from the
published payloads named beside it and is reproducible from the public
repository. Sections marked **[VOICE]** are the author's to write; the
apparatus is complete.*

---

## Abstract

**[VOICE — 150–200 words.** Write this last, in your own voice. The
factual spine, all verifiable below: a daily index of press salience
for five registered channels of India-relevant geopolitics,
2017-06-29 to present (3,304 days); construction registered before
use; 24 of 29 pre-registered episodes detected; independent
co-movement with the Caldara–Iacoviello GPR-India index at r = 0.484
in monthly levels over 110 shared months despite no shared pipeline
or dictionary; a 1979–2016 historical proxy on a different construct
whose border channels replicate the live series at r ≈ 0.87 and whose
two weaker channels are refused publication by a pre-registered
threshold; full reproducibility from a clean checkout in about five
minutes. State plainly what it measures — press attention — and what
it does not: risk, probability, or any forecast.**]**

**Keywords:** geopolitical risk, media salience, text-as-data, GDELT,
India, pre-registration, reproducibility

---

## 1. Introduction

**[VOICE — 600–900 words.** Your argument, not mine. The pieces worth
using, each defensible:

- The measurement gap: existing geopolitical-risk indices are monthly,
  built on a fixed newspaper panel, and treat a country as one number.
  Decision-relevant questions in India are channel-specific — the
  Pakistan border, the China border, Gulf energy, US trade policy, and
  shipping chokepoints do not move together and should not be summed
  into a single national mood.
- The credibility gap: an index whose dictionary can be edited after
  its results are seen is unfalsifiable. This paper's contribution is
  as much *procedural* as substantive — registration before use,
  append-only amendment, published misses, and a public reliability
  record.
- The contribution list: (i) a daily, channel-decomposed salience
  index for India; (ii) a pre-registered validation protocol with the
  hit-rate computed only after the episode list was frozen; (iii)
  independent-corpus and independent-index validation; (iv) a
  registered historical proxy back to 1979 that publishes its own
  failures; (v) complete reproducibility, including the raw store.
- The honest frame: this measures how loudly the world's press
  discusses India-relevant geopolitics, and nothing more.**]**

---

## 2. Data

**Substrate.** GDELT's global news monitoring: the DOC 2.0 API for
daily matched-article shares and the Web NGrams v5 corpus for
construction-identical article enumeration. Coverage is
English-language, worldwide, 2017-06-29 onward (3,304 daily
observations as of 2026-08-05).

**Corpus non-stationarity — measured, not assumed.** The monitored
corpus has contracted materially over the sample
(`docs/data/validation.json`, `drift`):

| Year | Mean daily monitored articles |
|---|---|
| 2022 | 282,419 |
| 2023 | 187,046 |
| 2024 | 163,328 |
| 2025 | 160,975 |
| 2026 | 144,069 |

This is precisely why the index is a **share** of the monitored
corpus rather than a count. The construction's adequacy is testable:
the correlation between each channel's share and the corpus size is
small and mostly negative (pakistan_west −0.064, china_east 0.017,
gulf_energy −0.200, us_trade 0.012, shipping −0.244), i.e. the series
are not mechanical reflections of GDELT's own growth or decline.

**Context sources, never inputs.** UCDP GED conflict events, IMF
PortWatch chokepoint transits, JODI official crude-import statistics,
Correlates of War MID 5.0 dispute records, and Wikipedia pageviews
enter the site as context or cross-checks and enter no score.

---

## 3. Construction

**Channels.** Five registered channels, each a phrase dictionary with
an optional in-document India anchor: `pakistan_west`, `china_east`,
`gulf_energy`, `us_trade`, `shipping` (`dictionaries.json`, frozen
2026-07-24 with dated append-only amendments).

**Daily share.** For channel *c* on day *t*, the share is matched
articles over total monitored articles. Where a channel needs two
sub-queries for API length limits, the sum of shares is used, a
slight upper bound on the union, disclosed.

**Transform.** Each channel's raw share is ranked against its own
trailing 730 days: a percentile in [0, 100], requiring 180 trailing
observations before a score is emitted. Percentile rather than
z-score because news volume is fat-tailed and drifts secularly.

**Headline (registered 2026-08-06, methodology v1.8.0).** The
published headline is the **trailing 7-day mean share** passed
through the identical percentile transform. The motivation is a
measured property of the rank transform: because the distribution is
dense near its centre, ordinary news-cycle oscillation produces large
rank movements. On 2026-08-03–05 the china_east raw shares were
0.0134%, 0.0232% and 0.0070% (two-year median 0.0165%), which the
daily transform rendered as 33.5 → 74.3 → 4.5. Seven days is the
minimal window that cancels the weekly periodicity of global press
volume. Responsiveness is preserved and was verified before adoption:
following the 2025-04-22 Pahalgam attack the 7-day pakistan_west
score read 99.5 the next day and pinned at 100 for the following
week. The daily series remains published in full as the underlying
tape; episode detection, sampling bands, receipts and alerts all
continue to operate on daily values.

**Composite.** Unweighted mean of the five channel percentiles — a
transparency convention, not a claim about relative importance;
alternative weightings are published in `docs/data/alt_specs.json`.

**Episodes.** Detected on raw shares, not percentiles: a spike day is
a value above the trailing 90-day mean plus 2σ with the baseline
lagged one day (a spike cannot inflate its own threshold); spike days
within three days cluster into one episode.

**Sampling uncertainty.** Days estimated from the ngrams sample carry
Wilson 95% intervals on the matched share, passed through the
identical splice ratio and percentile transform, and published in
`docs/data/uncertainty.json`. Moves whose intervals overlap the prior
day's are reported as not distinguishable from sampling noise.

---

## 4. Validation

All validation quantities were computed **after** their respective
registrations were frozen. The sequence is the evidence.

### 4.1 Pre-registered episode detection

Twenty-one episodes were frozen before the first validation run;
eight more (tranche 2) were drafted blind from external chronology
with ex-ante criteria and recorded exclusions, signed 2026-08-06, and
graded only afterwards.

| | Episodes | Detected | Rate |
|---|---|---|---|
| Tranche 1 (frozen 2026-07-24) | 21 | 18 | 86% |
| Tranche 2 (signed 2026-08-06) | 8 | 6 | 75% |
| **Combined** | **29** | **24** | **83%** |

Per channel (detected / n): pakistan_west 6/7, china_east 3/4,
gulf_energy 8/11, us_trade 4/4, shipping 3/3. Misses are enumerated
in `docs/data/validation.json` and never removed.

### 4.2 Independent-index validation (Caldara–Iacoviello GPR)

The GPR country index for India (GPRC_IND) is monthly, built from a
fixed newspaper panel with a different dictionary and no shared
pipeline with this index. Over 110 shared months:

| Series | r (levels) | r (monthly changes) |
|---|---|---|
| **Composite** | **0.484** | **0.232** |
| us_trade | 0.315 | 0.276 |
| gulf_energy | 0.304 | 0.060 |
| shipping | 0.272 | 0.098 |
| pakistan_west | 0.229 | 0.117 |
| china_east | −0.085 | −0.020 |

The composite's co-movement with an independently constructed index
is external validation of the construct. The china_east near-zero is
a construct difference, analysed rather than hidden: GPR keys on war
and threat vocabulary, while this channel deliberately captures
diplomatic and border-management coverage, which dominates its
distribution in ordinary months.

### 4.3 Historical proxy, 1979–2016, and its registered refusals

A separate historical study (registration frozen before first query;
`analysis/back_extension_memo.md`) reconstructs a *different*
construct — monthly shares of global event-mentions under frozen
actor-pair filters from GDELT's coded event archive — and is never
spliced into the live series.

Nine anchor episodes were registered before computation; six graded
in their channel's top decile of the trailing decade: Kargil 1999
(100.0), Brasstacks 1987 (99.0), Pokhran-II 1998 (96.6; US leg 99.2),
the 2001 Parliament attack (96.6), Doklam 2017 (92.9). The three
misses are informative rather than embarrassing: Operation Blue Star
1984 (52.3) is a domestic episode that a bilateral actor-pair filter
should not detect — evidence the filter is genuinely bilateral;
Mumbai 26/11 2008 (89.1) falls just short because non-state
perpetrators thin state-actor coding; Sumdorong Chu 1986 (54.8) sits
in a thin wire-service era.

The overlap audit applied a **pre-registered publication threshold**
(r ≥ 0.4) over 36 shared months:

| Channel | r | Verdict |
|---|---|---|
| pakistan_west | 0.893 | publishes (tracks) |
| china_east | 0.848 | publishes (tracks) |
| us_trade | 0.216 | **does not publish** |
| gulf_energy | 0.153 | **does not publish** |

The border channels replicate across two entirely different
constructions. The two channels the registration had already flagged
as weaker fail their own threshold and are withheld — the refusal is
the finding.

### 4.4 Dictionary robustness

Broader and narrower dictionary variants (frozen in
`dictionaries_alt.json`) are recomputed and correlated with the
primary series (2022 onward):

| Channel | narrow | broad |
|---|---|---|
| pakistan_west | 0.878 | 0.918 |
| china_east | 0.895 | 0.959 |
| gulf_energy | **0.527** | 0.779 |
| us_trade | 0.663 | 0.843 |
| shipping | 0.861 | 0.727 |
| composite | 0.796 | 0.880 |

The gulf_energy narrow correlation of 0.527 is low and is discussed
prominently on the validation page rather than buried: that channel's
level is term-dependent, and its rank movements should be trusted
more than its level.

### 4.5 Placebo and cross-source

Placebo channels (constructed on India-irrelevant vocabulary) produce
115 detected episodes, of which 52 overlap geopolitical episode days
(overlap fraction 0.452) — a base rate the reader should hold against
the hit-rate above. Wikipedia pageview series, a demand-side proxy,
correlate weakly with the supply-side index per channel (−0.02 to
0.188); this divergence is published as a finding, not resolved by
adjustment.

### 4.6 Measured sector sensitivities: a published null

Signed sector-to-channel mappings (sectors.json v1.1.0) were used to
compute NSE sectoral index returns relative to Nifty around episode
starts, 1/5/20 trading days, with seeded bootstrap intervals and
Benjamini–Hochberg FDR control at 10% across the full grid. **Of 39
cells, none survived correction.** With this episode set, no sector
index shows a sensitivity distinguishable from zero once the search
is paid for. That null is published in the payload and on the site.

---

## 5. Reproducibility and evidence

**Reproduction.** `scripts/reproduce.sh --use-cache` clones the
repository, refuses all data acquisition (network *and* cache),
rebuilds every published payload from the committed raw store, and
diffs against the published versions — about five minutes, no
credentials. Market-dependent outputs compare within a documented
±0.06 band because their Yahoo Finance inputs cannot be
redistributed; everything with committed inputs matches to 1e-6.

**Article-level evidence.** Each published day enumerates the matched
articles from the same corpus the score was computed from — on
2026-08-05, 119,349 documents were scanned and every matched article
is listed with its lane (counted by the estimator, present in the
day's wider corpus, or retrieved by relevance search).

**Operational transparency.** A public status page reports each
source's data age against stated freshness windows, and the morning
publication contract is scored from git commit timestamps rather than
self-report, with misses listed permanently.

---

## 6. Limitations

Stated as constraints, not caveats.

1. **Salience is not risk.** The index measures press attention. A
   quiet channel is not a safe one, and an anniversary can be as loud
   as an escalation.
2. **Anglophone lens, measured.** The substrate is English-language
   coverage, and a cross-language test shows this is a real constraint
   rather than a formal one. Reading the same registered article set on
   Hindi Wikipedia (titles resolved through Wikipedia's interlanguage
   links, never hand-picked) over 3,394 overlapping days, English
   Wikipedia tracks the index more closely than Hindi does **on five
   channels of five, in both levels and day-to-day changes, with no
   channel where Hindi leads**. Changes correlations fall from
   0.223/0.340/0.589/0.117/0.564 (English) to
   0.160/0.132/0.163/0.050/0.030 (Hindi); `us_trade` gives the study's
   only negative level correlation, −0.136. Attenuation from thin Hindi
   traffic does not explain the pattern: `us_trade` has the highest
   median Hindi traffic and the worst agreement, `gulf_energy` the
   lowest and the strongest. Six of 29 registered articles have no
   Hindi counterpart at all, and they are the foreign-policy-apparatus
   topics (sanctions regimes, maritime security), while the two
   India-adjacent channels resolve completely. The index measures
   English-language attention to India better than it measures
   Indian-language attention, and should be cited accordingly
   (`docs/data/wiki_hindi.json`).
3. **Single-coder judgment.** Every construct decision traces to one
   author. Registration and append-only amendment constrain
   *post-hoc* revision but cannot substitute for independent coders;
   inter-coder reliability is not available and its absence is stated
   here rather than obscured. Test–retest machinery is in place; the
   author's calibration labels currently stand at 16 of a registered
   threshold of 100 and the series is flagged UNCALIBRATED until met
   (machine-author agreement on the current overlap: 0.875, n = 16).
4. **Syndication, measured.** Share-of-coverage counts articles, so a
   wire story carried by two hundred outlets moves a channel as far as
   two hundred newsrooms reacting independently. The multiplier
   (articles per distinct normalized headline, over the day's full
   scanned corpus) is now published daily: on 2026-08-05, over a
   119,349-document scan, `pakistan_west` ran 160 articles across 46
   distinct stories, ×3.478 — roughly 71% of that channel's article
   count was republication, in the channel that carries the
   Pahalgam–Sindoor crisis. No de-duplication is applied and none is
   proposed: republication is a real editorial decision, not noise, and
   any deflation would be a second unregistered construct. The
   estimator is biased downward at small samples (the same channel-day
   reads 1.923 at 28,575 documents and 3.478 at 119,349), so only
   full-depth scans enter the published history
   (`docs/data/syndication.json`).
5. **The detector goes blind after it fires.** Episode detection uses a
   trailing 90-day mean + 2σ, so a crisis enters the window its own
   future threshold is computed from. The bar rises for ninety days and
   peaks *after* the episode ends in 521 of 523 detected episodes. For
   `pakistan_west` through Pahalgam and Sindoor the threshold went from
   0.0244 (2025-04-21) to 0.6912 (2025-07-20), a 28-fold increase; on
   2025-05-20 a share of 0.1340 — five and a half times the pre-crisis
   bar — did not register. Across the series, 2,158 distinct
   channel-days (12.4%) carry coverage the pre-episode threshold would
   have flagged and the live one did not. The registered rule is
   unchanged because every alternative is worse (excluding spike days
   presumes what a spike is; a fixed threshold abandons cross-channel
   comparability; a longer window delays first detection), but the cost
   is measured rather than inferred (`docs/data/detector_blindness.json`).
6. **The series is not one instrument.** Most days are GDELT DOC API
   counts; a minority were measured by the Web NGrams bridge and
   divided by an estimated per-channel splice ratio to reach the API's
   scale (38 of 3,484 days as of 2026-08-07). Any statistic crossing
   that boundary inherits the linking constant's uncertainty. The
   instrument label ships as a column in the published shares, and
   monthly aggregates flag months that span the seam.
5. **Sampling noise on thin channels.** Days estimated from samples
   carry wide intervals when a channel is quiet; the bands are
   published for exactly this reason.
6. **Association, not causation** anywhere market or event data
   appear beside the index.
7. **No forecasts.** A pre-registered forecast experiment
   (`validation/forecast_registration.json`, signed 2026-08-06) runs
   on a separated research page with a frozen fork criterion; until
   it resolves, the presumption stated on that page is that salience
   does not forecast.

---

## 7. Conclusion

**[VOICE — 300–400 words.** What you think this is for, and what you
want done with it. Suggested spine: the instrument is available, the
data is open (CC BY 4.0), the code is MIT, and the standing invitation
is adversarial — the site publishes what would falsify it and promises
to publish submissions unedited. If you want one closing idea: the
contribution that outlasts any particular number is the
demonstration that a public measurement instrument can be built so
that its own failures are visible by construction.**]**

---

## Data and code availability

Data CC BY 4.0, code MIT. Live payloads and frozen API contract at
igrm.in; complete source, raw stores and replication procedure at
github.com/PlausibleDissent9/india-geopolitical-risk-monitor
(`REPLICATION.md`). DOI: **[to be minted — Zenodo]**.

## References

**[Apparatus note: the citation list is short and specific — Caldara
& Iacoviello (2022) for GPR; Baker, Bloom & Davis (2016) for EPU as
the methodological ancestor; Leetaru & Schrodt (2013) for GDELT;
Palmer et al. (2022) for MID 5.0; Sundberg & Melander (2013) for
UCDP GED. Add anything your reading suggests; I will format to the
target venue's style once you choose it.]**
