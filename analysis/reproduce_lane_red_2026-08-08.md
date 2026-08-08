# The clean-room reproduction cannot pass, by construction

Found 2026-08-08 evening by the commit monitor: `reproduce` is RED on
`c328278` (#8) and `2da9bb7` (#9). Reproduced locally in a fresh clone
at the same tip. Not fixed here -- both files that could carry the fix
(`src/run_daily.py`, `scripts/reproduce.sh`) are in the other resident
agent's working tree, and its most recent commit was an attempt at this
same lane.

## Root cause

`bash scripts/reproduce.sh --use-cache` exports `IGRM_OFFLINE=1` and
runs `python -m src.run_daily`. At stage `[2/5] Markets` it raises:

```
src.fetch_markets.OfflineMarketDataUnavailable: IGRM_OFFLINE is set but
prices.csv/derived_returns.csv are absent; refusing a live market fetch
```

The guard is correct and is doing exactly its job. The inputs it wants
are **gitignored** (`.gitignore:3-4`), so a clean clone never has them
and never can: the market cache is third-party price data the project
does not redistribute. A fresh-clone offline reproduction therefore
cannot complete the market lane under any circumstances.

Verified: `git cat-file -e origin/main:data/raw/prices.csv` and
`derived_returns.csv` both absent at every commit; both listed in
`.gitignore`.

## Why the lane only started failing now

The guard landed 2026-08-07 (`631ad61`, the other agent's fail-closed
fix, landed here with its test). Before it, an offline run with an
absent cache fetched live or silently produced nothing. The lane did
not turn red because reproduction broke; it turned red because a
silent hole was closed and the reproduction script had been passing
through it.

## The shape of the fix

`scripts/reproduce.sh` already carries the right pattern in its own
comments: syndication, wiki_hindi and the fetch lanes are named as
DELIBERATELY out of scope, "verified by their own tests, not by this
diff, and adding them would make the monthly reproduce run fail for
reasons that are not reproducibility". The market lane belongs in that
list for the same reason, and its exclusion should be **reported in the
coverage number**, not silently skipped -- a replicator must be told
which lanes the proof did not cover and why.

What must NOT change: the guard. Making `fetch_markets` fall back to a
live fetch, or returning empty data under `IGRM_OFFLINE`, restores the
hole that closing produced this red.

## Urgency

The lane runs monthly (1st, 08:07 IST) **and on every push to main**,
so the red is continuously visible on every commit until fixed. It
gates nothing else: the 06:00 contract, CI and the daily lane are
unaffected.
