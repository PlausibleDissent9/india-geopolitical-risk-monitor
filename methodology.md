# IGRM Methodology

Version 1.1.1 · five channels frozen 2026-07-24, chokepoint sub-dictionaries and nowcast added 2026-07-31 · [changelog](#changelog) at the end.

## 1. What the index measures (and what it does not)

The index measures **press salience**: for each of five channels, the share
of all articles GDELT monitors globally that match the channel's term set,
expressed as a percentile against that channel's own trailing 730 days. A
composite score of 79 means exactly this: *today's matching-coverage share,
averaged across the five channels' percentiles, is higher than it has been
on 79% of days over roughly the past two years.* Nothing more.

It is built in the Caldara-Iacoviello article-share tradition, whose index
is also named "Geopolitical Risk" and also measures newspaper shares. The
name is a convention of the genre, not a claim: **salience is not risk.**
The two diverge in known, unavoidable ways, an under-covered crisis scores
low; anniversary retrospectives score high (§7); editorial fashion moves
the series with no change in the world. The index answers "how much is the
press writing about this?", never "how dangerous is this?". It is not a
forecast and not investment advice.

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
Three generic phrases are accepted with open eyes and disclosed here:
`"energy security"` and `"maritime security"` (broader than their channels;
kept for recall of policy coverage) and `"Suez Canal"` (includes routine
transit coverage; the percentile normalization absorbs its baseline).

**Cross-channel bleed, decided and documented:** `"Russian oil"` (India)
sits in *US & Trade Policy*, not *Gulf & Energy*, the risk vector is
sanctions policy, not physical supply. Red Sea tanker coverage belongs to
*Shipping*; Persian Gulf tanker incidents to *Gulf & Energy*. No term
appears in two channels, so the composite never double-counts an article
across the declared boundaries.

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
direction, the same share construct from hourly samples of the raw
feed, and ratio-spliced to the API series on overlap days, with each
channel's splice ratio and its dispersion published alongside the data
(see changelog). The published score is the
percentile rank of today's share within the channel's trailing 730 days
(inclusive of today; the window never contains future data). Days with
no observed value stay missing rather than scoring zero.

*Why percentile rather than z-score:* news-volume shares are fat-tailed and
drift with editorial fashion. A z-score inherits both problems, single
extreme days distort the mean and variance for months. The percentile is
robust to outliers, invariant to monotone changes in the level of coverage,
and yields a directly interpretable sentence ("higher than X% of the last
two years"). Its cost, compression at the top of the range, is why episode
detection does *not* run on scores (§5).

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
- **USDINR − DXY**, strips broad dollar moves from the rupee.

Brent and gold are reported **descriptively only**: no India-specific
component of a globally-priced commodity is separable, so they carry no
interpretation beyond context. Windows are 1, 5, and 20 **trading** days,
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
   backfill extension to 2017 planned. Residual: intervals stay wide
   forever; findings stay descriptive.
4. **Single-source dependency.** Everything currently rests on GDELT's
   corpus and its English-language, Western-outlet skew. Mitigation
   (planned): Wikipedia-pageview cross-validation. Residual: agreement
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
   the daily run at 18:00 IST treats "today" as the UTC date. A same-day
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
run.

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

## Changelog

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
  NGrams v5 feed (hourly samples, per-document matching, English only)
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
