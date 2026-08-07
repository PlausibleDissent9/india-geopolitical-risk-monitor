#!/usr/bin/env bash
# Reproducibility check (spec B4): from a clean clone, rebuild everything
# and diff the numeric outputs against the committed versions.
#
#   scripts/reproduce.sh [--use-cache]
#
# --use-cache copies data/raw/ from the source checkout first, so the run
# verifies computation only (minutes). Without it, the full GDELT backfill
# refetches (~30-60 min politely rate-limited) and the run additionally
# verifies the fetch path; recent GDELT revisions of the last few days can
# then produce small tail diffs -- the diff step ignores the final 35 days
# (matching the heal window in daily.yml: heal revisions and opportunistic
# chunk harvests propagate through trailing percentiles well past 7 days;
# 2026-08-06: the first proof run failed at indices 6-13 days back for
# exactly this reason -- committed history is a vintage record, a fresh
# rebuild is a current-data recomputation, and both are correct).
#
# Expected runtime: ~5 min cached, ~45 min uncached.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
echo "[reproduce] source: $SRC"
echo "[reproduce] workdir: $WORK"

git clone --quiet "$SRC" "$WORK/clone"
cd "$WORK/clone"

python3 -m venv .venv
.venv/bin/pip install --quiet -r requirements.txt

if [[ "${1:-}" == "--use-cache" ]]; then
  echo "[reproduce] copying raw-data cache from source checkout"
  rm -rf data/raw
  cp -R "$SRC/data/raw" data/raw
  # Cached mode verifies computation, strictly offline: ALL acquisition
  # is refused -- network and the settled-chunk cache alike -- so the
  # committed store is the only data source and the rebuild is a pure
  # recompute of the committed vintage. (2026-08-06: a cache hit used
  # to overwrite ngram-healed store days with DOC-cache values, which
  # made the diff depend on which lane happened to have produced the
  # vintage that morning.)
  export IGRM_OFFLINE=1
fi

.venv/bin/python -m pytest -q

# Marker file: anything in docs/data older than this was NOT regenerated
# by this run. Without it the diff compares the clone's committed copy
# against the source's identical committed copy and calls the match a
# reproduction -- which is true of every file no module touched, and
# tells a replicator nothing. Coverage is now reported as a number.
REBUILD_MARK="$WORK/rebuild_start"
touch "$REBUILD_MARK"

if [[ "${IGRM_OFFLINE:-}" == "1" ]]; then
  # Cached mode verifies the committed vintage EXACTLY: incremental run
  # over the copied store, no healing, no fetching. Healing here once
  # pulled one extra day in and shifted a shipping episode's bootstrap
  # p-values against the committed outputs (2026-08-01, pass 3): any
  # data added past the committed store is a vintage change, not a
  # reproduction. A from-scratch chunk rebuild is the uncached path.
  .venv/bin/python -m src.run_daily
else
  .venv/bin/python -m src.run_daily --backfill
fi

# Derived lanes that are PURE COMPUTATION over the committed stores:
# no network, no caches beyond what is in the repo, deterministic given
# the same inputs. Until 2026-08-07 reproduce.sh ran only run_daily, so
# every payload these produce was reported "not rebuilt (module not
# run) -- skipped" and the replication promise silently did not cover
# them. A dataset nobody can rebuild is not reproducible just because
# the rest of the repo is.
#
# Deliberately NOT here: syndication (needs the receipt corpus cache and
# will reach for the network on an uncached day), wiki_hindi (Wikimedia
# API), and the fetch lanes. Those are verified by their own tests, not
# by this diff, and adding them would make the monthly reproduce run
# fail for reasons that are not reproducibility.
.venv/bin/python -m src.provenance
.venv/bin/python -m src.publish_shares
.venv/bin/python -m src.monthly
.venv/bin/python -m src.blind_spot
.venv/bin/python -m src.alt_specs
.venv/bin/python -m src.seasonality
.venv/bin/python -m src.uncertainty
.venv/bin/python -m src.episode_actors
.venv/bin/python -m src.exposure
.venv/bin/python -m src.vintages
.venv/bin/python -m src.status_data
# Stamp last, or the rebuilt payloads lack the universal _meta fields
# the committed ones carry and every file diffs as "present in one side
# only" -- a reproducibility failure that is really a paperwork one.
.venv/bin/python -m src.stamp_meta

echo "[reproduce] diffing docs/data against committed versions"
.venv/bin/python - "$SRC" "$REBUILD_MARK" <<'EOF'
import json, sys
from pathlib import Path

src = Path(sys.argv[1]) / "docs" / "data"
new = Path("docs") / "data"
IGNORE_TAIL_DAYS = 35
TOL = 1e-6
# Market-dependent outputs (event_study, priced_risk) rest on Yahoo
# inputs that are deliberately NOT committed (redistribution license),
# so the committed numbers carry CI's fetch vintage and a replicator
# carries their own: Yahoo revises recent bars between fetches, which
# moves seeded-bootstrap fields by resampling-noise scale (observed
# max 0.046 on 2026-08-01). Those files compare within MARKET_TOL and
# the run reports how many numbers used the band. Everything whose
# inputs are fully committed must match to TOL.
MARKET_TOL = 0.06
MARKET_FILES = ("event_study.json", "priced_risk.json")
band_hits = [0]
failures = []

def compare(a, b, path="", dates_len=None):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k in ("generated",):
                continue
            if k not in a or k not in b:
                failures.append(f"{path}.{k}: present in one side only")
                continue
            compare(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list) and isinstance(b, list):
        n = min(len(a), len(b), max(0, len(a) - IGNORE_TAIL_DAYS))
        for i in range(n):
            compare(a[i], b[i], f"{path}[{i}]")
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        tol = MARKET_TOL if path.startswith(MARKET_FILES) else TOL
        # Tail maturation: the newest episode's 5- and 20-day market
        # windows complete as trading days pass, so per-cell episode
        # counts in market files legitimately differ by one between
        # vintages (observed 107 vs 108, 2026-08-01).
        if path.startswith(MARKET_FILES) and path.endswith(".n"):
            tol = 1.0
        if abs(a - b) > tol:
            failures.append(f"{path}: {a} != {b}")
        elif abs(a - b) > TOL:
            band_hits[0] += 1
    elif a != b:
        failures.append(f"{path}: {a!r} != {b!r}")

print(f"[reproduce] market-vintage band: +/-{MARKET_TOL} on {MARKET_FILES}")

mark = Path(sys.argv[2]).stat().st_mtime
verified, untouched = [], []
for f in sorted(src.glob("*.json")):
    mine = new / f.name
    if not mine.exists():
        untouched.append(f.name)
        continue
    # A file the rebuild never wrote is the clone's committed copy, so
    # comparing it to the source's committed copy proves nothing. Say so
    # rather than counting it as a reproduction.
    if mine.stat().st_mtime < mark:
        untouched.append(f.name)
        continue
    verified.append(f.name)
    compare(json.loads(f.read_text()), json.loads(mine.read_text()), f.name)

print(f"[reproduce] COVERAGE: {len(verified)} payload(s) actually "
      f"regenerated and diffed; {len(untouched)} not produced by any "
      "module this run and therefore NOT verified")
if untouched:
    print(f"[reproduce] not verified: {', '.join(sorted(untouched))}")

if failures:
    print(f"[reproduce] FAILED: {len(failures)} numeric differences")
    for line in failures[:40]:
        print("  ", line)
    sys.exit(1)
print("[reproduce] OK: rebuilt outputs match committed data within tolerance")
EOF

echo "[reproduce] done; workdir left at $WORK for inspection"
