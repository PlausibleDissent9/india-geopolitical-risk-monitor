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
NOT part of replication — without it the pipeline skips two
display-layer modules (daily brief, aptness labels) and no number
changes.

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
