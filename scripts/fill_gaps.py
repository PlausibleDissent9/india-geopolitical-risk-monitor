"""
Fill the store's missing days (referee finding #8, 2026-08-07).

The store had 21 days absent entirely -- 2 in 2017-12, 1 in 2020-10, 1
in 2023-03, 16 in 2025-06, 1 in 2025-07. They were published as
`known_gaps` in shares.json, which was honest but was not a fix, and the
project had never established whether they were *our* failures or
GDELT's.

THEY ARE NOT OURS. The script ran, recovered nothing, and the reason is
the answer.

I first "established" the gaps were repairable by probing
2025-06-05..2025-06-12 and getting all eight days back in 28 seconds.
That probe was worthless: the gaps in that month are 2025-06-15 to
2025-07-01, and the window I tested contained not one of them. I had
confirmed that GDELT holds days the store already had.

The real test, run afterwards on 2025-06-13..2025-07-03, returns
2025-06-13, 2025-06-14, 2025-07-02 and 2025-07-03 -- the days bracketing
the gap -- and NOTHING for the seventeen days between. GDELT has no data
there. The outage is upstream, and 17 of the 21 missing days are that
single block.

The remaining four (2017-12-01, 2017-12-02, 2020-10-20, 2023-03-23) are
UNVERIFIED: the probes for them were rate-limited into failure (GDELT
asks for one request per five seconds and enforces it hard). Inconclusive
is recorded as inconclusive rather than assumed to match.

So this script stays, because it is the thing that produced the finding
and because a future GDELT re-ingest would make it useful, but the gaps
are a disclosed upstream absence rather than a repairable defect. That
is why publish_shares lists them and why monthly.py refuses a mean for
2025-06 instead of averaging the fortnight that survived.

WHAT THIS SCRIPT MAY AND MAY NOT DO
-----------------------------------
It may add days that are absent. It may not change a single value that
already exists -- not by a rounding step, not by a "refresh", not at
all. Published history is append-only (src/vintages.py enforces that
nightly), and a backfill script that quietly revised the past would
defeat the tripwire watching for exactly that.

The guarantee is enforced, not intended: every pre-existing cell is
compared before and after, and the script refuses to write if any
differs.

  python scripts/fill_gaps.py --dry-run    report what it would fill
  python scripts/fill_gaps.py              fetch and fill
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import fetch_gdelt as fg  # noqa: E402

STORE = ROOT / "data" / "raw" / "gdelt_volume.csv"
# Days either side of a gap to fetch. GDELT's timeline endpoint is
# happier with a window than a single day, and neighbours are free.
PAD_DAYS = 3


def load_store() -> pd.DataFrame:
    df = pd.read_csv(STORE, parse_dates=["date"])
    df["date"] = df["date"].dt.date
    return df.set_index("date").sort_index()


def gap_days(df: pd.DataFrame) -> list[date]:
    have = set(df.index)
    out, cur = [], min(have)
    last = max(have)
    while cur <= last:
        if cur not in have:
            out.append(cur)
        cur += timedelta(days=1)
    return out


def windows(gaps: list[date]) -> list[tuple[date, date]]:
    """Contiguous runs of gaps, padded, merged where they overlap."""
    if not gaps:
        return []
    runs: list[list[date]] = [[gaps[0]]]
    for d in gaps[1:]:
        if (d - runs[-1][-1]).days <= PAD_DAYS * 2:
            runs[-1].append(d)
        else:
            runs.append([d])
    return [(r[0] - timedelta(days=PAD_DAYS),
             r[-1] + timedelta(days=PAD_DAYS)) for r in runs]


def main() -> None:
    dry = "--dry-run" in sys.argv
    with open(ROOT / "dictionaries.json", encoding="utf-8") as f:
        dicts = json.load(f)
    channels = {k: v for k, v in dicts.items() if not k.startswith("_")}

    before = load_store()
    gaps = gap_days(before)
    if not gaps:
        print("[fill-gaps] no gaps; nothing to do")
        return
    wins = windows(gaps)
    print(f"[fill-gaps] {len(gaps)} missing days in {len(wins)} window(s)")
    for a, b in wins:
        n = sum(1 for g in gaps if a <= g <= b)
        print(f"[fill-gaps]   {a} .. {b}  ({n} missing)")
    if dry:
        return

    filled = before.copy()
    for a, b in wins:
        for ch, spec in channels.items():
            try:
                s = fg.fetch_channel(spec["terms"], a, b, spec.get("anchor"))
            except Exception as e:  # noqa: BLE001 -- one channel may fail
                print(f"[fill-gaps] {ch} {a}..{b} failed: "
                      f"{type(e).__name__}: {e}")
                continue
            if s.empty:
                print(f"[fill-gaps] {ch} {a}..{b}: no data returned")
                continue
            added = 0
            for ts, val in s.items():
                d = ts.date() if hasattr(ts, "date") else ts
                # ONLY absent cells. An existing value is never touched,
                # whatever GDELT says today -- that is what makes this a
                # backfill rather than a rewrite.
                if d in filled.index and pd.notna(filled.at[d, ch]):
                    continue
                if d not in gaps:
                    continue
                filled.loc[d, ch] = float(val)
                added += 1
            print(f"[fill-gaps] {ch} {a}..{b}: filled {added} day(s)")

    filled = filled.sort_index()

    # The guarantee, enforced. Every cell that existed before must be
    # bit-identical after; if not, refuse to write and say so.
    common = before.index.intersection(filled.index)
    drift = []
    for ch in before.columns:
        a_col = before.loc[common, ch]
        b_col = filled.loc[common, ch]
        differs = (a_col.notna() & (a_col != b_col))
        for d in a_col.index[differs]:
            drift.append((str(d), ch, a_col[d], b_col[d]))
    if drift:
        for d, ch, old, new in drift[:10]:
            print(f"[fill-gaps] CHANGED {d} {ch}: {old} -> {new}")
        raise SystemExit(
            f"[fill-gaps] refusing to write: {len(drift)} pre-existing "
            "value(s) would change. This script may only ADD days; "
            "rewriting history would defeat the vintage tripwire.")

    still = [g for g in gap_days(filled)]
    newly = len(gaps) - len(still)
    if newly == 0:
        print("[fill-gaps] nothing recovered; store unchanged")
        return

    filled.to_csv(STORE, index_label="date")
    print(f"[fill-gaps] filled {newly} of {len(gaps)} missing days; "
          f"{len(still)} still absent")
    if still:
        print(f"[fill-gaps] remaining: {[str(d) for d in still]}")


if __name__ == "__main__":
    main()
