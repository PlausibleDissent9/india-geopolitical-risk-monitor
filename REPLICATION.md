# Replication kit

For an external reproducer: what to run, what you should see, and what
each outcome proves. No credentials are needed anywhere in this
procedure; every data source is public.

## Setup

```
git clone https://github.com/PlausibleDissent9/india-geopolitical-risk-monitor
cd india-geopolitical-risk-monitor
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Python 3.9+ works; CI runs 3.11. The optional `ANTHROPIC_API_KEY` is
NOT part of replication. It may populate the separate display-only aptness
labels, which never change a score. The machine-written daily-brief experiment
is withdrawn and cannot call a model or write prose, with or without a key.

## Path 0 — check the index against its own documentation (~3 seconds)

```
.venv/bin/python -m src.blind_replicator
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
[blind_replicator] best: weak / calendar -- 19830/19830 values agree (100.0000%)
```

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

## Path 1 — cached verification (~5 minutes)

```
scripts/reproduce.sh --use-cache
```

Clones your checkout into a temp dir, copies the committed raw store,
sets `IGRM_OFFLINE=1` (all acquisition refused — network and chunk
cache alike; the committed store is the only data source), reruns the
full pipeline, and diffs every `docs/data/*.json` against the
committed versions.

**What it proves:** every published number is a deterministic function
of the committed raw data. The pipeline is fully deterministic —
rebuilding twice produces byte-identical output (bootstraps are
seeded).

**Expected result:** exact match at tolerance 1e-6, with two
documented exceptions:

- `event_study.json` / `priced_risk.json` compare within ±0.06. Their
  market inputs come from Yahoo Finance, which we do not redistribute
  (license); your fetch vintage differs from CI's by recent-bar
  revisions, which moves seeded-bootstrap fields by resampling-noise
  scale. Per-cell episode counts (`.n`) may differ by one as the
  newest episode's market windows mature.
- Run the check against a **daily data commit** (the ones titled
  `data: update YYYY-MM-DD` or `data: final ...`), where store and
  outputs were committed as a pair. Mid-day working commits between
  daily runs may carry code ahead of data.

## Path 2 — uncached verification (~45 minutes)

```
scripts/reproduce.sh
```

Same, but refetches everything from GDELT's public API (politely
rate-limited). Additionally proves the fetch path. The diff ignores
the trailing 35 days (the heal window): GDELT revises recent days, so
a committed vintage and a fresh fetch legitimately differ there; both
are correct records of what the source said at their respective times.

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
