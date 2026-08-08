# External precision audit v3 — prospective source-frame protocol

Status: **SOURCE-FRAME COLLECTION ONLY — NO SAMPLE, LABELS OR RESULT**

Effective for completed UTC score days beginning 2026-08-08. The fixed source
window ends 2026-11-05. This protocol repairs the two defects documented in
`validation/blind_audit_500/V2_INVALID.md`; it does not revive v2 and does not
license a precision, validation or superiority claim.

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

## Frozen source population

Every complete UTC score day from 2026-08-08 through 2026-11-05 is in scope.
No day may be selected, removed or replaced because of its score, event status,
source mix, provisional precision, another index or coder availability. A
missing or ineligible day is a frame failure and must be reported; it is not an
exclusion.

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

## Sampling and coding plan after the window closes

No sample may be drawn until all 90 day attestations, source-cache hashes and a
clean-room verifier agree. At that point a separate, timestamped registration
must freeze:

1. the exact Git commit and ordered source-day manifest;
2. a public cryptographic seed committed before any coder receives a row;
3. simple random sampling without replacement of up to 500 contribution
   instances per channel (a census if fewer exist);
4. two independent external coders receiving the same evidence in separately
   frozen random orders, with channel-specific rubric but no query group,
   matched phrase, score, tier, stratum or prior label;
5. coder compensation fixed before coding and independent of agreement or
   pass/fail outcomes; and
6. immutable coder packets, coordinator key, scoring code and output schema.

Repeated evidence caused by real production multiplicity remains repeated in
the primary estimate. Reliability is calculated once per unique evidence
identity, and contradictory within-coder repeat labels are published as a
diagnostic rather than silently resolved.

## Registered interpretation boundaries

The primary estimand is each coder's matched-item precision for production
group contributions in this 90-day regime, separately for each channel. It is
contribution-weighted across the fixed window. It is not typical-day precision,
historical precision, story-level precision, population recall, event accuracy,
risk accuracy, causal validity or forecasting performance.

The existing prospective gate remains a diagnostic threshold, not proof of
validity: at least 400 firm labels per coder and channel, with a 95% lower
confidence bound of at least 0.80. Inter-coder reliability requires at least
400 unique-evidence firm overlaps, raw agreement at least 0.90 and Gwet's AC1
at least 0.70. Abstentions, missing evidence, disagreements, repeated-evidence
conflicts and every channel failure publish.

Recall remains a separate independently sampled study. No comparison with CI,
AI-GPR or another index is licensed unless both systems are evaluated on one
predeclared common corpus with construct differences reported and the separate
recall, reproducibility and comparison registrations completed.

## Current claim

The only claim created during the collection window is: **an eligible source
day was captured prospectively and its exact group-contribution counts
reproduce the production shares.** An attestation is not a precision estimate.
