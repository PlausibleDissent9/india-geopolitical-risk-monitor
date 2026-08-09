# Strategy review, 2026-08-09

A structured outside-in pass over IGRM: where it stands against the reference
set, what actually blocks it, what to build, what to stop building.

**Status of this document.** It is analysis, not a registration and not a
public claim. Every number below is read back from a committed payload and
carries its path. Where the review's first draft asserted something the
payloads do not support, the correction is kept in place rather than quietly
removed — see *Two corrections* at the end, both of which changed a
headline claim.

---

## 1. The verdict

The measurement apparatus is better than the measurement. The honesty
machinery is genuinely strong and is not the bottleneck.

The bottleneck is that **nothing has ever left the repository**, and **nobody
who could have said "no" has ever examined the instrument**. Every artifact
is legible only to someone who clones the repo. The audiences named —
academics, journalists, institutional researchers — do not clone repos.

The second constraint is deeper. `analysis/referee_report_2026-08-07.md` is
excellent and *simulated*. The episode lists are founder-written, the
registrations founder-signed, the grading machine-run. The ordering
discipline is real and constrains post-hoc revision, but it cannot
manufacture independence. A referee the project instantiated cannot reject
the project.

---

## 2. What is genuinely ahead

**Blind reconstruction with an enforced import ban.** `src/blind_replicator.py`
rebuilds the published series from `docs/codebook.html` and
`docs/data/shares.csv`, and `tests/test_blind_replicator.py` parses its
imports to forbid touching the pipeline. Alternative codebook readings score
far below, which is what makes the headline result meaningful rather than
tautological. Nothing in the comparison set has an equivalent.

Correct scope, and it matters: it certifies **the documented share→score
transform**, not the measurement. It proves the published numbers follow from
the published inputs by the published rule. It says nothing about whether the
matched articles are on-construct — that is §3.

**Negatives published at the same cadence as positives, by the same code.**
`docs/data/negative_results.json` compiles them from source payloads rather
than hand-typing:

| Finding | Value | Source |
|---|---|---|
| Stress gauge | 2 of 29 | `stress_gauge.json` |
| Predictability | no salience-leading direction clears 0.05 | `predictability.json` |
| India-VIX lead-lag | lag −8, corr **0.0588**, CI [0.0211, 0.0975] | `priced_risk.json` |
| Back-extension | 2 of 4 audited channels refused publication | `back_extension.json` |

The Hindi-vs-English result is the strongest of these because the project
killed its own defence: `us_trade` has the highest Hindi traffic and the
*worst* agreement, so "low traffic explains it" does not survive.

**A vintage integrity ledger.** `docs/data/vintages.json` records 12
vintages with the retrieval command in the payload, so anyone can ask what
the series said on a given day. GPR and EPU revise silently and there is no
ALFRED for text-based risk indices. **10 vintages are clean; 2 are revised,
with 50 and 101 changed values.** That is the honest form of the claim, and
it is still a first — the value is that revisions are *detected and
recorded*, not that none occurred.

---

## 3. What is genuinely behind

**The apparatus barely beats a naive baseline, and the project publishes
this itself.** From `docs/data/detection_baselines.json`:

| Reading | Hits (of 29) |
|---|---|
| Registered criterion | 24 |
| **Naive any-channel detector** | **26** |
| Strict start-based | 19 |
| Chance expectation | 6.8 |

`registered_null: false`. Placebo overlap 0.4522 against random placement
0.3558 — an excess of 0.0964. A reader who opens that file learns the
headline validation figure is beaten by a detector with no dictionaries at
all. The file's own `how_to_read` says the value must therefore lie in
**channel attribution** — and then never computes it. See move 1.

**Precision is unmeasured, and where measured it is poor.** From
`docs/data/precision.json`, `calibrated: false`, 16 author labels:

| Channel | Machine precision | n labelled |
|---|---|---|
| pakistan_west | 0.829 | 35 |
| shipping | 0.538 | 39 |
| gulf_energy | 0.438 | 16 |
| us_trade | 0.243 | 37 |
| **china_east** | **0.209** | 43 |

If these hold, roughly three in four matched articles in two of five
channels are off-construct. **This is the largest scientific liability in the
project** and it sits in a public payload where any competent reader will
find it.

**Other standing gaps.** The series is not one instrument post-2026-06-30
(two splice ratios rest on n=1 with SD printed as 0.0000). Corpus
composition drifts and there is no fixed-panel variant — which is GPR's own
design and the first attack an economist will make. Construct breadth is
five channels, English only, one aggregator, 2017+. And there is no DOI, no
ORCID, no preprint, no listing, no documented external user.

---

## 4. Ten moves, ranked by impact ÷ effort

1. **Compute the channel-attribution statistic.** Conditional on any
   detection within ±3 days, is it in the correct channel? Score against
   prior-frequency assignment and loudest-channel-that-day, with a
   permutation null. Register before computing. This is the central result
   of the five-channel design, sitting unclaimed, and it is the one thing a
   single-number index structurally cannot do. **Hours. Best ratio here.**
2. **Promote the vintage archive from a diff viewer to a dataset.** Long-form
   CSV plus an `as_of(date)` accessor. State the honest scope: the archive
   begins 2026-07-24 and is not a historical real-time dataset. Compounds
   one row per day, forever.
3. **Reframe the headline claims, then mint ORCID + Zenodo DOI.** Order is
   load-bearing — a DOI is permanent, and an over-claimed abstract minted
   today is a permanent liability. Abstract carries 24/29 *with* naive
   26/29 and chance 6.8; replication claim rescoped to the transform;
   precision status in the limitations. **~6 founder-hours, unblocks the
   whole ladder.**
4. **Price the splice, or quarantine it.** A 95% band that omits a ±25-point
   error source is not a 95% band. The headline gets visibly less confident;
   that is the correct outcome and a publishable act.
5. **Recall against a non-press-selected event frame.** UCDP GED and MID 5.0
   are already committed. Every current validation number rests on ground
   truth the founder selected; this is the only test where he did not.
   Recall will likely be poor — publish it with the miss list.
6. **Cut the October contract to three capabilities.** See §5. The only move
   with negative effort, and it pays for 1–5.
7. **Spin the 1979–2019 back-extension out as its own dataset and paper.** A
   41-year India-specific bilateral attention series does not exist in the
   literature, and the refusal rule is the methodological contribution.
   Target a data venue. **Highest citation potential.**
8. **Fixed-panel robustness variant, and start retaining outlet sets today.**
   Buildable only forward from the retention start date, so every day not
   retained is lost permanently.
9. **Field the external precision/recall study.** `validation/precision_v3/`
   is frozen with two prospective cohorts. **By impact alone this is #1**;
   it ranks 9th only on cost. Two channels may fail — publishing a bad
   number plus a re-specification is a stronger credential than an
   unmeasured good one.
10. **Distribution: DBnomics, then Kaggle.** Strictly after move 3; a listing
    without a DOI is an orphan.

Two things deliberately excluded: the India-VIX lead-lag (corr 0.0588 is
statistically nil and must never become a story), and further Indic
buildout — the coverage gradient already published is the publishable
version of that result.

---

## 5. Kill list

Retire per `GOVERNANCE.md` — tombstone, do not delete.

- **The six synthetic conformance payloads and their pages.** They assert
  that a contract works over data that does not exist. The spec says it:
  a synthetic foundation is never evidence that a real dependency exists.
  Keep the schemas; retire the published vectors.
- **`ledger.html`.** A public endpoint whose entire content is a refusal.
  Refusal discipline turned into surface area.
- **`world.html` / `world_state.json`.** A coverage matrix of absences is
  not a measurement.
- **`standard/oges/`.** Publishing a standard before a second implementer
  exists is the clearest signal of premature institution-building.
- **The stress gauge as a live daily lane.** 2/29 is a finding worth keeping
  forever. Recomputing a failed gauge nightly buys nothing.

**One inconsistency to fix rather than kill.**
`governance/source_rights_registry.json` has `default_policy: deny` with
sources at `decision_state: review_required` — including the GDELT feeds
that produce the primary index and publish nightly. The registry blocks new
lanes and grandfathers the core. Either sign the core sources' decisions or
state explicitly that pre-contract lanes are grandfathered and why. As it
stands a hostile reader can point at the project's own governance file and
say the primary product publishes on unreviewed rights.

---

## 6. The credibility ladder

0. **ORCID.** Free, two minutes, must precede the DOI so they link.
1. **Reframed abstract + Zenodo DOI.** Everything below is gated on it.
2. **Preprint.** SSRN rather than arXiv — arXiv econ.GN needs endorsement
   for a first-time submitter, which is real friction for an independent.
3. **A replication a stranger can run in five minutes with no clone.** The
   three-second `--check` is excellent and nobody will ever see it, because
   it needs a checkout. A notebook pulling the published CSVs over HTTPS is
   the highest-conversion artifact available for a skeptical reader.
4. **Registered predictions about the instrument, not the world.** Register,
   before coding begins, the expected precision per channel; publish the
   hit. This scores self-knowledge, and the object predicted is a
   measurement, so it does not violate the no-forecast rule.
5. **Dataset listing.** DBnomics first, after rung 1.
6. **The replication wedge.** Re-run a published result that used GPRC_IND
   with IGRM's decomposition and send it to those authors — outreach that
   hands the recipient a result rather than a request.
7. **One documented external user.** Not a partnership. One named
   researcher or newsroom that used it and will say so.
8. **Peer review.** A data venue for the 41-year series; the tracker is its
   companion, not the submission.

**The order that matters most:** rung 1 before everything, and move 9
before any channel-level claim reaches a wider audience. The failure mode to
avoid is a preprint that lands while `china_east` precision is 0.209 and
unmeasured — because the first competent reader will find that number in the
project's own payload, and will then distrust the parts that are excellent.

---

## Two corrections to this review's first draft

Both were caught by reading the payloads back, and both changed a headline.

1. **"A pre-registered r ≥ 0.4 gate" does not exist.** No such threshold
   appears in `governance/historical_intelligence_contract.json` or in
   `docs/data/back_extension.json`. What is committed is a per-channel
   `overlap_audit` verdict — `tracks` for `pakistan_west` (r = 0.893) and
   `china_east` (r = 0.848), `DOES NOT PUBLISH (negative finding)` for
   `us_trade` (r = 0.216) and `gulf_energy` (r = 0.153). The numeric gate
   was an inference presented as a registration. The codebook entry written
   the same day states the verdicts instead.

2. **"`n_changed_values: 0` across every published vintage" is false.**
   `docs/data/vintages.json` reports `n_vintages: 12`,
   `n_vintages_clean: 10`, `n_vintages_revised: 2`, the two revisions
   carrying 50 and 101 changed values. The defensible claim is that the
   ledger *detects and records* revisions, which is still something no
   comparator offers — not that none occurred.

The pattern in both: an argument for the project reached for a stronger
number than the artifact supports. That is the exact direction of error this
project's whole apparatus exists to catch, and it is worth noting that it
appeared in a document arguing the apparatus is excellent.
