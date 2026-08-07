# IGRM founder interview — working copy

**Purpose.** These answers supply the parts of the working paper that must
sound like Ishan rather than a research apparatus. That is the whole point of
the exercise, so the answers have to be his. Nobody else can write them —
not a co-author, not a model. A paper whose "what surprised me" was invented
is a paper with a fabricated premise in it, and that is the one defect the
rest of IGRM's honesty apparatus could not survive.

**What this document does instead.** Under each question sits the *verified
number* from the repo, with its source file, so answering is a matter of
reacting to a fact rather than recalling one. Blunt fragments are better than
prose. Voice notes are fine.

**Status:** answers blank as of 2026-08-07. Facts current as of the same date.

---

## Before you start: three premises in the question set are wrong

Worth fixing before they reach a draft, because two of them are unflattering
in the *wrong* direction — they understate the instrument.

| The question says | The data says | Source |
|---|---|---|
| "the fused gauge detecting only 1/21" | **2 of 29**, hit rate 0.069 | `docs/data/stress_gauge.json` → `validation` |
| "the historical border-channel replication" (as one finding) | Two findings: pakistan_west **r = 0.893**, china_east **r = 0.848** publish; us_trade **0.216** and gulf_energy **0.153** were withheld under the pre-registered rule | `docs/data/back_extension.json` → `overlap_audit` |
| implies the index's own detection is comparable to the gauge's | The index's episode detection is **24 of 29** at ±3 days. The gauge is 2 of 29. The gap between those two numbers is itself a finding | `docs/data/validation.json` → `hit_rate` |

That third row is probably the most interesting thing on this page: **fusing
four sources made detection dramatically worse than the press channel alone.**
If you want one answer to Q3 that no reviewer will have seen coming, it is
sitting there.

---

# The origin

## 1. What exact question were you trying to answer when IGRM began? Name the event or frustration that made the existing indexes feel insufficient.

*No repo fact can answer this. It is the one paragraph a reader will remember.*

Prompts, not answers — what was on screen when you decided the existing thing
was not good enough? Was it a specific index, a specific day, a specific
number that was obviously wrong about India?

**Your answer:**

>

---

## 2. Why are the five channels the correct decomposition for India? Which one would a global index most badly misunderstand?

**Facts you can lean on:**

- The five: `pakistan_west`, `china_east`, `gulf_energy`, `us_trade`,
  `shipping`.
- **`shipping` is the channel with no actor-pair analog at all.** The
  1979–2019 back-extension could not build it and never will from that
  source: chokepoint salience has no bilateral coding, because there is no
  country the Strait of Hormuz is in a relationship with
  (`src/back_extension.py`). A global event-based index structurally cannot
  see this channel.
- **`gulf_energy` is the channel that is most "India-shaped."** Its narrow-
  dictionary robustness correlation is **0.527**, the lowest of the five
  (next lowest `us_trade` 0.663; `china_east` 0.895). Low robustness there
  means the construct is genuinely sensitive to how you word it — which is
  an argument that it is doing specific work, and also its weakest point.
  (`docs/data/validation.json` → `robustness`)

**Your answer:**

>

---

# What the instrument taught you

## 3. Which finding genuinely surprised you?

**The five candidates, with their actual numbers. Pick the one that actually
surprised *you* — the paper needs your reaction, not the biggest number.**

**(a) Markets lead the press by about eight days.** Largest association at
**lag −8**: India-VIX percentile changes tend to *precede* attention changes.
Association, not causation, and stated that way everywhere.
`docs/data/priced_risk.json` → `lead_lag.reading`

**(b) Fusing four sources destroyed detection.** The India Stress Gauge —
press 0.35, events 0.25, market 0.25, Wikipedia 0.15, weights pre-registered
before computation — detects **2 of 29** episodes at ≥90 within ±3 days.
Hit rate **0.069**. The press channel alone gets **24 of 29**.
`docs/data/stress_gauge.json`, `docs/data/validation.json`

**(c) The index is Anglophone and the data says so out loud.** English
Wikipedia tracks this index more closely than Hindi Wikipedia on **5 of 5
channels**, in *both* levels and day-to-day changes. The gap is
**one-directional** — there is no channel where Hindi leads.
`docs/data/wiki_hindi.json`

**(d) The border channels replicate across forty years.** Built from a
different source, different unit, filters frozen in a signed memo before the
first query ran: pakistan_west **0.893**, china_east **0.848** over the 36
overlapping months. Two other channels failed the same pre-registered test
(0.216, 0.153) and were withheld.
`docs/data/back_extension.json`

**(e) The sector sensitivity null.** 39 cells, seeded-bootstrap CIs,
Benjamini–Hochberg FDR at 10%. **Zero cells survived correction.** With this
episode set, no sector index shows a sensitivity distinguishable from zero
once the search is paid for.
`docs/data/sector_sensitivity.json` → `_meta.multiple_comparisons`

**Your answer:**

>

---

## 4. Which miss or failure made IGRM better? Explain what you changed in your own thinking, not only what changed in the code.

**Candidates from the record, if any of these is the one:**

- **The placebo result nobody advertises.** 115 placebo episodes, **52
  overlap** with real ones — **45.2%**. That is a weak result, it is
  published, and it is the number a hostile referee will find first.
  (`docs/data/validation.json` → `placebo`)
- **The June 2025 gap.** 2025-06-15 to 07-01 is missing and is *unfixable* —
  the outage is upstream. The first investigation "proved" GDELT still had
  the days by probing a window with **zero overlap** with the actual gap.
- **The gauge.** Four sources, pre-registered weights, worse than one source.
- **Blue Star, 1984.** A registered anchor that scored 52.3 because it was
  filed under the India–Pakistan channel and was an internal operation. It
  stays on the list and stays a miss, because dropping it after seeing it
  fail would be choosing the denominator from the answer.

The second half of the question is the part only you can write: what you now
do differently *before* trusting a result.

**Your answer:**

>

---

## 5. The project publishes low precision, late mornings and failed tests. Why expose numbers that make the project look worse?

**Exactly what is exposed, so the answer can be specific:**

- **Precision is UNCALIBRATED and says so.** Your own labels: **16 of the
  100** registration threshold, 4 abstentions. Machine–author agreement
  **0.875 on n=16**, published *with* its n. `calibrated: false`.
  (`docs/data/precision.json`)
- **Placebo overlap 45.2%** — above.
- **The gauge's 6.9%.**
- **The sector null**: 0 of 39 cells.
- **Two back-extension channels withheld** for failing their own test.
- **Every revision to the published series is diffed nightly** and a silent
  one fails the build. (`docs/data/vintages.json`)
- **A nightly blind rebuild** from the public codebook alone —
  **19,830 of 19,830** values exact. (`docs/data/replication.json`)

That last one is the argument, if you want it: the reason anyone should
believe the flattering numbers is that the unflattering ones are on the same
page, computed by the same pipeline, on the same schedule.

**Your answer:**

>

---

# The intellectual claim

## 6. If IGRM does not predict risk, what is it actually useful for at 6 AM?

*Yours entirely. One constraint: nothing in the answer may imply forecast —
that rule is lint-enforced across the site and should hold in the paper too.*

Worth knowing while you answer: the VIX lead-lag says the **market moves
first**. So the 6 AM value is not an early warning about markets. Whatever it
is useful for, it is not that — and saying so is stronger than hedging.

**Your answer:**

>

---

## 7. What does the Hindi Wikipedia result change about the phrase "Indian geopolitical salience"?

**The finding, exactly:** English Wikipedia tracks this index more closely
than Hindi Wikipedia does, on **5 of 5 channels**, in both levels and changes.
**One-directional** — no channel where Hindi leads.

The honest reading already published: *the index is built from an English
corpus and appears to measure English-language attention to India better than
it measures Indian-language attention to India.*

So the phrase has a modifier in it that the name does not carry. Your call
whether the paper renames the construct, footnotes it, or argues the
English-language attention *is* the object of interest for the users who need
it. All three are defensible; they are different papers.

**Your answer:**

>

---

## 8. What is the strongest claim you are willing to make about IGRM today? What claim would be dishonest?

**The strongest claim the evidence currently supports** — stated at full
strength, because you asked for maximum and this one does not need hedging:

> IGRM is a daily, fully public measure of press salience for India whose
> construction is **exactly reproducible from its own published
> documentation** — 19,830 of 19,830 values, rebuilt nightly by code with no
> access to the pipeline — whose every published vintage is diffed for silent
> revision, whose pre-registered episode detection recovers 24 of 29 events at
> ±3 days, and whose two border channels replicate against an independently
> constructed forty-one-year proxy at r = 0.89 and 0.85 under filters frozen
> before the first query ran.

Very few published indices, including well-cited ones, can claim the first
clause at all. That is the sentence to build the paper around.

**Claims that would be dishonest**, given what is on the site today:

- that it predicts, forecasts, or anticipates anything;
- that it measures *risk* rather than *press salience*;
- that its precision is established — it is uncalibrated at n=16 of 100;
- that the placebo test passed — 45.2% overlap is not a pass;
- that fusing sources improved it — it made detection 12× worse;
- that it measures Indian-language attention — 5 of 5 channels say otherwise;
- that the historical series extends the index — different construct, and it
  must never be spliced.

**Your answer:**

>

---

# The end state

## 9. Who should use this first: an academic, policymaker, investor, journalist or business owner? What decision becomes easier for that person?

*Yours. One observation that may sharpen it: the reproducibility result and
the frozen API contract are worth most to whoever needs to* cite *or* rebuild
*the series — which points at academics — while the daily 6 AM cadence points
at desks. Those two audiences want different products, and picking one is a
real strategic decision, not a diplomatic one.*

**Your answer:**

>

---

## 10. In one year, what outcome would make you say IGRM became undeniable?

*Yours. Ambitious version, since you asked for optimistic: the outcome that
would settle it is not traffic — it is somebody you did not contact citing
IGRM in published work, and a second person reproducing the series from the
codebook without emailing you. The machinery for the second one now exists
and is measured nightly.*

**Your answer:**

>

---

# Short founder details

| Field | Answer |
|---|---|
| Exact publication name | |
| Preferred affiliation line | |
| ORCID, if any | |
| Weekly hours available until 1 November | |
| College application deadlines that matter | |
| One person whose analytical standard the paper must withstand | |

**Note on ORCID:** free, ~2 minutes, and it is worth having before the DOI is
minted so the two are linked from the start.

---

## Sources for every number above

| Claim | File |
|---|---|
| 24/29 episode detection, placebo 45.2%, robustness by channel | `docs/data/validation.json` |
| Gauge 2/29, weights, per-source components | `docs/data/stress_gauge.json` |
| English leads Hindi 5/5, one-directional | `docs/data/wiki_hindi.json` |
| 0.893 / 0.848 track; 0.216 / 0.153 withheld | `docs/data/back_extension.json` |
| 0 of 39 cells survive FDR 10% | `docs/data/sector_sensitivity.json` |
| VIX leads attention, lag −8 | `docs/data/priced_risk.json` |
| Precision uncalibrated, 16/100, agreement 0.875 | `docs/data/precision.json` |
| 19,830 / 19,830 blind replication | `docs/data/replication.json` |
| Vintage diffing, silent-revision tripwire | `docs/data/vintages.json` |
