# Simulated hostile referee report — 2026-08-07

Produced by an adversarial review agent instructed to attack the weakest
claims and to recompute published statistics from published files only.
Every recomputation it attempted reproduced (19,830/19,830; placebo
52/115; the splice table; all four AI-GPR correlations) — the findings
below are about **framing and inference**, not arithmetic. Saved verbatim
because several findings change what the paper may claim, and the worst
thing that could happen to this report is that it gets summarised into
harmlessness.

**Triage (by the crew, same day):**

- **Machine-actionable next** (no founder gate): publish chance baselines
  beside the hit rate and placebo (F3, F4 — the referee computed a naive
  any-channel detector at 26/29 vs IGRM's 24/29, chance ≈6.8/29, placebo
  chance 35.6% vs observed 45.2%); define the hit criterion in the
  codebook (start-based gives 19/29, any-day gives 24/29 — the ambiguity
  is one sentence); report rho² beside rho on vs-gpr; run the §8a battery
  on the 7-day headline (F16); year-over-year outlet Jaccard from the
  receipt caches (F15); rescope the replication claim per F5 ("the
  share→score transform is completely documented", not "the index is
  verified") wherever the site or paper leads with it.
- **Already in flight** (Codex's source-replay work addresses the F2
  replay condition; the splice sensitivity payload addresses half of F1;
  the OTS anchoring in A1 of the ideation report addresses F14).
- **Founder-gated**: the construct-name question (F9 — "Anglophone press
  salience" vs the locked IGRM name); channel re-specification for
  gulf_energy (F11) and china_east precision (F8, blocked on the n=100
  labels); adopting new splice ratios (F1, the NOTES 0.24/0.15B call);
  whether to suspend bridge-era channel scores (F1's hard version).

The three acceptance conditions (replay both-columns, base-rate
disclosure, calibration floor) are the referee's; the crew endorses all
three as the paper's to-do list.

---

[Report follows verbatim.]

**Recommendation: Major revision.** The project's transparency apparatus
is unusually good — hash-pinned registrations, published negatives, an
append-only corrections culture — and several headline statistics
reproduce exactly from the published artifacts. But the transparency is
doing rhetorical work that the measurement itself cannot yet support: the
strongest-sounding claims (100% replication, 24/29 detection, the AI-GPR
benchmark) are each weaker than their framing, and the acquisition layer
(splice ratios, zero runs) carries errors that propagate into every
downstream statistic without ever being reflected in the published
uncertainty bands.

## Reproduction record

| Published statistic | Reproduced? |
|---|---|
| 19,830/19,830 exact replication | Yes, exactly |
| Placebo overlap 45.2% (52/115) | Yes, exactly |
| Hit rate 24/29 | Yes — but only under the lenient criterion ("any episode day within ±3"); start-based gives 19/29 |
| Splice shift table | Yes, within 1-dp rounding |
| AI-GPR: rho 0.256 / 0.252, Pearson 0.298 / 0.351, n=108/106 | Yes, all four exactly; provider file SHA matches the registration |

## Findings

1. **[FATAL — post-2026-06-30 channel claims]** The frozen china_east
   splice ratio (3.3612, n=5) vs the independent audit (2.6998, n=18,
   log-SD 0.3954) moves the 7-day headline up to 25.6 points; us_trade
   and shipping ratios rest on n=1 with an SD printed as 0.0000; the
   published 95% bands treat the ratio as exactly known. A 95% band that
   omits a ±25-point error source is not a 95% band.
2. **[FATAL — the primary series as an object of record]** source_replay
   evidence: seven exact-zero runs (54 channel-days) replay positive on
   all 54; substitution changes 1,740 us_trade scores (max 97.5), 532
   shipping, 1,826 composite days (max 19.5). No downstream statistic is
   rerun under the correction; only the flattering series is headlined.
3. **[MAJOR]** 24/29 depends on an undisclosed lenient criterion
   (start-based: 19/29); double-credits single detections (24 hits ≤ 22
   distinct); never benchmarked against base rates — random ≈6.8/29,
   naive any-channel spike detector 26/29.
4. **[MAJOR]** Placebo 45.2% lacks its chance baseline: real episodes
   cover 27.8% of days; random placement expects 35.6%. The excess is
   ~10 points at ≈2.2σ, and no null was ever registered.
5. **[MAJOR]** The 19,830/19,830 replication certifies the documented
   transform, not the measurement; misbilled as the strongest claim
   while acquisition (findings 1–2) is where the uncertainty lives.
6. **[MAJOR]** AI-GPR framing converts near-orthogonality (rho²=6.5%,
   CI lower bound 0.050) into an achievement via a decision rule
   authored with data in hand; registered nine minutes after the fetch.
7. **[MAJOR]** Cross-source (GDELT vs Wikipedia) correlations are ≈0
   (pakistan_west −0.02); the validation page still frames the check as
   support.
8. **[MAJOR]** Machine-audited precision: china_east 0.209, us_trade
   0.243 — UNCALIBRATED at 16/100 author labels. The channel with the
   worst splice uncertainty has the worst precision.
9. **[MAJOR]** The Anglophone finding contradicts the instrument's name;
   "established name" is not available to a two-week-old index.
10. **[MAJOR]** The codebook calls the composite "no clean
    interpretation," yet it anchors the AI-GPR primary statistic and the
    front page.
11. **[MAJOR]** gulf_energy carries 38% of the validation weight with
    the worst dictionary stability (0.527), sub-0.5 precision, and
    mostly non-India-specific events.
12. **[MINOR]** The china_east ratio/dictionary calibration
    inconsistency is disclosed in analysis/ but not on the public page.
13. **[MINOR]** Detector blindness (threshold up 28× after Pahalgam)
    interacts flatteringly with the ±3/any-day hit criterion; publish
    the frozen-threshold counterfactual hit rate.
14. **[MINOR]** Every "registered before computed" claim rests on
    repo history a referee cannot independently verify; complete the
    OTS anchors and archive the SHAs externally.
15. **[MINOR]** GDELT's corpus halved 2022→2026; the drift checks
    cannot detect composition change. Publish outlet-set Jaccard by year.
16. **[MINOR]** The 7-day headline's detection quality rests on two
    hand-picked anecdotes; run §8a on composite7.

## Conditions for acceptance

1. **Replay condition:** rerun §8a, the AI-GPR protocol, and the event
   study on the replay-substituted store; publish both columns.
2. **Base-rate condition:** codebook-level hit criterion; unique
   crediting; chance baselines beside 24/29 and 45.2%; registered
   permutation null; one recall test on a non-press-selected event set.
3. **Calibration condition:** no channel over a bridge with <14
   independent overlap days; bands include ratio uncertainty; complete
   the n=100 calibration; re-specify any channel below 0.5 precision.

*"The revision it needs is not more honesty — it is moving the honesty
from the payloads into the headline claims, so that the numbers a reader
quotes carry the same qualifications as the JSON files almost nobody
opens."*
