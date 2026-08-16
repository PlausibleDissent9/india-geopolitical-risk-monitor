# Review packet A — code, security and release

**Ask:** 3–5 hours. One written verdict. Nothing else.

You are being asked to attack a publishing system, not to admire it. The
useful outcome of this review is a list of things that are wrong. A review
that finds nothing is a review we cannot use, because the point is to know
before an outside reader does.

---

## What the system is

IGRM publishes a daily India geopolitical-risk index at https://igrm.in
from public data (chiefly the GDELT Project). It is built so that it
refuses rather than guesses: when a source is missing, a right is
unclear, or two independent computations of the same number disagree, the
system publishes a value-free refusal instead of a value.

That refusal behaviour is the thing worth attacking. If you can make it
publish a number it should not have published, or make it claim freshness
or authority it does not have, that is the finding.

## What you are reviewing

An exact commit, given to you as a SHA. Not "the repository" — one frozen
candidate, so your verdict stays true after we keep working.

Roughly: ~30k lines of Python, a set of publishing shell scripts, a
governance plane of JSON registries and Ed25519-signed rights decisions,
and GitHub Actions workflows.

## The specific questions

You do not need to cover all of these. Depth on two beats a sweep of all.

1. **Can the publisher be made to publish without rights?** The rights
   plane is deny-by-default: a source is unusable until a human signs a
   decision artifact, and the publisher pins each signature digest in
   code. Can that be bypassed, widened, or satisfied with something other
   than a genuine signature?

2. **Can a refusal be turned into a value?** Find a path where a
   value-free unavailable envelope acquires a number, a date, a freshness
   claim, or an implication of capability.

3. **Is the exact candidate really the thing verified?** The publisher is
   supposed to capture candidate, tree and parent once and verify those
   exact bytes before and after its checks. Look for places it re-derives
   them from ambient git state, or verifies a worktree rather than the
   pushed candidate.

4. **Do credentials stay at the transport boundary?** They are supposed
   never to reach mutable candidate code. Check the shell publishers and
   the environment they build.

5. **Are the gates real?** We have found several of our own gates that
   could not fail — a test that read the constant it was testing, a
   verification whose exit code came from a pipe. Assume more exist.

## What we already know is wrong

Told to you up front, because a review that spends its hours rediscovering
these is wasted:

- `tests/test_freshness.py::test_the_real_site_has_no_stale_or_undatable_payloads`
  reads the live site, so it fails whenever publishing is behind. It is
  excluded from the publish gate deliberately (a stale site otherwise
  refuses the pushes that would refresh it).
- A composition of ours shipped a stale `PINNED_RIGHTS_SHA256`, and the
  authority plane then answered `source_authority_invalid` for 23 of 28
  endpoints — a confident wrong answer rather than an error.
  `scripts/audit_pins.py` was written in response and currently reports
  one unresolved finding.
- Coverage is ~73%.

## Deliverable

A written verdict, any format, containing:

- Findings, each with a **concrete path to the bad outcome** — inputs or
  state, and what gets published or accepted that should not be.
  Severity in your own words.
- What you actually examined, and what you did not. The limits matter as
  much as the findings; we would rather publish "the release path was
  reviewed and the India methodology was not" than imply whole coverage.
- Whether you are willing to be named. Anonymous is fine and does not
  reduce the value.

## What this is not

Not an endorsement of the index's conclusions or its methodology — that is
packet B. Not a certification. We will publish your findings and our
remediations, including anything we choose not to fix and why.

## Terms

Fee or pro-bono, agreed before you start. You keep the right to publish
your own findings independently. We will not ask you to soften anything.

**Contact:** Ishan Krishna — ishankrishna9@gmail.com
