# Daily-brief factual-grounding incident — 2026-08-08

Status: **withdrawn; do not cite or reuse generated prose**

## Scope of public exposure

The experiment wrote ten committed versions of `docs/data/daily_brief.json`
covering five completed news days, 2026-08-03 through 2026-08-07:

| News day | Commits containing generated prose |
|---|---|
| 2026-08-03 | `eb5bb33`, `2a7c8f7` |
| 2026-08-04 | `eec9aec`, `49a2adc` |
| 2026-08-05 | `0e0f60c`, `3ce0c41` |
| 2026-08-06 | `e129122`, `8d02cab`, `88b9cbc` |
| 2026-08-07 | `eaad1e5` |

Git preserves those bytes as incident evidence. None of the generated prose is
an IGRM result.

## Confirmed failures

1. **Unsupported stress-gauge claims.** Nine of the ten committed versions
   stated a stress-gauge value. `src.daily_brief.build_context()` supplied only
   `latest.json` scores and `receipts.json` display evidence; it never read or
   supplied `stress_gauge.json`. The values therefore had no machine-readable
   provenance in the model input.
2. **Display selection presented as source-pool quality.** The context exposed
   `spike_quality_tier12_share`, then calculated on a tier-first sorted and
   capped displayed list. Generated prose described it as a quality or
   concentration property of the day's source pool. The denominator was
   presentation-selected and could not support that interpretation.
3. **Displayed representatives presented as the score denominator.** The
   context called `len(receipts.channels[*].articles)` `n_articles`. That array
   had already been URL-deduplicated, grouped by a title key and capped for
   display; it was not the number of documents or group contributions used by
   the estimator.
4. **Cross-date evidence join.** Commit `eaad1e5` summarized scores dated
   2026-08-07 while its loaded receipts payload was dated 2026-08-06. The input
   included both dates but did not require equality, and the prose used the
   older receipt counts and headlines as evidence for the newer scores.

## Root cause

JSON-schema output constrained the shape of the response, not the truth of its
contents. The only post-generation control was a regular expression rejecting
some predictive phrases. There was no claim ledger, numeric-source pointer,
entity whitelist, denominator/type system, date-join assertion, or
sentence-level grounding verifier. Labeling prose “machine-written” did not
make unsupported factual claims acceptable.

## Containment

- `src.daily_brief.main()` has no generation, network or write branch.
- The daily workflow invokes the module without a model API key only as a
  withdrawal assertion.
- `docs/data/daily_brief.json` is a null tombstone with the frozen v2 top-level
  fields and explicit withdrawal metadata.
- The API contract marks the endpoint deprecated through at least 2026-11-06.
- Freshness treats the tombstone as intentionally static, and public status
  names the lane as withdrawn.

## Minimum conditions for any successor

A future brief must be a new, versioned design. Before publication it must:

1. Require exact equality among the score day, receipt day and every other
   evidence day.
2. Build a typed fact table whose values carry payload paths, units,
   denominators and allowed renderings.
3. Generate from fact identifiers or deterministic templates, not an
   unrestricted prose context.
4. Reject every number and named entity that cannot be mapped back to an
   allowed fact identifier.
5. Keep display counts, retrieval-pool counts, scored-document counts and
   score-contribution counts as different types that cannot be substituted.
6. Pass adversarial mutation tests and independent human review before the
   publication flag can be enabled.

Until all six conditions are implemented and reviewed, no generated daily
prose is authorized.
