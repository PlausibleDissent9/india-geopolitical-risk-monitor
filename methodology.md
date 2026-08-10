# IGRM Methodology

Version 1.11.0 · five channels frozen 2026-07-24, V2 layers added 2026-07-31, comparators and predictability 2026-08-01, receipts drill-down 2026-08-02, API contract frozen 2026-08-04, corpus receipts and sampling bands 2026-08-06, 7-day headline 2026-08-06, raw shares and the independent splice audit published 2026-08-07, construct naming locked and AI-GPR benchmark published 2026-08-07 · [changelog](#changelog) at the end.

## 1. What the index measures (and what it does not)

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

## 2. Term selection and the ex-ante rule

Each channel's dictionary draws from four categories, geography where
tension physically manifests, institutions and standing mechanisms,
recurring doctrine/press vocabulary, and structural chokepoints. Geography
alone under-detects diplomatic coverage; doctrine vocabulary typically
carries the most recall. Every term carries a one-line rationale inside
`dictionaries.json` itself; that file, not this page, is the term-level
record. Channels hold 10-14 terms: below ~8 the series is thin and noisy,
above ~15 marginal terms import contamination faster than signal.

**The ex-ante rule.** No term may be a retrospective event name (Galwan,
Pulwama, Balakot, Sindoor, Kargil, Uri, 26/11, Doklam, …). The reason is
circularity: an index whose queries contain event names *by construction*
spikes at those events, and its "validation" against them would be
meaningless. Spikes must be *detected* by structural vocabulary that existed
before, and will exist after, any particular event. The rule is enforced in
CI by `tests/test_dictionaries.py`, which fails the build on a banned name.
One borderline call is documented: *"surgical strikes"* entered common
Indian-press usage after 2016 but is doctrine vocabulary reused across
subsequent escalations, not the name of an event; it is admitted on that
basis.

**Query grammar.** GDELT's DOC API permits OR only inside a single
un-nested parenthetical that may not mix AND. Every term is therefore one
quoted phrase, and disambiguation is done by a single channel-level anchor
word, e.g. `India ("Line of Control" OR "ceasefire violations" OR …)`.
Quoted phrases match exact token sequences (hyphens tokenize to spaces; no
stemming, hence singular and plural forms where both are common in copy).
Two generic phrases are accepted with open eyes and disclosed here:
`"energy security"` (broader than its channel; kept for recall of policy
coverage) and `"Suez Canal"` (includes routine transit coverage; the
percentile normalization absorbs its baseline).

**Cross-channel bleed, decided and documented:** `"Russian oil"` (India)
sits in *US & Trade Policy*, not *Gulf & Energy*, the risk vector is
sanctions policy, not physical supply. Red Sea tanker coverage belongs to
*Shipping*; Persian Gulf tanker incidents to *Gulf & Energy*. No term
appears in two channels, so the composite never double-counts an article
across the declared boundaries.

**Excluded by choice: leadership rhetoric.** Statements by military
and political leadership are not construct vocabulary: adding them
would make rhetoric frequency part of the measure, and prolific
official communication would move a channel even when its underlying
geography is quiet. Such stories count only when they co-occur with
structural vocabulary; pure rhetoric does not count, and that is a
disclosed design decision (2026-08-04), not an oversight.

**Freeze.** Dictionaries froze 2026-07-24 (`_meta.frozen_on`). Any later
change appears in the [changelog](#changelog) with a date and a reason. An
index whose definition moves silently is not reproducible.

## 3. Normalization

Each channel's raw series is GDELT's `timelinevol` measure: matching
articles as a **share** of all monitored articles that day, which already
nets out GDELT's secular corpus growth. Where a channel's term set
exceeds the API's query-length limit (measured ~250 characters), the
channel series is the sum of two sub-query shares; an article matching
both sub-queries counts twice, making the series a slight upper bound on
the union share. The partition is fixed and versioned with the
dictionaries. From July 2026, during a DOC-API disruption, the recent
tail is computed from GDELT's raw Web NGrams files at the maintainer's
direction, the same share construct from half-hourly samples of the raw
feed, and ratio-spliced to the API series on overlap days, with each
channel's splice ratio and its dispersion published alongside the data
(see changelog).

### 3.1 Independent audit of the splice calibration

The production ratios remain frozen, but they are not described as
validated. A proposed 38-day stability check was rejected before
publication because it was circular: on 37 of the 38 cached days, the
store value used as the denominator had itself been produced by dividing
the cached NGrams value by the production ratio. Re-estimating from that
pair mechanically recovers the old constant.

The table below uses a genuinely independent denominator instead: the
last pre-bridge DOC-API store preserved in git commit `091c25e`, paired
with the retained NGrams day caches. The recovered window is 2026-06-30
to 2026-07-21. It supplies 18 independent days for the first three
channels, but only the original single day for US Trade and Shipping.

| Channel | Frozen ratio (original n) | Independent audit ratio (n) | Change | Audit log-SD |
|---|---:|---:|---:|---:|
| Pakistan / Western Border | 1.9547 (5) | 2.4634 (18) | +26.0% | 0.3296 |
| China / Eastern Border | 3.3612 (5) | 2.6998 (18) | -19.7% | 0.3954 |
| Gulf & Energy | 1.7910 (5) | 1.8098 (18) | +1.0% | 0.0976 |
| US & Trade | 2.5616 (1) | not independently re-estimable (1) | not estimated | 0.0000 |
| Shipping & Chokepoints | 2.9747 (1) | not independently re-estimable (1) | not estimated | 0.0000 |

Bridge shares equal the NGrams share divided by the ratio. Relative to the
independent audit, the frozen Pakistan ratio is smaller, so primary
post-bridge Pakistan shares are higher; the frozen China ratio is larger,
so primary post-bridge China shares are lower. Under the audited alternative,
the latest Pakistan score therefore moves down 8.0 points and China moves up
5.1. That is the direction of this sensitivity, not a claim that either
independent ratio is known without uncertainty.

This is a sensitivity finding, not a replacement calibration. It shows
material uncertainty in the Pakistan and China links and leaves the two
one-day links untested. Production values and published history remain
unchanged to preserve the v1 vintage. The score-level effect is material,
so it is published rather than summarized away:

| Series | Channel | Median absolute shift | Maximum absolute shift | Shift on 2026-08-06 |
|---|---|---:|---:|---:|
| Daily | Pakistan / Western Border | 6.6 | 10.9 | -8.0 |
| Daily | China / Eastern Border | 13.0 | 18.7 | +5.1 |
| Daily | Gulf & Energy | 0.0 | 0.4 | 0.0 |
| Daily | Composite | 1.3 | 3.0 | -0.6 |
| Trailing 7-day | Pakistan / Western Border | 9.4 | 11.4 | -4.5 |
| Trailing 7-day | China / Eastern Border | 21.7 | 25.6 | +23.5 |
| Trailing 7-day | Gulf & Energy | 0.0 | 0.4 | 0.0 |
| Trailing 7-day | Composite | 2.6 | 4.1 | +3.8 |

The table is the fixed 37-day study window from 2026-07-01 to 2026-08-06.
The machine-readable artifact was extended through 2026-08-09 (40 days)
before the retained-identity rights boundary was hardened, and is now frozen
at `docs/data/splice_sensitivity.json`. It will not be recomputed unless a
current signed source decision permits that evidence use. Neither artifact is
a corrected history or may be substituted silently for the primary.

The published sampling-band artifact is likewise a fixed historical window:
`docs/data/uncertainty.json` covers 2026-06-30 through 2026-08-07. It remains
available for those dated scores but does not claim coverage of later days and
will not be recomputed from retained identity-bearing caches without a current
signed decision covering the complete study window.

A future measurement version may
adopt new ratios only after at least 14 independently observed overlap
days exist for every channel, the score-level impact is published, and
the old vintage remains downloadable. Code and the recovered API snapshot
are in `analysis/splice_overlap_audit.py` and
`analysis/splice_overlap_api_091c25e.csv`.

The published score is the
percentile rank of today's share within the channel's trailing 730 days
(inclusive of today; the window never contains future data). Days with
no observed value stay missing rather than scoring zero.

*Why percentile rather than z-score:* news-volume shares are fat-tailed and
drift with editorial fashion. A z-score inherits both problems, single
extreme days distort the mean and variance for months. The percentile is
robust to outliers, invariant to monotone changes in the level of coverage,
and yields a directly interpretable sentence ("higher than X% of the last
two years"). Its cost is **saturation**, and the cost is large enough to
state with a number rather than a phrase: between 2025-04-23 and
2025-05-14 the `pakistan_west` percentile moved 2.2 points (97.8-100.0)
while the underlying share moved 5.5-fold (0.214% to 1.173%). During a
sustained crisis the percentile therefore carries almost no intensity
information — it cannot distinguish the peak day from the twentieth day —
and the share carries all of it. Two consequences follow and are honoured
elsewhere in this document: episode detection runs on raw shares, not
scores (§5), and **the raw shares are published as a first-class artifact**
(`docs/data/shares.csv`) so any reader can apply a non-saturating
transform of their own.

*Why 730 days:* long enough to span more than one editorial cycle and both
halves of a typical escalation-and-decay arc; short enough that "the last
two years" remains a claim about the current coverage regime rather than a
different era of the corpus. §8's stability check (365- and 1095-day
recomputations) tests that nothing below hangs on this choice.

*Minimum observations:* no score is emitted until a channel has 180 trailing
observations; early-window days are null rather than percentiles against a
thin baseline.

## 4. The composite convention

The headline composite is the unweighted mean of the five channel
percentiles. This is a **transparency convention, not a claim** that the
five channels matter equally to India, no defensible weighting exists
(trade-weighted? casualty-weighted? by what?), and any chosen weighting
would smuggle in an editorial judgment the data cannot support. The
components are the primary product; the composite exists so the site has
one number to anchor the day. Readers who dislike the convention can
recompute any weighting from the published per-channel series in
`docs/data/history.json`.

## 5. Spikes and episodes

A **spike day** for a channel is a day whose *raw volume share* exceeds the
trailing 90-day mean plus two standard deviations, with the baseline lagged
one day so that a spike cannot inflate the threshold that must catch it.
Detection runs on raw shares, not percentile scores, because a bounded
series compresses at 100 and can make a 2σ exceedance arithmetically
unreachable exactly when coverage is most extreme.

Spike days separated by three or fewer calendar days cluster into one
**episode** (start, end, peak). Episodes rather than raw spike days are the
unit of analysis because multi-day coverage waves are one event
journalistically, and treating each day as independent would let long
episodes dominate every downstream average. The 2σ/90-day/3-day parameters
are conventions; §8 reports a 1.5σ secondary specification so readers can
see the findings are not threshold-dependent.

## 6. Event-study design

The event study reports **India-specific relative returns** around episode
starts, never outright returns:

- **Nifty 50 − MSCI EM**, strips global equity beta; what remains is the
  India-specific equity move.
- **Defence basket − Nifty**, the sharpest India-specific hypothesis: if
  border salience means anything to markets, it should appear in defence
  names relative to the broad index. (Basket: HAL, BEL, BDL, Mazagon Dock,
  Cochin Shipyard; equal-weight, daily-rebalanced.)
- **Energy OMC, IT services and ports/logistics baskets − Nifty**, the
  three registered sector-transmission hypotheses, each using its frozen
  equal-weight basket.
- **USDINR − DXY**, strips broad dollar moves from the rupee.

Brent and gold are configured **descriptive-only** outcomes: no India-specific
component of a globally-priced commodity is separable, so they carry no
interpretation beyond context. A configured outcome appears only when its
current source cache contains observations; the JSON explicitly lists
available and unavailable outcomes. Windows are 1, 5, and 20 **trading** days,
inclusive of the first trading day on or after the episode start. Every
estimate carries a bootstrapped 95% interval (1,000 resamples over
episodes). The language rule is absolute: episode starts are *associated
with* subsequent relative returns. Coverage and prices respond to the same
underlying events; nothing in this design can separate the two, so
"caused" and "predicts" never appear (§7).

## 7. Known limitations

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

## 8. Validation

Where credibility lives. Four checks, all runnable from the repo.

**8a. Pre-registered historical detection** (`python -m src.validate
hit-rate`). Twenty-one episodes across the five channels, 2017-2025, were
frozen in `validation/validation_episodes.json` before the first
validation run (thirteen at the 2026-07-24 freeze; eight pre-2022
episodes appended, dated, under the file's append-only rule when the
backfill extended to 2017, still before any validation ran). None of
their names appears in any query term, that is the ex-ante rule doing
its work. A hit is a detected episode in the same channel within ±3
days. The per-channel hit table is published to `docs/data/validation.json`
and is this project's key figure: **18 of 21 detected (86%)** on first
run. A second tranche of 8 episodes (2018–2022, concentrated in the
thin channels) was drafted blind from external chronology, registered
with ex-ante criteria and recorded exclusions
(`validation/validation_episodes_tranche2_SIGNED.json`), founder-signed
on 2026-08-06, and graded only after that signature: **6 of 8
detected**, bringing the combined record to **24 of 29 (83%)**. The
two tranche-2 misses (the 2022 BrahMos accidental launch, the 2022
OPEC+ production cut) are listed in the payload like every miss —
the sequence draft-blind, sign, then grade is the figure's warrant.

**83% is not the number to be impressed by, and this section will not
present it alone.** The same payload
(`docs/data/detection_baselines.json`) publishes what 24 of 29 should be
read against: **6.8** hits expected by chance, **19 of 29** under the
stricter start-based timing rule, and **26 of 29** for a naive detector
that asks only whether *any* channel moved, ignoring which one. The
naive rule beats the registered one by two events. So detection alone is
cheap, and the honest reading of this section is not "the index detects
events" — it is that the index detects them *in the right channel*, which
is the only part a naive rule cannot do. Anywhere the 24 of 29 figure is
quoted without those baselines, the quote is flattering the index.

**8b. Dictionary robustness** (`python -m src.validate robustness`).
Broader and narrower constructions of every channel are frozen in
`dictionaries_alt.json`. The full index is recomputed under each and
correlated with the primary. Correlations above 0.9 mean "why these terms?"
has no purchase; anything lower is reported as term-dependence, prominently.
The robustness and placebo fetch windows cover 2022 onward (request
budget), narrower than the 2017 primary series; each published table
states the window it covers.

**8c. Placebo channels** (`python -m src.validate placebo`). Two channels
with no India-geopolitics content (IPL cricket, Bollywood) run through the
identical pipeline. They must not spike around geopolitical episodes; their
overlap fraction is published. One disclosed imperfection: Indian sport is
not perfectly insulated from geopolitics (India-Pakistan fixtures), so the
cricket terms avoid Pakistan-linked phrasing.

**8d. Normalization-window stability.** The index recomputed at 365- and
1095-day windows must be qualitatively unchanged (rank correlation with the
primary reported alongside 8b's table). Episode detection is additionally
reported at 1.5σ beside the primary 2σ.

A note on what validation cannot do: passing 8a-8d shows the instrument
detects what it claims to detect and is not an artifact of one term list.
It does not, and cannot, convert salience into risk (§7.1).

## 9. The India Stress Gauge

**Experimental secondary object; not a validated headline measure.** As of
7 August 2026 the registered detection rule succeeds on 2 of 29 episodes.
That negative result is published rather than tuned away. Each release also
lists the latest available and missing components and the effective weights
after any registered renormalization.

The gauge fuses four sources into one daily 0-100 line: the composite
press-salience percentile, a conflict-event intensity percentile from
the GDELT Events stream ((verbal + material conflict events) / global
events), a market-stress percentile (the mean of the India VIX level
percentile and the USDINR 10-day realized-volatility percentile), and
a Wikipedia attention percentile. Each component is ranked against its
own trailing 730 days with the same 180-observation minimum as the
index; the gauge is their weighted mean.

**These weights belong to the stress gauge, not to the index.** §4
refuses any weighting of the five press channels because none is
defensible; the gauge is a different registered object combining four
*distinct measurement modalities*, where the components are not
interchangeable and a stated weighting is unavoidable. A reader who
finds §4 and §9 contradictory has found an ambiguity in this document
rather than in the construction: the index composite is unweighted and
always has been. The gauge's weights (press 0.35, events 0.25, market
0.25, wikipedia 0.15),
the detection rule (gauge at 90 or higher within 3 days of an episode
date), and the missing-component rule (press required, at least two of
the other three present, weights renormalized) were registered in
`validation/stress_gauge_weights.json` with per-component rationale
and committed before any hit-rate was computed; the repository history
is the proof of ordering. The hit-rate against the pre-registered
episode list publishes with the gauge in
`docs/data/stress_gauge.json`, along with the per-component
percentiles behind each day's number. Whatever the hit-rate is, it is
reported as found; the gauge measures attention and stress, and
predicts nothing.

## 10. Comparator countries and predictability

Three comparator series (Pakistan, Indonesia, Vietnam) plus India run
through one deliberately simple instrument: a single shared
geopolitical-risk vocabulary of ten structural phrases, anchored per
country, registered with per-term rationale in `comparators.json`
before the first fetch. Cross-country lines are comparable by
construction because the instrument is identical; levels still reflect
Anglophone press attention, disclosed. The five-channel index remains
the primary product; the comparators exist for context and for the
cross-country questions V8 will formalize.

The predictability study (`docs/data/predictability.json`) asks the
directed lead-lag question on daily changes: five own-lags with and
without five lags of the candidate leader, R-squared increment, and a
permutation p-value from time-shifted nulls. In the published run, no
salience-leading direction clears the conventional 0.05 threshold;
events-leading-salience is the closest of the registered directions.
Exact values live in `docs/data/predictability.json` rather than this
prose so a registered rerun cannot leave a stale number here. This
negative result is consistent with the instrument's stated scope: a
salience monitor, not a risk predictor.

## 11. Receipts and source tiers

`docs/data/receipts.json` publishes a bounded latest-day evidence
display, not a census and not the complete evidence behind the 7-day
headline. The primary path reuses the sampled Web NGrams corpus and may
add separately labelled, query-matched GDELT DOC supplemental URLs. It
deduplicates URLs, then publishes one representative for each
case-folded 120-character `(title or url)` key, up to 150 representatives
per channel. If the corpus path is unavailable, the explicitly labelled
artlist-only fallback publishes at most 75. On the primary path, every
row states its lane; corpus rows distinguish the scoring sample from the
extended scan.

Each displayed domain is looked up in `source_tiers.json`. Registered
tiers affect presentation order and descriptive source-mix fields only;
unregistered domains remain unranked. The legacy
`spike_quality_tier12_share` field is the tier-1/2 share of the displayed,
tier-sorted list and must not be read as the source mix of the underlying
retrieval pool. Most importantly, **source tiers never enter a channel
score or the composite**.

## 12. API contract

`docs/data/api_contract.json` freezes, as of 2026-08-07, every endpoint
IGRM serves for machine consumption: the file's format, a plain-language
description, and its top-level "frozen fields" (JSON keys or CSV
columns) promised not to be removed, renamed, or repurposed within
major version 2. New fields may be added to any payload at any time
without notice; only a removal, rename, or type change requires a
major version bump, which would be announced in the contract's
`deprecated` list and in this changelog before it ships. The contract
versions independently of this document (which tracks construct
changes) and of the `igrm` Python package (which tracks code) --
`docs/api.html` renders it for human readers. The contract file itself
is committed and hand-frozen, not regenerated by the daily pipeline:
a promise that rewrote itself every night would not be a promise.

## 13. Historical Intelligence (the 1979-2019 archive) {#historical-intelligence}

The back-extension is a **separate instrument**, and this section exists to
keep it separate. It counts actor-pair event mentions in the GDELT Events
archive; the live index measures press salience over a matched-article
corpus. The two are never spliced, never plotted on one axis, and no
statistic computed on one is comparable to a statistic computed on the
other. Where the archive is read at all, it is read as a series in its own
right.

Three readings are registered in
`governance/historical_intelligence_contract.json` and published in
`docs/data/historical_intelligence.json` (rendered at
`docs/history-lab.html`, defined field by field in the codebook):
**regime baselines** over four calendar decades, **structural break scans**,
and **analog retrieval**. Only the two channels the source payload's
`overlap_audit` marks `tracks` are eligible; the refusals are published with
their correlations rather than dropped.

Four rules bind all three, and they are the reason this section is short
rather than a set of findings:

1. **Every statistic reports its own denominator**, and a statistic over
   fewer than the registered minimum is refused with a reason rather than
   computed over a thin window. No unavailable value is ever rendered as a
   dash, a zero, or an imputed mean; the interface prints "unavailable" and
   why.
2. **A break is a candidate break in the measured series.** It is never
   described as a historical cause, a turning point, a regime change, or an
   explanation of any event, and its stability across minimum-segment
   settings is published beside it. Where the candidate moves with the
   setting, the instability is the result.
3. **An analog is a similarity lookup, not a precedent.** It carries no
   claim that similar months share causes and no claim about what follows
   them. Features missing on either side of a pair are named and excluded,
   never filled.
4. **No present-day knowledge is backfilled.** The archive ends 2019-12, and
   any label, annotation or category whose evidence postdates that is
   refused and the refusal published. Archetypes exist only where a
   human-authored registered anchor does; nothing here is machine-labelled.

The decade labels are calendar slices, not political regimes, and the word
"regime" in `regime_baselines` should be read that way and no other. Nothing
in this section is a forecast.

## Changelog {#changelog}

- **2026-08-07, v1.11.0 (AI-GPR benchmark; Divergence Register).**
  Before computing any joint statistic, the exact Iacoviello-Tong
  country-monthly file, IGRM history vintage, event list, sample rule,
  transformations, primary statistic, block bootstrap, decision text and
  analysis-script hash were frozen in public commit `58ca6c0`. The primary
  result across 106 consecutive-month changes is Spearman rho 0.256, with a
  six-month moving-block 95% interval of [0.050, 0.407] and a twelve-month
  robustness interval of [0.082, 0.364]. Under the frozen rule, the two
  measures share a common component but are far from redundant. Two initial
  invocations failed before producing output because SciPy was absent; the
  dependency was installed and declared without changing the script or any
  registered choice. The failures are in the public run log. A new
  append-only Divergence Register publishes the five largest benchmark rank
  gaps and two salience-versus-physical-flow gaps with receipts and claim
  limits. No raw AI-GPR values are redistributed, and no superiority claim
  is made.

- **2026-08-07, v1.10.2 (construct name locked; public/private boundary).**
  IGRM retains its established name, while the paper title and construct
  line use the scientifically accurate term *geopolitical salience*. A
  dedicated comparison page identifies the exact Caldara-Iacoviello India
  series already tested and states that the newer AI-GPR products remain
  untested. An operational author queue, accidentally served as a public
  page and endpoint earlier the same day, was removed because it is not
  research data. The analytical record remains public: registrations,
  amendments, corrections, validation misses and sensitivity results.
  Removing the out-of-scope endpoint triggers API contract v2.0.0; the
  removal is recorded in the contract itself.

- **2026-08-07, v1.10.1 (independent splice audit; primary unchanged).**{: #splice-audit }
  A proposed 38-day calibration-stability result was rejected before
  publication because 37 comparison values had been constructed from
  the same numerator and production ratio. The independent replacement
  recovers the last pre-bridge DOC-API store from git, reports 18-day
  re-estimates for Pakistan, China and Gulf, refuses to claim a new
  estimate for the two n=1 channels, and publishes the full score-level
  sensitivity at `docs/data/splice_sensitivity.json`. Pakistan and China
  shifts are material; the homepage carries a notice. Production ratios
  and every primary history value remain unchanged to preserve the v1
  vintage. The rejected result and correction mechanism are recorded in
  the append-only corrections ledger.
- **2026-08-07, v1.10.0 (the construct is partly Anglophone, measured).**
  The index is built from an English-language corpus, read by an
  English-language matcher, and was cross-validated against English
  Wikipedia. Every leg of that apparatus was Anglophone, so nothing
  published could distinguish "salience of India-relevant geopolitical
  risk" from "what the international English-language press covers
  about India". `src/wiki_hindi.py` runs the test that can: the same
  registered article set read on Hindi Wikipedia, with Hindi titles
  resolved through Wikipedia's own interlanguage links rather than
  chosen by hand, correlated against the same daily shares over 3,394
  overlapping days.

  **The index tracks English-language attention more closely than
  Indian-language attention, on five channels of five, in both levels
  and day-to-day changes, with no channel where Hindi leads.** Changes
  correlations fall from 0.223/0.340/0.589/0.117/0.564 (English) to
  0.160/0.132/0.163/0.050/0.030 (Hindi) for pakistan_west, china_east,
  gulf_energy, us_trade and shipping respectively; `us_trade` is the
  only negative level correlation in the study at −0.136.

  The obvious objection is that Hindi Wikipedia simply carries less
  traffic, so the correlation attenuates through noise. That does not
  survive the data: `us_trade` has the *highest* median Hindi traffic
  of any channel (602 views/day) and the worst agreement, while
  `gulf_energy` has the lowest (161) and the strongest. The ordering of
  traffic and the ordering of agreement do not match.

  Six of the twenty-nine registered articles have no Hindi counterpart
  at all — CAATSA, Sanctions against Iran, Houthi movement, Piracy off
  the coast of Somalia, Trade policy of the United States, Energy
  policy of India — and their absence is reported as a result rather
  than a coverage caveat: they are the foreign-policy-apparatus topics,
  and the two India-adjacent channels (`pakistan_west` 6/6,
  `china_east` 5/5) resolve completely while the other three lose a
  third of their articles each.

  This changes no score, weight or published value. It is a limitation
  of the instrument, and anyone citing this index as a measure of
  *Indian public* salience should read `docs/data/wiki_hindi.json`
  first. Section 8c's supply-side/demand-side caveat stands; this is a
  sharper and less flattering version of it.

- **2026-08-07, v1.9.0 (the quantity publishes; referee findings).**
  Raw channel shares — the input the percentile series is computed
  from — are promoted to a first-class published artifact
  (`docs/data/shares.csv`, `shares.json`), with the store's 21 known
  missing days disclosed in the payload rather than left for a user to
  discover. This answers three findings at once, all now stated as
  limitations rather than implied: **(a) ceiling saturation** — across
  2025-04-23 to 2025-05-14 the pakistan_west percentile moved 2.2
  points (97.8–100.0) while the underlying share moved 5.5-fold
  (0.214%→1.173%), so during a sustained crisis the percentile carries
  almost no intensity information and the share carries all of it;
  **(b) cross-channel incommensurability** — percentiles are
  within-channel ranks against different reference distributions, so
  averaging them into a composite has no clean interpretation, whereas
  shares are fractions of one common daily corpus; **(c)
  cross-time incomparability** — a score of 90 in 2019 and in 2026 are
  ranks against different two-year baselines, while a share means the
  same thing in every year. The percentile series is unchanged and
  remains the headline because it answers "loud for this channel?",
  which a bare share cannot; publishing the quantity beside it lets any
  reader apply their own normalization and recompute the index from
  scratch. No published value changed in this entry.
- **2026-08-06, v1.8.0 (the headline becomes the 7-day; founder-signed
  in chat the same day).** The front page now leads with
  `composite7`/`score7`: the trailing-7-day mean of each channel's raw
  share passed through the **identical** percentile transform. Reasons,
  in order: (1) a rank transform amplifies the dense middle of the
  distribution, so ordinary news-cycle oscillation printed as 40–70
  point daily swings on thin channels (china_east 33.5 → 74.3 → 4.5
  across three days whose raw shares were 0.0134% → 0.0232% → 0.0070%
  against a two-year median of 0.0165%); (2) seven days is the minimal
  window that cancels global press volume's weekly periodicity; (3) the
  construction was verified on real onsets before signing — the 7-day
  read **99.5 the morning after the Pahalgam attack** and 96–98 through
  Article 370, so nothing urgent is lost. The daily series is unchanged
  and fully published as the tape (chart underlay, episodes, receipts,
  and alerts remain daily; the separately bounded historical sampling-band
  artifact has the frozen window disclosed above); `composite`/`score`
  keep their frozen contract meaning forever, and the weekly fields are
  additive. No historical value of any series changed.
- **2026-08-06, v1.7.0 (tone as a second axis; G-track layer 1).**
  Each channel's matched articles — the same articles the registered
  dictionaries selected and the receipts pages enumerate — are
  annotated with GDELT GKG's V2Tone by URL join, and the per-channel
  daily mean publishes as `docs/data/tone.json` with the join rate
  disclosed (GKG does not carry every URL). Tone introduces **no new
  article selection**: the registered dictionaries remain the only
  selector, and tone is an annotation, never a filter. **Context axis
  only: tone enters no score, no percentile, and no composite**, and
  may never do so without a founder-signed memo recorded here. No
  score construction changed anywhere in this entry; series values
  are bit-identical.
- **2026-08-06, v1.6.0 (corpus receipts and sampling bands; founder MI
  work order of 2026-08-05).** Receipts construction changed: the
  primary lane now enumerates matched articles from the same sampled
  ngrams corpus the day's scores are computed from (matcher, anchor,
  and tokenizer identical to the series -- an article in this lane is
  one the estimator actually counted), with a bounded artlist
  supplement restoring wire originals whose syndicated copies the
  sample caught; every article is lane-labeled and the artlist-only
  path remains as fallback (`src/receipts_ngrams.py`, gated by
  `tests/test_receipts_ngrams.py`). Sampling uncertainty published and
  displayed: Wilson 95% intervals on each sample-estimated day's
  matched share, passed through the identical splice ratio and
  trailing-percentile transform as the point value, shaded on the
  composite chart and disclosed in the at-a-glance strip when a
  headline move sits inside two days' bands
  (`docs/data/uncertainty.json`, `src/uncertainty.py`, gated by
  `tests/test_uncertainty.py`). Robustness made legible: ex-ante
  reading conventions on the validation page, per-channel plain
  readings, a public discussion of the gulf_energy narrow correlation
  (0.527), and weekly primary-vs-variant overlay series
  (`docs/data/robustness_series.json`). The founder's first 16 firm
  calibration rulings now count toward the registered n=100 threshold
  (author-machine agreement 0.875 on the overlap; series remains
  flagged UNCALIBRATED). No score construction changed anywhere in
  this entry: series values are bit-identical; receipts, uncertainty,
  and validation displays are evidence layers.
- **2026-08-04, v1.5.0 (API contract).** Section 12 added: the v1.0.0
  API contract (`docs/data/api_contract.json`, `docs/api.html`) freezes
  27 endpoints across `docs/data/*.json`, three CSVs, and `feed.xml`,
  with a stated promise and deprecation policy. Nothing deprecated yet.
  Gated by `tests/test_api_contract.py` (every served payload appears
  in the contract; every frozen field is still present in the live
  payload).
- **2026-08-02, v1.4.0 (receipts drill-down).** Section 11 added:
  clicking any channel score on the homepage opens `receipts.html`,
  showing the exact query and a tier-sorted sample of matched articles
  for the latest day (`docs/data/receipts.json`, gated by
  `tests/test_receipts.py`). Source tiers (`source_tiers.json`,
  registered 2026-08-01) order the list credible-first and produce
  `spike_quality_tier12_share`; disclosed everywhere as never entering
  any score. Not a historical archive -- only the latest published day
  is kept.
- **2026-08-01, v1.3.0 (comparators and predictability).** Section 10
  added: four-country comparator series from one registered shared
  vocabulary, and the directed lead-lag study whose negative result
  (salience predicts nothing; events marginally lead salience) is
  published as found.

- **2026-07-31, v1.2.0 (stress gauge).** Section 9 added: the India
  Stress Gauge, four pre-registered components fused into one daily
  0-100 line, gated on the completed events history, hit-rate
  published as found. Registration precedes computation in the commit
  history.
- **2026-07-31, v1.1.1 (nowcast).** A provisional "today so far" score
  now publishes to `docs/data/nowcast.json` roughly every two hours,
  computed from a partial-day sample of the Web NGrams bridge with the
  v1.0.1 splice calibration and ranked against each channel's trailing
  730 days exactly as a finished day is. It is labeled provisional
  everywhere it appears, discloses its sample size (`n_samples`,
  `n_docs_sampled`), never enters the historical series, and is
  superseded by the daily run's finalized number. The historical
  construction is unchanged.
- **2026-07-31, v1.1.0 (chokepoint sub-dictionaries).** The shipping
  channel gains four sub-dictionaries (`shipping.chokepoints` in
  `dictionaries.json`: Hormuz 5 terms, Bab el-Mandeb 5, Suez 3, Malacca
  3, each with per-term rationale). They exist only for the
  salience-vs-transits comparison on the analysis page, where each
  corridor's weekly press salience is set against IMF PortWatch transit
  calls, both as percentiles of their own 2019-present weekly history.
  Sub-dictionary series never enter the composite. A sub-dictionary may
  repeat a parent-channel term (it is a decomposition of shipping, not
  an addition) but no term appears in two sub-dictionaries; they carry
  no anchor word because they measure global corridor salience, not
  India-linked salience. The ex-ante rule and query grammar apply
  unchanged and CI enforces both on the new terms
  (`tests/test_dictionaries.py`). Store:
  `data/raw/chokepoint_salience.csv`; site payload:
  `docs/data/chokepoints.json`.
- **2026-07-29, v1.0.1.** (1) Percentile computation now returns
  missing for days with no observed value; previously a missing day
  scored as 0th percentile, deflating the composite when one channel's
  tail lagged. (2) During the July 2026 DOC-API disruption, and at the
  GDELT maintainer's direction, recent days are computed from the Web
  NGrams v5 feed (half-hourly samples, per-document matching, English only)
  and ratio-spliced to the API series on overlap days. Splice ratios
  (log-sd, overlap days): pakistan_west 1.95 (0.38, n=5), china_east
  3.36 (0.46, n=5), gulf_energy 1.79 (0.15, n=5), us_trade 2.56 (n=1),
  shipping 2.97 (n=1); the thin-overlap channels are calibrated on the
  single day both sources cover and marked accordingly. (3) The
  gulf_energy sub-query "crude oil supply" has not yet been fetched by
  any source at historical depth; the channel currently carries its main
  sub-query, and the series will be re-based when it lands. (4)
  Event-study cells now publish bootstrap p-values with
  Benjamini-Hochberg FDR flags (10%) across the grid of relative-outcome
  tests, as §6 specifies.
- **2026-08-05, dictionaries v1.2.0 (precision amendment, founder-
  approved).** Two full-text leak classes removed after practitioner
  and founder review. Shipping: bare `"shipping lanes"` and
  `"maritime security"` dropped (a charity swim story reached the
  receipts via body-text mentions of dodging shipping lanes); standing
  corridor geography `"Gulf of Aden"` and construct vocabulary
  `"merchant vessels"` added to carry the recall. China/East: bare
  `"Arunachal Pradesh"` dropped (as a state name it matched monsoon,
  flood and administrative coverage across the Northeast); the
  standing boundary term `"McMahon Line"` added. Both channels remain
  single sub-queries, so no series-construction change rides along.
  Effects on recall and precision will be measured by the standing
  auditor and published as found. Ex-ante rule enforced by CI on the
  amended lists as on the originals.
- **2026-07-31, v1.1.0-dev (V2 data layers).** (1) Sector event study:
  three sector baskets added beside defence (energy_omc, it_services,
  ports_logistics; members and channel hypotheses pre-registered in
  `validation/sector_hypotheses.json` before any cell was computed).
  Outcome grid doubled, so the 10% FDR threshold tightened: 4 cells now
  flag significant (was 5); the new sector hypotheses are largely NOT
  confirmed at this threshold, a pre-registered negative reported as
  such. (2) Events stream: daily GDELT Events v1 counts for India
  (national, bilateral-dyad, and state layers; `data/raw/events_*.csv`),
  backfilling to 2017. (3) Physical flow: IMF PortWatch daily transit
  calls for Suez, Bab el-Mandeb, Malacca, and Hormuz
  (`data/raw/portwatch_chokepoints.csv`, 2019-present, revisions
  upserted). Attribution: IMF PortWatch (portwatch.imf.org).
- **2026-07-24, v1.0.0.** Initial dictionaries frozen (five channels,
  10-14 terms each, per-term rationale in `dictionaries.json`). Robustness
  variants and placebo channels frozen the same day. Validation episode
  list pre-registered (13 episodes, 2022-2025). Parameters: 730-day
  percentile window, 180-observation minimum, 2σ/90-day/3-day episode rule,
  1/5/20 trading-day event windows, 1,000-resample bootstrap.
