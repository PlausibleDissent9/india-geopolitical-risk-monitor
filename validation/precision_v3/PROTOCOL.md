# External precision audit v3 — prospective source-frame protocol

Status: **SOURCE-FRAME COLLECTION ONLY — NO SAMPLE, LABELS OR RESULT**

Effective for completed UTC score days beginning 2026-08-08. The fixed source
collection ends 2026-11-05. This protocol repairs the two defects documented
in `validation/blind_audit_500/V2_INVALID.md`; it does not revive v2 and does
not license a precision, validation or superiority claim.

The 90 calendar days are split prospectively into two disjoint cohorts:

| Cohort | Fixed source days | Role | Earliest coding date |
|---|---|---|---|
| v3a | 2026-08-08 through 2026-09-18, 42 days | initial production-frame audit | 2026-09-19 |
| v3b | 2026-09-19 through 2026-11-05, 48 days | out-of-time holdout replication | 2026-11-06 |

Both windows, selection seeds, sample sizes, code, rubric, source regime,
missingness rule and pass criteria are frozen in `registration.json` before
the first v3 source day is available. V3a gives the ten-week programme a
bounded external result without deleting the longer design. V3b remains a
genuinely future, non-overlapping replication. A v3a result can never be
described as the v3b result or as 90-day evidence.

## Why v3 begins at score construction

V2 reconstructed its source frame later from receipt caches. One source day
contained 39 snapshots while the published score used 48, and the sampler
unioned documents across query groups even though production adds each group's
share. A reproducible sample from the wrong population is still the wrong
study.

For v3, `src.fetch_ngrams` writes the following into the production day cache
on the same pass that computes the score:

- every located, loaded and missing sampling timestamp;
- the exact matcher specification and its SHA-256;
- the dictionary and production-matcher SHA-256 values;
- each group-qualified document key, the per-document India anchor set and
  the associated date, title and URL metadata; and
- the aggregate denominator and group shares that enter score construction.

`src.precision_frame_v3` independently applies the embedded anchor rules and
requires each contribution count to reconstruct its published six-decimal
group share exactly. It refuses partial days, fewer than 48 loaded samples,
missing metadata, group drift, hash drift or a revised prior attestation. Each
accepted day produces a compact append-only attestation in
`data/raw/precision_v3_days/` before any coder sees any row.

An ineligible production day is recorded instead as
`FRAME_FAILURE_NO_LABELS`, with the source-cache hash and observed depth when
available. It invalidates that cohort's sample but remains in the consecutive
calendar chain, so the failure cannot be hidden and every later calendar day
can still be attested. A regime change ends confirmatory eligibility under this
registration: later days remain recorded as failures rather than silently
starting a new regime or restoring either cohort. A failure record is immutable;
a repaired or replaced source file may not retroactively turn it into an eligible
day.

## Frozen source populations

Every UTC score day from 2026-08-08 through 2026-11-05 belongs to exactly one
named cohort. No day may be selected, removed or replaced because of its score,
event status, source mix, provisional precision, another index or coder
availability. A missing or ineligible day makes that cohort incomplete and
must be reported; it is not an exclusion. V3b remains source-collectable even
after v3a labels exist because its documents are future, its seed is already
frozen and the production matcher/dictionary regime cannot change silently.

The primary sampling unit is one **group-qualified contribution instance**:

```text
(completed score day, channel, query group, production document key)
```

If one document contributes to two production query groups, it enters the
primary population twice. That multiplicity is intentional: it represents the
quantity production actually adds to the channel numerator. The attestation
also reports distinct document keys and the multi-group excess so a later
unique-document estimand can be named separately. It may never be substituted
for the primary contribution estimand.

The production matcher specification, dictionary and matcher-code hashes must
remain one regime across the source window. A change ends the confirmatory
frame; it cannot be silently pooled into the existing study.

## Sampling and coding plan after each cohort closes

No cohort sample may be drawn until every calendar-day attestation in that
cohort, every source-cache hash and the clean-room reconstruction agree. The
registration already freezes the selection seeds and algorithm, so nobody can
search seeds after seeing the frame. `sha256_rank_v1` gives every contribution
in a channel the same inclusion probability; the first 500 ranks are selected,
or the channel is a census when its frame contains fewer than 500.

The resulting package freezes:

1. the exact ordered source-day manifest, frame digest and per-channel counts;
2. the deterministic contribution-instance sample and inclusion probability;
3. the same evidence in two separately hash-ordered coder sheets;
4. a distinct, unscored pre-window pilot sheet for rubric training;
5. a private coordinator key binding each audit ID to its source contribution;
6. a manifest hash for every file before either coder receives a row; and
7. fixed coder compensation independent of agreement, precision or pass/fail.

The builder also emits a rights-safe public freeze receipt containing only the
package, frame, sample and sheet hashes. That exact receipt must be committed
to the public repository, with its commit identifier recorded, before either
coder receives a package file. The private packet's self-manifest is not by
itself evidence of pre-label timing.

Scoring verifies the exact receipt bytes against that reachable Git commit.
Each coder also returns a separate private attestation binding an opaque,
distinct coder ID to the assigned sheet hash, receipt hash, anchor commit and
ordered access/completion timestamps. The attestation affirms independence,
outcome-independent compensation, pilot-first ordering, no collaboration, no
LLM/classifier labelling and no viewing of IGRM outputs or prior labels while
scoring. The result publishes hashes of both submitted sheets and attestations;
it does not pretend these procedural declarations are cryptographic proof of
human independence.

The target channel is visible because the rubric is channel-specific. Query
group, matched phrase, contribution rank, source tier, IGRM score, machine
label and every prior label remain hidden. Coders work independently after the
pilot. A third masked reviewer may examine disagreements only after both
primary files are locked; adjudication is a secondary diagnostic and never
replaces either coder's primary estimate.

Repeated evidence caused by real production multiplicity remains repeated in
the primary estimate. Reliability is calculated once per unique evidence
identity. A coder who gives contradictory firm labels to repeated evidence
triggers a published repeat-conflict diagnostic and makes reliability
inconclusive rather than being silently reconciled.

## Registered interpretation boundaries

The primary estimand is each coder's ON share for production group
contributions in the named fixed cohort, separately for each channel. It is
contribution-weighted across that cohort. It is not typical-day precision,
historical precision, story-level precision, population recall, event accuracy,
risk accuracy, causal validity or forecasting performance.

The prospective gate remains a diagnostic threshold, not proof of validity.
For every coder and channel it requires at least 400 firm labels, a Wilson 95%
lower bound of at least 0.80 among firm labels, and an exact finite-population
95% lower bound of at least 0.80 when every ABSTAIN is conservatively treated
as OFF. The last condition prevents inaccessible evidence from mechanically
inflating a pass.

Inter-coder reliability requires at least 400 unique-evidence firm overlaps
per channel, no within-coder repeat conflict, raw agreement at least 0.90 and
Gwet's AC1 at least 0.70. Constant-label overlap is inconclusive, not an
automatic pass. All ten coder/channel gates and all five reliability gates
must pass conjunctively. Abstentions, access status, disagreements, repeated
evidence, failures and deviations publish regardless of direction.

Recall remains a separate independently sampled study. No comparison with CI,
AI-GPR or another index is licensed unless both systems are evaluated on one
predeclared common corpus with construct differences reported and the separate
recall, reproducibility and comparison registrations completed.

## Current claim and rights boundary

The only claim created during the collection window is: **an eligible source
day was captured prospectively and its exact group-contribution counts
reproduce the production shares.** An attestation is not a precision estimate.

The private coder packet may contain third-party titles and links for audit
use. It is not a public-data licence. Public results must be separately
rights-reviewed and may disclose hashes, dates, domains, counts and labels
without redistributing text that the project has no right to relicense.
