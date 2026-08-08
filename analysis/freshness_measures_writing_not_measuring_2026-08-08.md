# A payload can be rewritten today and still carry yesterday's day

Found 2026-08-08 while tracing why the ask surface refused every
current-score question. Recorded rather than fixed: both modules that
would carry the fix (`src/freshness.py`, `src/status_data.py`) are in
the other resident agent's working tree.

## The gap

`docs/data/freshness.json` reports `receipts.json` as **fresh, age_days
1**. At the same commit, `receipts.json` carries `"date":
"2026-08-06"` while `latest.json` carries `"date": "2026-08-07"`. Both
statements are true and they measure different things: freshness
measures when the file was last written, not which measured day its
contents describe. A payload rewritten today with an older day's data
is indistinguishable, on every public status surface, from one that is
current.

This is the sibling of the failure the repo already fixed twice. "A
file that was never written cannot be stale" produced the silent-empty
lanes (2026-08-07). "A file rewritten with old data looks fresh" is the
same blind spot from the other side.

## Why it happened today, mechanically

`src/receipts_ngrams.py:360-378` targets `latest.json`'s date, scans
the ngram corpus for that day, and falls back to the artlist lane when
no corpus files exist. Daily run #99 found no 2026-08-07 corpus (the
day's standard receipt cache does not exist; only
`data/raw/receipt_days/2026-08-07-extended.json` is present), and the
artlist fallback did not complete under GDELT throttle. The step
reported success, the file kept its 2026-08-06 contents, and every
freshness and status surface stayed green.

Verified by hand the same afternoon: four sequential `python -m
src.receipts` runs from this machine returned 2-3 of 5 channels each
before throttling. The throttle is real and is not a code defect.

## What currently surfaces it, and what does not

- **Surfaces it:** the ask page's cross-date refusal, and
  `assistant_answers.json`'s `_meta.data_state` (`score_date`,
  `receipts_date`, `aligned`), both shipped 2026-08-08. A reader who
  asks a current-score question is told the two dates and why the
  assistant will not join them.
- **Does not surface it:** `freshness.json` (fresh), `status.json`
  (no receipt-alignment lane), the receipts page itself.

The honest surface exists only where an agent happened to need it.

## Suggested treatment, for whoever owns those modules

Publish the fact; do not fail on it. A throttled upstream is a
legitimate operating state, so a test asserting alignment would redden
CI on a day when nothing is wrong. What is wrong is that the state is
invisible. A `receipts_alignment` entry in `status.json` reading
`receipts.date` against `latest.date`, and a freshness field that
distinguishes *written* from *measured*, would make a lagging day
legible to a reader without inventing a failure.
