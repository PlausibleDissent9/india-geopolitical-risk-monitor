# Construction and Validation of a Press-Salience Index for India-Related Geopolitical Risk

**Ishan Krishna** · Working paper, v0.1 (July 2026) · Data and code: https://plausibledissent9.github.io/india-geopolitical-risk-monitor/

<!-- HOW TO USE THIS SCAFFOLD
Sections marked [YOUR VOICE] carry the paper's judgment; write them
yourself, and expect interview questions to come from them. Sections
marked [DRAFTED] are factual restatements of the published methodology
and validation numbers; edit for voice but the facts stand. Keep the
whole thing at 4-6 pages; the archive of weekly notes is the long form.
Delete these comments as you go. -->

## Abstract [DRAFTED — tighten in your voice]

I construct a daily, category-decomposed index of press salience for
India-related geopolitical risk in the article-share tradition of
Caldara and Iacoviello (2022). Five channels — the Pakistan and China
borders, Gulf energy security, US trade policy, and shipping
chokepoints — are measured as the share of English-language global news
coverage matching frozen, ex-ante term dictionaries over 2017–2026, and
normalized to trailing two-year percentiles. Against a pre-registered
list of 21 major episodes whose names appear in no query, the index
detects 18 within ±3 days (86%). Results are stable across
normalization windows (ρ = 0.96–0.99), and calendar recurrence explains
only 4–7% of channel variance. Comparing attention to options-implied
volatility, changes in India VIX tend to precede changes in press
attention by roughly two trading days — markets first, press second.
The index measures attention, not risk, and reports associations, not
causes; all data, code, and validation results are public.

## 1. Motivation [YOUR VOICE]

<!-- The questions this section must answer, in your words:
- Why does India-specific geopolitical salience deserve its own index
  when a global GPR index exists? (Hint: composition — India's risk mix
  of two land borders + energy imports + US trade dependence + sea lanes
  is not a scaled-down copy of global risk.)
- Why measure the press at all? (The C-I argument: newspaper attention
  is the observable trace of risk perception; and for India, no public
  daily decomposition exists.)
- One paragraph on what you personally wanted to know that no existing
  series answered. This is the paragraph an interviewer remembers. -->

## 2. Related work [DRAFTED — verify citations read naturally]

Caldara and Iacoviello (2022) construct the canonical geopolitical risk
index from newspaper article shares, naming it a *risk* index while
measuring press coverage — a naming convention this project follows,
with the divergence stated explicitly. Baker, Bloom and Davis (2016)
established the newspaper-share method for economic policy uncertainty.
This index differs in three ways: it is India-specific and
category-decomposed; its dictionaries are frozen ex ante with a
CI-enforced ban on retrospective event names; and its detection claims
are validated against a pre-registered episode list rather than
illustrated anecdotally.

## 3. Construction [DRAFTED]

Five channels, each defined by 10–14 quoted phrases across four
categories (geography, institutions, doctrine vocabulary, chokepoints),
frozen 2026-07-24 with a per-term rationale published beside the code.
The ex-ante rule bars any term naming a specific event (Galwan,
Pulwama, Doklam, …), enforced by a test suite in CI: spikes must be
*detected* by structural vocabulary, never baked in. Daily raw values
are the percentage of GDELT-monitored English articles matching each
channel's query; channels needing multiple sub-queries (API length
limits) sum their sub-query shares, a disclosed slight upper bound on
the union. Scores are percentile ranks against the channel's own
trailing 730 days (minimum 180 observations); the composite is the
unweighted mean of the five, published as a transparency convention
with alternative weightings released alongside. From July 2026 the
recent tail is computed from GDELT's raw Web NGrams files (per the
maintainer's direction during a DOC-API disruption), ratio-spliced to
the API series on overlap days with the splice dispersion published.

## 4. Episodes and the event study [DRAFTED]

A spike day exceeds the trailing 90-day mean by two standard deviations
(baseline lagged one day; detection on raw shares, since bounded
percentiles compress extremes); spike days within three days cluster
into episodes — 517 across 2017–2026. Around episode starts, the event
study reports cumulative India-specific *relative* returns — Nifty
minus MSCI EM, a defence basket minus Nifty, USDINR minus DXY — over 1,
5, and 20 trading days with bootstrapped 95% intervals and
Benjamini–Hochberg correction across the test grid. Brent and gold are
descriptive only. All language is associational: coverage and prices
respond to the same underlying events, and nothing in this design
separates the two.

## 5. Validation [DRAFTED — add one sentence of your reading]

Twenty-one episodes (2017–2025) were pre-registered before any
validation ran; none of their names appears in any query. Detection
within ±3 days succeeds for 18 of 21 (86%). The three misses are
informative rather than embarrassing: the Doklam standoff built too
slowly for a ±3-day window (a limitation of window choice, flagged at
pre-registration), and the Abqaiq attack and 2020 OPEC+ collapse fall
in the one channel whose supply-side sub-query could not be fetched at
launch — both are re-tested when it lands. Percentile scores correlate
0.96 (365-day) and 0.99 (1095-day) with the primary 730-day window.
Day-of-year effects explain 4.1–7.2% of detrended log-share variance —
anniversary journalism exists but does not drive the series. Placebo
channels (IPL cricket, Bollywood) and dictionary-robustness
recomputation run in CI and publish to the site's validation page;
GDELT-vs-Wikipedia cross-source correlations are low (−0.02 to 0.19),
which I report as a genuine supply-versus-demand attention divergence
rather than a validation failure. <!-- [YOUR VOICE]: one or two
sentences on what the cross-source divergence means to you. -->

## 6. Attention and priced risk [YOUR VOICE, numbers drafted]

The gap series — attention percentile minus India VIX percentile on
shared trading days — identifies when the press runs hotter than the
market and vice versa. In cross-correlation, changes in the VIX
percentile lead changes in composite attention with the largest
association at a lag of two trading days.
<!-- Your interpretation here is the paper's most original paragraph:
markets appear to reprice before coverage accumulates. What does that
imply about what a salience index is for? (One honest answer: it is a
better narrative-tracker than early-warning system — which is exactly
what a salience index should claim.) -->

## 7. Limitations [DRAFTED — from methodology §7, keep the candor]

Salience is not risk: under-covered crises score low and anniversary
coverage scores high, by construction. No causal identification exists
or is claimed. With tens of episodes, not thousands, intervals stay
wide and findings stay descriptive. All sources share English-language
and Western-outlet skew; cross-source agreement cannot remove shared
bias. Dictionary hindsight is bounded by the ex-ante rule, not
eliminated. The July 2026 source switch introduces a spliced seam,
published with its calibration dispersion.

## 8. Conclusion [YOUR VOICE]

<!-- Three sentences: what exists now that didn't before; what it can
and cannot answer; what you will do with it (the weekly-note archive
and the post-freeze roadmap). No grand claims — the restraint IS the
conclusion. -->

## References

- Caldara, D., & Iacoviello, M. (2022). Measuring Geopolitical Risk.
  *American Economic Review*, 112(4), 1194–1225.
- Baker, S. R., Bloom, N., & Davis, S. J. (2016). Measuring Economic
  Policy Uncertainty. *Quarterly Journal of Economics*, 131(4),
  1593–1636.
- Leetaru, K., & Schrodt, P. A. (2013). GDELT: Global data on events,
  location, and tone. *ISA Annual Convention*.
- IGRM data, code, dictionaries, and validation:
  https://github.com/PlausibleDissent9/india-geopolitical-risk-monitor
