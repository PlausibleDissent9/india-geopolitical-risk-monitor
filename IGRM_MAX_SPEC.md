# IGRM — The Maximum Version

What this instrument looks like at its ceiling, what each addition buys,
which limitations can be mitigated and how, and which are permanent.

Written July 2026. Assumes the current live system (GDELT single-source,
2022–2026, five channels, event study, live site) as the starting point.

---

## PART I — THE MAX SYSTEM, LAYER BY LAYER

### Layer 1 — Multi-source attention measurement

**GDELT DOC API** (current). Article-share of global coverage matching each
channel's dictionary. Daily, back to 2017. The workhorse.

**Wikipedia pageviews** (add). Daily views for a curated set of articles per
channel — "Line of Actual Control," "Strait of Hormuz," "India–Pakistan
relations." Free API, no rate limits, back to 2015.
*Why it matters:* this is **public attention**, not press production. Press
coverage is supply-side (editors decide what to write); pageviews are
demand-side (people decide what to read). When they diverge, that's a finding,
not noise.

**Google Trends** (add, optional). Search interest for channel-relevant terms.
Third independent attention signal. Caveat: normalized index, not raw counts,
and the API is awkward — treat as supporting evidence, not a core series.

**Output:** three parallel attention series per channel, each normalized the
same way, plus a combined measure and — critically — **pairwise divergence
series** (GDELT vs Wikipedia, etc.).

### Layer 2 — Priced-risk benchmark

**India VIX** (options-implied volatility on Nifty). Already in your market
pull. Elevate it from descriptive to a first-class comparison series.

**India sovereign CDS spreads** if obtainable, or USDINR implied vol as a
proxy. These measure what people pay to hedge — the closest available thing
to "actual perceived risk."

**The key construct: the attention–pricing gap.**
Normalize both to percentiles. Where attention is high and priced risk is
flat, the press is louder than the market. Where priced risk moves without
attention, markets know something the coverage hasn't caught.
*This gap is more interesting than either series alone, and it's the single
strongest intellectual addition available to this project.*

### Layer 3 — Measurement construction

- Trailing 730-day percentile per channel per source (current method).
- Combined index: state explicitly whether sources are averaged, weighted, or
  reported separately. **Recommended: report separately as the headline, with
  an averaged composite clearly labelled a convention.**
- Composite across channels: unweighted mean, labelled a transparency
  convention, never a claim about relative importance.
- Episode detection: mean + 2σ over 90 days on **raw volume shares** (not
  bounded percentile scores), clustered with a 3-day gap rule.

### Layer 4 — Validation (where credibility actually lives)

This is the layer almost every student project skips. It is the difference
between a dashboard and an instrument.

**4a. Historical event detection.** Fix dictionaries ex ante (structural terms
only, no event names). Then test: does the index spike within ±3 days of a
pre-registered list of major episodes? Report hit rate per channel.
*This is the single most convincing figure the project can produce.*

**4b. Dictionary robustness.** Build 3 alternative dictionary versions per
channel — broader, narrower, differently-worded. Recompute the full index.
Report pairwise correlations across versions.
*If the composite correlates >0.9 across reasonable alternatives, "why these
terms?" stops being a fatal question.*

**4c. Cross-source agreement.** Correlation between GDELT and Wikipedia
attention per channel. High agreement = the signal isn't a GDELT artifact.
Persistent divergence = a documented finding about supply vs demand attention.

**4d. Placebo channels.** Construct 2–3 channels for topics with no plausible
India-geopolitics link (e.g. a sports or entertainment term-set). They should
NOT spike around geopolitical episodes.
*This is the cheapest, most powerful robustness check available and it takes
about two hours. If placebo channels spike too, your detection is measuring
general news volume, not geopolitical salience.*

**4e. Stability across normalization windows.** Recompute with 365-day and
1095-day windows. Results should be qualitatively unchanged.

### Layer 5 — Analysis

- Event study on India-specific **relative** returns only:
  Nifty − EM (strips global equity beta),
  defence basket − Nifty (the India-specific hypothesis),
  USDINR − DXY (strips broad dollar moves).
- Windows: 1 / 5 / 20 **trading** days.
- **Bootstrapped confidence intervals** (1000 resamples) on every estimate.
- **Multiple-comparisons correction** (Benjamini–Hochberg) across the full
  test grid: channels × outcomes × windows.
- **Lead–lag analysis** between attention and priced risk: does attention
  precede implied-vol moves, follow them, or neither? Cross-correlation
  function with confidence bands.
- All language: "associated with." Never "caused," never "predicts."

### Layer 6 — Delivery

- Live site: composite, five channels, multi-source toggle, interactive chart
  with episode shading, per-episode detail pages.
- **Versioned open data** with a Zenodo DOI per release, CC BY 4.0.
- Public methodology page rendered from methodology.md.
- Weekly sourced dossier → your 250-word note → published to IGRM and
  Indiconomics simultaneously.
- Optional: a simple JSON API endpoint so others can query the index.
- Full reproducibility: a stranger clones the repo, runs one command, gets
  your numbers.

---

## PART II — LIMITATIONS: WHAT CAN AND CANNOT BE FIXED

### FIXABLE — with the specific mitigation

**1. Single-source dependency**
*Mitigation:* Wikipedia pageviews + Trends. Cross-source correlation
quantifies how much is GDELT-specific.
*Residual:* both corpora share English-language and Western-outlet skew.
Agreement between biased sources isn't proof of unbiasedness — say so in §7.

**2. "Why these terms?" (dictionary sensitivity)**
*Mitigation:* Layer 4b robustness harness. Show correlations across 3
alternative dictionaries.
*Residual:* you still chose the alternatives. Mitigated, not eliminated.

**3. Circularity in validation**
*Mitigation:* the ex-ante structural-terms rule, enforced in CI. Pre-register
the validation episode list before running 4a.
*Residual:* you wrote the dictionaries in 2026 knowing 2017–26 history.
Hindsight is bounded by the rule, not removed. Disclose it.

**4. Multiple comparisons / fishing**
*Mitigation:* Benjamini–Hochberg correction, plus pre-registering the primary
hypothesis (defence-basket) and labelling everything else exploratory.
*Residual:* none material, if done honestly.

**5. Point estimates without uncertainty**
*Mitigation:* bootstrapped CIs on every event-study number. Report intervals,
not points.
*Residual:* intervals will be wide. That's honest, not a flaw.

**6. Thin sample**
*Mitigation:* extend to 2017 (doubles episodes); consider lowering the spike
threshold to 1.5σ as a *secondary* specification, reported alongside 2σ.
*Residual:* the binding constraint is how many geopolitical episodes India has
actually had. Cannot be manufactured.

**7. Correctness risk (timezone, holidays, lookahead)**
*Mitigation:* the hardening pass + tests in CI. A no-lookahead test is
non-negotiable.
*Residual:* none, if tested.

**8. Composite arbitrariness**
*Mitigation:* label it a convention; make components the headline; optionally
publish 2–3 alternative weightings (equal, trade-exposure, import-exposure) so
readers see the answer isn't weighting-dependent.
*Residual:* no weighting is theoretically privileged. Disclosure is the fix.

**9. Anniversary / editorial-cycle effects**
*Mitigation:* measure it. Regress channel volume on day-of-year fixed effects;
report how much variance anniversaries explain. Optionally publish a
deseasonalized variant.
*Residual:* salience genuinely includes anniversary attention. Arguably a
feature; disclose either way.

**10. "It's called a Risk Monitor but measures salience"**
*Mitigation:* a one-line definition directly beneath the headline number on
the site, plus §1 of the methodology. This is exactly what Caldara–Iacoviello
do — their index is named "Geopolitical Risk" and measures newspaper shares.
*Residual:* none, once stated plainly. Naming convention, not a claim.

### NOT FIXABLE — the honest boundary of the method

**A. Salience is not risk.** Every source you add measures attention. Adding
a priced-risk benchmark lets you *study the gap* — which is genuinely more
interesting — but the index itself never becomes a risk measure. Permanent.

**B. No causal identification.** There is no natural experiment, instrument,
or discontinuity available in this design. You cannot separate "coverage moved
markets" from "both responded to the same underlying event." Permanent, at any
level of statistical sophistication.

**C. Inference-grade power is unreachable.** Tens of episodes, not thousands.
Wide intervals forever. Descriptive findings only. Permanent.

**D. No actionable prediction.** Weak, honestly-framed forecasting results are
obtainable. Nothing tradeable. Permanent.

**E. Source bias survives.** Cross-validation quantifies divergence; it does
not produce an unbiased measurement. Permanent.

---

## PART III — THE HONEST CEILING

Fully built, this is a **well-characterized descriptive instrument** that:

- measures multi-source attention to India-relevant geopolitical topics,
- validates that measurement against pre-registered historical episodes,
- demonstrates robustness to reasonable alternative constructions,
- documents where attention diverges from priced risk,
- reports associations with India-specific relative returns, with honest
  uncertainty and correction for multiple testing,
- and states precisely what it cannot do.

That is a citable working paper — something another researcher could adopt,
critique, or extend. It is realistically the ceiling for one person without a
lab, a data budget, or proprietary access.

**What it is not, and never becomes:** a risk measure, a causal study, a
forecasting tool.

**The thing that makes it credible is not the feature count.** It is Layer 4
plus a methodology section that names every limitation above without being
asked. A three-source validated index with a sharp methodology beats a
six-source unvalidated one in front of anyone whose opinion matters.

---

## PART IV — BUILD ORDER (highest value first)

1. Correctness hardening + tests in CI *(2–3 hrs)* — protects everything else
2. **Placebo channels** *(2 hrs)* — cheapest, most powerful validation
3. Historical validation suite *(2–3 hrs)* — your key figure
4. Dictionary robustness harness *(3–4 hrs)* — kills the main attack
5. Extend backfill to 2017 *(free, cached)* — doubles sample
6. Bootstrapped CIs + BH correction *(2–3 hrs)* — statistical credibility
7. Wikipedia pageviews as source two *(4–6 hrs)* — independent validation
8. Attention–pricing gap series *(6–8 hrs)* — most interesting addition
9. Anniversary-effect quantification *(2 hrs)* — turns a limitation into a result
10. Site polish, episode pages, DOI, API *(6–8 hrs)*
11. Weekly sourced dossier *(3–4 hrs)* — workflow quality of life

**~35–45 hours of build.** Items 1–6 (~12–15 hrs) capture most of the
credibility gain. Items 7–11 are refinement.

**Not on this list, because they aren't build tasks:** the five dictionaries,
methodology.md §§1–8, and the weekly notes. Specifications for maximum-quality
versions of all three are in Part V.

---

## PART V — THE AUTHORED COMPONENTS AT MAXIMUM

Three artifacts are not code: the dictionaries, methodology.md, and the weekly
notes. Below is what a maximum-quality version of each looks like — structure,
criteria, tests, and the failure modes that separate a strong version from a
weak one.

---

### V.1 — DICTIONARIES

**What a maximum dictionary is:** a net that catches coverage of a channel with
high recall and low contamination, where every term survives the question
*"why this term, and why not the obvious alternative?"*

**Structure — four term categories per channel.** A strong dictionary draws
from all four; a weak one is all geography.

| Category | What it catches | Failure if omitted |
|---|---|---|
| **Geography** | Named places where tension physically manifests | Miss nothing — but geography alone under-detects diplomatic and process coverage |
| **Institutions & actors** | Forces, bodies, standing mechanisms, talks formats | Miss the entire diplomatic/negotiation news cycle |
| **Doctrine & recurring press language** | The vocabulary reporters reuse across events | Miss the majority of recall; this category usually carries the most weight |
| **Structural assets & chokepoints** | Physical infrastructure whose disruption is the story | Miss supply-side and maritime coverage |

**Sizing:** 8–15 terms per channel. Below 8, recall is too thin and the series
is noisy. Above 15, marginal terms start importing contamination faster than
signal.

**Hard constraints:**

1. **Ex-ante rule.** No retrospective event names. A spike at a known episode
   must be *detected* by structural terms, never *baked in* by naming the
   event. Enforced in `tests/test_dictionaries.py`, run in CI.
2. **Anchor generic terms.** A bare country-pair ("India China") catches trade,
   cricket, diplomacy, everything. Every generic term needs a qualifier that
   constrains it to the channel.
3. **Declare cross-channel bleed deliberately.** Some terms plausibly belong to
   two channels. Decide, document the decision, and be consistent — silent
   double-counting inflates the composite.
4. **Phrase-quote exact multi-word terms.** Unquoted multi-word strings become
   AND-queries and silently change what you're measuring.

**Per-term documentation.** Each term carries one line: *why this term.* These
lines are the raw material for methodology §2, and they are the answer when
someone asks how the net was built.

**Four tests a maximum dictionary passes:**

- **Recall test.** Take 3–5 real episodes per channel from the sample period.
  Would these terms have caught the coverage? If not, what category is missing?
- **Precision test.** Sample 20 articles the query actually returns. What
  fraction are genuinely about this channel? Below ~70%, the terms are too loose.
- **Robustness test.** Build broader and narrower variants; the resulting index
  should correlate >0.9 with the primary. If it doesn't, the result is
  term-dependent and must be reported as such.
- **Placebo test.** A term-set for an unrelated topic should not spike during
  geopolitical episodes. If it does, the pipeline is measuring general news
  volume, not channel salience.

**Freeze discipline.** Set `_meta.frozen_on` at launch. Every post-freeze change
goes in the methodology changelog with a date and a reason. An index whose
definition moves silently is not reproducible.

---

### V.2 — METHODOLOGY.MD

**What a maximum methodology is:** a document written to a hostile expert
reader, in which every parameter is justified, every convention is labelled as
a convention, and every limitation is named before the reader can raise it.

**Section-by-section: the question each must answer, and what strong vs weak
looks like.**

**§1 — What the index measures.**
*Question answered:* "What does a score of 79 actually mean?"
Must state: the measurement object (press salience), the normalization frame
(percentile against trailing 730 days, per channel), and — the harder sentence
— what it explicitly does **not** mean. Must name the salience/risk divergence
directly: under-covered crises, anniversary attention, editorial fashion.
*Weak version:* describes the pipeline. *Strong version:* defines the construct
and immediately bounds it.

**§2 — Term selection and the ex-ante rule.**
*Question answered:* "Why these terms and not others?"
Must contain: per-channel rationale (the one-liners from V.1), the four-category
logic, the ex-ante rule and *why circularity makes event names inadmissible*,
how the rule is enforced in code, the freeze date, and the changelog.
*Weak version:* lists the terms. *Strong version:* explains the selection
principle such that a reader could construct a sixth channel correctly.

**§3 — Normalization.**
*Question answered:* "Why percentile rank, and why 730 days?"
Must justify percentile over z-score (news volume is fat-tailed and drifts
secularly; percentile is robust to both and yields an interpretable statement),
and the window length as a stability/recency trade-off. Must state the
minimum-observations rule and what happens before it is met.
*Weak version:* states the parameters. *Strong version:* argues why the
alternatives are worse.

**§4 — The composite convention.**
*Question answered:* "Why unweighted, and what does the headline number claim?"
Must state explicitly that the unweighted mean is a **transparency convention,
not a claim about relative importance**, that components are the primary
product, and — at maximum — must report alternative weightings so the reader can
verify conclusions are not weighting-dependent.
*Weak version:* "we take the average." *Strong version:* concedes the
arbitrariness, then demonstrates it doesn't drive results.

**§5 — Spikes and episodes.**
*Question answered:* "What counts as an event, and why that threshold?"
Must specify: mean + 2σ over 90 days on **raw volume shares, not bounded
percentile scores** — and explain why (a bounded series can make a 2σ threshold
unreachable). Must justify clustering into episodes rather than counting spike
days, and state the gap rule. At maximum: report a secondary threshold (1.5σ)
alongside to show the finding isn't threshold-dependent.

**§6 — Event-study design.**
*Question answered:* "How do you isolate India-specific effects, and what are
you claiming?"
Must justify each relative outcome — Nifty − EM strips global equity beta,
defence − Nifty isolates the India-specific hypothesis, USDINR − DXY strips
broad dollar moves — and state why Brent and gold are descriptive-only (no
India-specific component is separable in a global commodity). Must specify the
window convention (trading days, inclusive of episode start) and state the
language rule: association, never causation, with the reason.

**§7 — Limitations.**
*Question answered:* "Where does this break?"
This section is where a serious reader forms their judgment. It must name,
unprompted: salience ≠ risk; no causal identification; sample-size limits on
inference; single/multi-source bias that cross-validation quantifies but does
not remove; anniversary effects as a construction feature; hindsight in
dictionary construction and how the ex-ante rule bounds but does not eliminate
it; timezone convention; composite arbitrariness.
*Weak version:* two hedging sentences. *Strong version:* enumerated, specific,
each with its mitigation and its residual — such that a critic finds nothing to
add.

**§8 — Validation.**
*Question answered:* "How do I know this measures anything real?"
Must contain: the pre-registered episode list, the detection window (±3 days),
hit rate per channel, placebo-channel results, cross-source agreement
statistics, and dictionary-robustness correlations. This is the section that
converts the project from a dashboard into an instrument.

**Changelog.** Every post-freeze parameter or dictionary change, dated, with a
reason. Reproducibility depends on it.

**Overall test for the finished document:** hand it to someone who wants to
dismiss the project. If they cannot raise an objection that isn't already
addressed in §7, the methodology is at maximum.

---

### V.3 — THE WEEKLY NOTE

**What a maximum weekly note is:** ~250 words that convert a data movement into
an interpretation a reader could not have produced from the chart alone.

**Structure:**

1. **Headline claim** (1 sentence) — the single most important thing that moved,
   stated as a claim, not a description. "Shipping salience hit its highest
   level since X" is a description; "the Red Sea story is now driving more
   India-relevant coverage than the LAC, for the first time in eighteen months"
   is a claim.
2. **Mechanism** (2–3 sentences) — *why* it moved, grounded in the sourced
   articles from the weekly dossier. This is where citations attach.
3. **What it does and doesn't imply** (1–2 sentences) — the discipline that
   separates analysis from commentary. Explicitly bound the reading.
4. **One number worth remembering** (1 sentence).

**Quality criteria:**

- **Falsifiable, not vague.** A claim someone could disagree with beats a
  summary nobody could dispute.
- **Grounded in the week's sources**, not general knowledge — the dossier's
  citations are the evidence base.
- **Honest about the instrument.** If a spike is plausibly an anniversary
  artifact or a coverage-drift artifact, saying so is stronger than ignoring it.
- **Consistent voice across weeks.** An archive of notes with a recognizable
  analytical style is itself evidence; a set of interchangeable summaries is not.

**Failure modes:** restating the numbers in prose; hedging every claim into
meaninglessness; asserting causation the instrument cannot support; writing
about geopolitics generally rather than about what the index did.

**Cadence over polish.** Fifteen consecutive notes of consistent quality is a
stronger artifact than three excellent ones and a gap. The archive is the
product.
