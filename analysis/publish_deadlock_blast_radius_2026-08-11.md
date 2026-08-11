# How far the publish deadlock reached

Measured 2026-08-11 from the Actions API. Records what the run history
supports and, as carefully, what it does not.

## The mechanism

`publish_push.sh` gated every candidate with `gate.sh --committed`, which runs
what CI runs — including the tests marked `live`, which fetch igrm.in and
assert about the payloads the site is ALREADY SERVING. Thirteen lanes call
that script. So once any watched payload went stale, every one of those lanes
was refused at its commit step, including the lanes whose job is to refresh
the stale payloads.

## The causal ordering the run history supports

`daily.yml` broke FIRST, and for a different reason than the others: its own
first step, "Enforce dictionary rules (ex-ante rule)", ran a bare `pytest -q`
with the live suite included and no continue-on-error. It produces
comparators, episode_terms, receipts, receipts_archive, spike_breadth and
validation — so when it died, those six went stale and stayed stale.

    daily.yml last success   2026-08-08 02:44   first failure  2026-08-08 15:51
    the six payloads go stale and cannot be refreshed
    every other publisher then starts failing at its COMMIT step:
      multilingual-backfill  last success 2026-08-09 22:03 -> fails 2026-08-10 22:19
      permanence             last success 2026-08-10 17:11 -> fails 2026-08-11 03:22
      morning                last success 2026-08-09 15:05 -> fails 2026-08-11 01:22
      receipts-extended      never succeeded; both runs died at its publish step

Failing step names, read from the API rather than inferred:

    morning.yml               Commit and push
    daily.yml                 Commit data
    receipts-extended.yml     Publish complete view or bank incomplete checkpoint
    notes.yml                 Commit
    permanence.yml            Commit the permanence record
    events-backfill.yml       Commit progress
    multilingual-backfill.yml A batch that landed nothing is a failure

Every one of those steps invokes `publish_push.sh`.

## What this does NOT establish

- **events-backfill has been failing since 2026-08-02**, well before the six
  payloads went stale, so its failure predates the deadlock and this fix
  should not be credited with resolving it.

  INVESTIGATED AFTERWARDS, and the first sentence above needs qualifying. The
  lane is a self-chaining backfill fired by a trigger file, not a nightly job:
  it last ran on 2026-08-02 (two runs in the same minute, racing, both dying
  at "Commit progress" in 2 and 5 minutes -- far too fast to be the gate) and
  has been dormant since. Dormant is not the same as broken, and it is costing
  nothing.
  What matters is whether it left a hole, and it did not. `_missing_days()`
  reports THREE incomplete days, 2026-08-07 to 2026-08-09 -- recent days, not
  a gap in history, so the historical backfill completed regardless of that
  failure. Those three days are filled by `daily.yml`, which runs
  `fetch_events --update 5` at line 107 and has been dying at its FIRST step
  since 2026-08-08, never reaching it.
  So the three gaps are a SYMPTOM of the same root cause, not a separate
  defect, and `--update 5` will close them on the first healthy daily run. No
  fix is needed here, and calling this "a separate defect" without looking was
  a claim I had not earned.
- **notes.yml is not currently failing** (last success 2026-08-07, nothing red
  after it). It is listed above only because it shares the push path.
- **drift.yml and bq-gfg-probe.yml fail at their own compute steps**, not at a
  publish step. Different causes, untouched by this.
- The CI step LOGS were not read — fetching them needs an authenticated token
  this environment does not have. The evidence is: the failing step names, the
  shared push path they all invoke, the temporal ordering above, and the live
  freshness assertion reproduced locally against origin/main, which fails
  naming exactly the six payloads. That is strong and consistent; it is not the
  same as having read the log line.

## Consequence

The receipts lane is task #49 in the founder's list — "burned 60 min nightly
and banked nothing". The run history says that is not a staging bug: run #2
worked for 95 minutes and was then REFUSED PERMISSION TO BANK IT at the
publish step. A lane doing its work and being denied the right to record it
looks identical, from the outside, to a lane that did nothing.
