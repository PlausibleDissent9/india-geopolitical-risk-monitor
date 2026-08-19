# Replication kit

For an external reproducer: what to run, what you should see, and what
each outcome proves. The public reconstruction needs no credentials or
non-public data. Re-executing every upstream lane is a separate task with
different rights and vintage constraints, stated below rather than hidden.

## Setup

```
git clone https://github.com/PlausibleDissent9/india-geopolitical-risk-monitor
cd india-geopolitical-risk-monitor
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Python 3.11+ (the interpreter CI tests; 3.9 measurably fails). The optional `ANTHROPIC_API_KEY` is
NOT part of replication. It may populate the separate display-only aptness
labels, which never change a score. The machine-written daily-brief experiment
is withdrawn and cannot call a model or write prose, with or without a key.

## Path 0 — check the index against its own documentation (~3 seconds)

```
.venv/bin/python -m src.blind_replicator --check
```

Start here. This is the fastest and, for most readers, the most
informative check on the site, and it does not touch the raw store at
all.

`src/blind_replicator.py` rebuilds the entire published series from two
public files — the transform as stated in `docs/codebook.html`, applied
to `docs/data/shares.csv` — and diffs the result against
`docs/data/history.csv`. It is **forbidden from importing the
pipeline**, and `tests/test_blind_replicator.py` parses its imports to
enforce that. A replicator that can see `src/scores.py` reproduces it by
construction and measures nothing.

**Expected result:**

```
[blind_replicator] best: weak / calendar -- N/N values agree (100.0000%)
```

`N` advances with the published series. The command also requires zero
missing reconstructed cells; 100% agreement over a smaller overlap is a
failure, not a pass.

**What it proves:** the published index is exactly reproducible from its
own published documentation, by code with no access to the code that
produced it. If you disagree with the number, either the codebook does
not say enough for a stranger to reproduce it, or the pipeline does
something the codebook does not describe — both are defects, and the
tool reports which conventions were in play so you can say which.

It also prints how every *other* reading of the codebook scored. Those
numbers are the argument for why the conventions are stated as precisely
as they are:

| reading | reproduces |
|---|---|
| at-or-below ties, calendar window | **100.00%** |
| at-or-below, observation window | 65.28% |
| midrank ties | 11.6–14.9% |
| strictly-below ties | 0.00% |

Same inputs, same paragraph, everything from exact to nothing. Three
sentences were added to the codebook's Conventions list on 2026-08-07
because this tool found them missing.

This check runs every night in `daily.yml` and is **fail-loud**: it
requires an exact match, so a future methodology change breaks the lane
until the codebook is updated to match. That is deliberate.

## Path 1 — clean-room public reconstruction (~2 minutes)

```
scripts/reproduce.sh --public
```

Clones the checkout into a temporary directory, creates a fresh pinned
environment, runs the non-live test suite with source access refused, and executes the independent
public reconstruction above. It does not copy `data/raw`, fetch a source,
or read the production score implementation.

**What it proves:** every published daily channel and composite score cell
can be reconstructed exactly from the public codebook and shares file,
with complete denominator coverage, in a clean checkout. This is the
rights-safe guarantee enforced by the `reproduce` workflow.

**What it does not prove:** it does not recreate acquisition, receipts,
event studies, market-derived outputs, or every analytical payload. Those
claims require their own input-complete proofs; this command never presents
a partial rebuild as full-pipeline reproduction.

## Path 2 — owner cache-dependent pipeline audit

```
scripts/reproduce.sh --use-cache
```

This mode is for an authorized checkout holding the exact source caches.
It remains strictly offline and fails closed if any required cache is
absent. In particular, `data/raw/prices.csv` and
`data/raw/derived_returns.csv` are not redistributed in Git, so a public
clone cannot use this mode to recreate market-dependent outputs. A passing
owner run is an internal computation audit, not an independently accessible
public reproduction receipt. It compares complete arrays and every regenerated
field; there is no ignored tail or market-tolerance escape hatch.

## Path 3 — new-vintage source re-execution

```
scripts/reproduce.sh --live-source
```

This refetches available upstream sources and therefore creates a new
source vintage. It can test acquisition and transformation behavior, but
it cannot prove that the exact historical bytes behind the committed
vintage were recovered. GDELT revisions, source outages, licensing limits,
and market-bar revisions are reported as such; they are never hidden by
calling a tolerance band “exact reproduction.”

## Independent checks that need no rebuild

```
.venv/bin/python -m pytest -q       # includes:
```

- `src/audit.py` (run in CI daily): two independent derivations of the
  day's scores must agree — a fail here blocks publication entirely.
- `tests/test_published_promises.py`: every statistic a page claims
  must exist in the payload it cites.
- `tests/test_api_contract.py`: every served payload appears in
  `docs/data/api_contract.json` and every frozen field is present.

## Data provenance

| Source | Role | Access |
|---|---|---|
| GDELT DOC API | daily volumes, artlist receipts lane | public, rate-limited |
| GDELT Web NGrams v5 | corpus scan, splice bridge, receipts | public GCS objects |
| UCDP GED (bulk CSV) | conflict-event context (never in any score) | public download |
| IMF PortWatch | chokepoint transits | public ArcGIS |
| Yahoo Finance | market outcomes for the event study | fetched, not redistributed |

## Reporting a discrepancy

Open a GitHub issue with the diff line(s) and your run log. A
confirmed discrepancy gets a corrections-ledger entry
(`docs/corrections.md`) naming the cause — that ledger is append-only
and public, and reproducers finding real errors is exactly what it is
for.
