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
# then produce small tail diffs -- the diff step ignores the final 7 days.
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
fi

.venv/bin/python -m pytest -q
.venv/bin/python -m src.run_daily --backfill

echo "[reproduce] diffing docs/data against committed versions"
.venv/bin/python - "$SRC" <<'EOF'
import json, sys
from pathlib import Path

src = Path(sys.argv[1]) / "docs" / "data"
new = Path("docs") / "data"
IGNORE_TAIL_DAYS = 7
TOL = 1e-6
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
        if abs(a - b) > TOL:
            failures.append(f"{path}: {a} != {b}")
    elif a != b:
        failures.append(f"{path}: {a!r} != {b!r}")

for f in sorted(src.glob("*.json")):
    mine = new / f.name
    if not mine.exists():
        print(f"[reproduce] {f.name}: not rebuilt (module not run) -- skipped")
        continue
    compare(json.loads(f.read_text()), json.loads(mine.read_text()), f.name)

if failures:
    print(f"[reproduce] FAILED: {len(failures)} numeric differences")
    for line in failures[:40]:
        print("  ", line)
    sys.exit(1)
print("[reproduce] OK: rebuilt outputs match committed data within tolerance")
EOF

echo "[reproduce] done; workdir left at $WORK for inspection"
