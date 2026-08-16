"""
Nightly dual-computation audit (practitioner layer item 9).

Recomputes a battery of published numbers from raw stores by
deliberately separate derivations (inline arithmetic, not the site
builders) and exits nonzero on any mismatch, failing the publish
loudly. This is the manual V2/V3/V4 audit made permanent: two
different computations must agree before a day goes live.

Checks:
  1. latest.json composite equals the mean of its channel scores.
  2. stress gauge equals the renormalized weighted mean of its
     published components under the registered weights.
  3. Comparator latest values equal an inline trailing-percentile
     recompute from the raw store (complete weeks only).
  4. Map relations totals for three heavy partners equal raw dyad
     store sums.
  5. Chokepoint payload week counts and joint-window integrity.

  python -m src.audit          exit 0 all-pass, exit 1 with the list
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data"
RAW = ROOT / "data" / "raw"

TOL = 0.051  # published numbers are rounded to 0.1


def _fail(msgs: list[str], ok: bool, label: str) -> None:
    print(("PASS " if ok else "FAIL ") + label)
    if not ok:
        msgs.append(label)


def main() -> None:
    failures: list[str] = []

    latest = json.loads((DATA / "latest.json").read_text())
    if latest.get("composite") is not None:
        scores = [c["score"] for c in latest["channels"].values()]
        # Same rounded-inputs bound as the gauge below: the composite is
        # rounded from the UNROUNDED channel mean while this recompute
        # averages the five already-rounded published scores, so honest
        # arithmetic can differ by up to ~0.10. TOL refused the green
        # 2026-08-15 final at 47.8 vs mean 47.74 (run 31919051691) and
        # cost the 06:00 IST contract that morning.
        ok = (all(s is not None for s in scores)
              and abs(float(np.mean(scores)) - latest["composite"]) <= 0.101)
        _fail(failures, ok,
              f"latest composite {latest['composite']} == mean(channels) "
              f"{round(float(np.mean([s for s in scores if s is not None])), 2)}")

    sg_path = DATA / "stress_gauge.json"
    if sg_path.exists():
        sg = json.loads(sg_path.read_text())
        w = sg["_meta"]["weights"]
        present = {k: v for k, v in sg["components"].items() if v is not None}
        if present and sg.get("gauge") is not None:
            calc = sum(present[k] * w[k] for k in present) / sum(w[k] for k in present)
            # Both sides are published rounded to 0.1: the gauge itself
            # (+/-0.05) and each component feeding this recompute
            # (weighted +/-0.05 combined), so honest arithmetic can
            # differ by up to ~0.10. A 0.051 tolerance here blocked
            # three green days over 2026-08-02/03 (ledger entry).
            _fail(failures, abs(calc - sg["gauge"]) <= 0.101,
                  f"gauge {sg['gauge']} == weighted components {round(calc, 2)}")

    cm_path = DATA / "comparators.json"
    if cm_path.exists() and (RAW / "comparator_salience.csv").exists():
        cm = json.loads(cm_path.read_text())
        sal = pd.read_csv(RAW / "comparator_salience.csv", parse_dates=["date"])
        sal = sal.set_index("date").sort_index()
        for k, v in cm["countries"].items():
            s = sal[k].sort_index()
            # inline trailing percentile, independent of build_index
            pct = s.rolling("730D", min_periods=180).apply(
                lambda a: float("nan") if np.isnan(a[-1])
                else 100.0 * float(np.mean(a[~np.isnan(a)] <= a[-1])), raw=True)
            wk = pct.resample("W-MON").mean().dropna().round(1)
            wk = wk[wk.index <= s.dropna().index.max()]
            ok = (len(wk) > 0 and abs(float(wk.iloc[-1]) - v["latest"]) <= TOL
                  and str(wk.index[-1].date()) == v["weeks"][-1])
            _fail(failures, ok,
                  f"comparator {k} latest {v['latest']} @ {v['weeks'][-1]}")

    mr_path = DATA / "map_relations.json"
    if mr_path.exists() and (RAW / "events_dyads.csv").exists():
        mr = json.loads(mr_path.read_text())
        dy = pd.read_csv(RAW / "events_dyads.csv")
        sums = dy.groupby("partner")["n"].sum()
        for p in ("PAK", "CHN", "USA"):
            if p in mr["partners"]:
                ok = int(sums.get(p, 0)) == mr["partners"][p]["n"]
                _fail(failures, ok,
                      f"map {p} n {mr['partners'][p]['n']} == dyad sum {int(sums.get(p, 0))}")

    cp_path = DATA / "chokepoints.json"
    if cp_path.exists():
        cp = json.loads(cp_path.read_text())
        for k, c in cp["chokepoints"].items():
            ok = (len(c["weeks"]) == c["n_weeks"]
                  == len(c["salience_pct"]) == len(c["transits_pct"]))
            _fail(failures, ok, f"chokepoint {k} arrays consistent ({c['n_weeks']})")

    if failures:
        print(f"[audit] {len(failures)} MISMATCH(ES); refusing the publish")
        sys.exit(1)
    print("[audit] all dual computations agree")


if __name__ == "__main__":
    main()
