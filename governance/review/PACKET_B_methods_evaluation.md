# Review packet B — methods and evaluation

**Ask:** 3–5 hours. One written verdict. Nothing else.

You are being asked whether this index measures what it claims to measure,
and whether its evaluation could ever show it wrong. The most useful
outcome is a specific reason to disbelieve a published number.

---

## What the index claims

IGRM publishes a daily composite for India, 0–100, built from five
channels (Pakistan/west, China/east, Gulf energy, US trade, shipping).
Each channel is a **trailing percentile of press attention**, computed
from GDELT n-gram and event counts. The composite is the unweighted mean
of the five channel percentiles.

The construct is deliberately narrow, and the narrowness is the claim
worth attacking: **it measures how much the press is talking about a
thing, not how dangerous the thing is.** Attention and risk diverge, and
the index is only honest if it never quietly trades on the confusion.

## The specific questions

Depth on two beats a sweep of all.

1. **Is the percentile construction defensible?** Trailing window,
   minimum observation count, how ragged channel tails are handled, what
   happens when a channel has no data. Is there a specification under
   which today's number would be materially different and equally
   justifiable?

2. **Does the denominator do what it should?** Counts are normalised
   against per-period English article volume. Does that actually remove
   the effect of the corpus growing, or of a single outlet's volume
   changing?

3. **Is the GPR comparison fair?** We publish a comparison against
   Caldara–Iacoviello GPR. Is it constructed so it could fail? Where does
   ours differ, and is the difference explained or excused?

4. **Could the evaluation ever falsify the index?** Forecasts are meant to
   be preregistered with frozen targets, denominators, baselines and
   information cutoffs before outcomes exist, with every attempt retained
   including failures, nulls and abstentions. Look for the escape hatches:
   post-hoc threshold changes, silent denominator changes, a baseline weak
   enough to beat by construction, missing outcomes dropped rather than
   counted.

5. **Does the public presentation overclaim?** Uncertainty bands,
   robustness numbers, the wording around spikes. Would a careful reader
   come away believing something the data does not support?

## What we already know is weak

- Validation against real-world outcomes is thin. We do not have a strong
  claim that the index predicts anything, and we would rather you say so
  plainly than have us imply otherwise.
- Some historical series are frozen behind rights decisions and cannot be
  extended.
- The five channels were chosen by judgment, not by a selection procedure.

## What you get

- The live site, all payloads as public JSON/CSV, and the codebook.
- A frozen commit SHA so your verdict stays true.
- `docs/break.html` — our own standing invitation to break the index,
  with the specific attacks we think are strongest.
- Any raw store you want, on request.

## Deliverable

A written verdict, any format, containing:

- Findings, each with **what specifically would have to be true for the
  published number to be wrong**, and how a reader could check.
- What you examined and what you did not.
- A direct answer to one question: **would you cite this index in your own
  work, and if not, what would have to change?** A no with a reason is
  more useful to us than a yes.
- Whether you are willing to be named. Anonymous is fine.

## What this is not

Not a code or security review — that is packet A. Not an endorsement. We
will publish your findings and our responses, including what we decline to
change and why.

## Terms

Fee or pro-bono, agreed before you start. You keep the right to publish
independently. We will not ask you to soften anything.

**Contact:** Ishan Krishna — ishankrishna9@gmail.com
