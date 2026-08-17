# Event-coding methodology — decision memo

Drafted 2026-08-17 for the methods reviewer and the founder's signature.
Gates the 12 points currently unreachable because the canonical graph
emits `event: 0` and `exposure_edge: 0`.

---

## The question is smaller than it looked

The canonical release emits 15 `evidence_item`s, 15 `entity`s and 1
`universe_release`, and zero events. The stated reason
(`src/universe_emitter.py`) is that the universe's inclusion rule is
*mechanical* — a domain either appeared in an available channel or it did
not — whereas "classifying a headline into an event class needs a
registered coding rule nobody has written."

That framing is now out of date in one important respect:

**IGRM already uses a published event-coding scheme, daily, in
production.** `src/fetch_events.py` consumes the GDELT Events V1 export
and codes on CAMEO: material conflict is `QuadClass` 3/4, protest is root
code 14, cooperation is `QuadClass` 1/2, and it retains
`goldstein_mean`. `data/raw/events_dyads.csv` holds 118,631 rows on that
basis, back to 2017.

So this is not "choose a taxonomy from nothing." It is closer to
**register the taxonomy already in use, and decide at what granularity to
emit it.**

Second relevant fact: `_download()` fetches the whole daily export zip,
which contains *individual* events. The pipeline aggregates them to daily
counts and discards the rest. The discrete events are already arriving
every day and being thrown away — emitting them needs a retention
decision, not a new source or a new provider.

Third: `data/raw/ucdp_events.csv` already exists. UCDP GED is
human-coded, which makes it the natural validity check on CAMEO's machine
coding rather than a competing input.

---

## Options

### A — Register CAMEO, emit aggregate event observations
Emit `event` objects at the granularity already stored: daily × partner
(or daily × admin-1) counts by CAMEO class, carrying `goldstein_mean`.

- **Acquisition cost:** zero. The data is in the repo now.
- **Fidelity:** an "event" is then an aggregate observation, not a
  discrete occurrence. Honest, but a reviewer may object that it
  stretches the object name.
- **Time:** days.

### B — Register CAMEO, retain and emit discrete events  ← recommended
Keep the individual India-relevant rows from the export already
downloaded, and emit one `event` per coded occurrence with its CAMEO
code, actors, Goldstein score and source count.

- **Acquisition cost:** zero — same file, currently discarded.
- **Storage cost:** the India-filtered slice, not the global export.
  Needs measuring before committing.
- **Fidelity:** matches what the canonical schema means by `event`, and
  makes `exposure_edge` derivable (actor → actor, actor → chokepoint).
- **Time:** ~1–2 weeks including tests and a registered rule document.

### C — Cross-validate against UCDP GED  ← recommended alongside B
Use the already-fetched UCDP data as an independent, human-coded check
on the CAMEO series rather than as a second input.

- **Cost:** zero acquisition; UCDP rights decision is drafted and pending
  signature.
- **Why it matters:** it converts "we used CAMEO" into "we used CAMEO and
  measured where it disagrees with human coding," which is the difference
  between a defensible methods section and an assertion.

### D — Add ACLED
A third event source, high quality, India coverage.

- **Cost:** free for academic registration; commercial licensing paid.
- **Verdict: not yet.** It is already scoped in this repo as
  `acled_conflict_index` in the benchmark contract — i.e. something to
  compare *against*. Adding it as an input before B and C are done buys
  nothing that B and C do not, and adds a dependency and a rights review.

### E — Decline, and publish the absence
Register a decision that IGRM does not emit events, and state why.

- This project already treats a well-evidenced negative as a product, so
  this is a real option rather than a failure. But it forfeits 12 points
  when the input data is already in hand, which makes it hard to justify.

---

## Recommendation

**B + C.** Register CAMEO as the coding rule — citing Schrodt's published
codebook — retain the discrete India-relevant events already being
downloaded, and validate the series against UCDP GED.

Zero new sources. Zero new acquisition cost. Two rights decisions already
drafted and awaiting signature (`gdelt_events_v1`, `ucdp_ged`).

## What a reviewer must rule on, not me

1. **Is CAMEO's machine coding fit for this construct?** Its known
   weaknesses — wire-copy duplication inflating counts, actor
   misattribution, geocoding error — bear directly on an India index.
   This is the substantive call and it is a methods judgement.
2. **Granularity:** discrete events (B) or aggregate observations (A).
3. **Whether `exposure_edge` may be derived** from CAMEO actor pairs, or
   whether that requires its own registered rule.
4. **Disagreement threshold with UCDP** beyond which the CAMEO series is
   reported as unreliable rather than merely noisy.

## What must not happen

The coding rule must be registered *before* events are emitted, and
frozen with its implementation digest, exactly as
`universe_emitter.py` does for the membership rule. Emitting events
first and describing the rule afterwards would make the rule a
post-hoc description of whatever the code did — which is the failure this
project's registration discipline exists to prevent.
