"""Point-in-time vintages as a product: reconstruct any published series
exactly as it stood on any publish date (ideation A3 -- the ALFRED move).

vintages.json PROVES the series is append-only in practice. This payload
makes that property USABLE: a researcher running a backtest needs the
numbers as they stood on day D, not as they stand today, and until now
that took twelve `git show` invocations and trust in their own plumbing.

COMPACT BY CONSTRUCTION
A naive long-format panel (vintage x day x channel) is ~240k rows of
which >99% duplicate the current file, because 10 of 12 vintages differ
from today's series by nothing at all. So each vintage is published as a
RECIPE: truncate the current series at the vintage's last observation,
then apply its diffs (values that differed from today's file). For the
ten clean vintages the diff is empty and the recipe is one truncation.
The whole panel is a few kilobytes and reconstruction is exact --
verified below against git for every vintage before anything publishes.

The moat argument, stated plainly: every other asset here could be
rebuilt by a well-funded competitor after the fact. A real-time archive
cannot -- vintages exist only if you were saving them while they
happened. Each day this file exists, the gap a later entrant cannot
close grows by one day.

  python -m src.vintages_panel            write docs/data/vintages_panel.json
  python -m src.vintages_panel --check    verify reconstruction, write nothing
"""
from __future__ import annotations

import csv
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src import vintages

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"
COLUMNS = vintages.COLUMNS


def _rows(text: str) -> dict[str, dict[str, str]]:
    return {r["date"]: r for r in csv.DictReader(io.StringIO(text))}


def build() -> dict[str, Any]:
    current_text = (SITE_DATA / "history.csv").read_text(encoding="utf-8")
    current = _rows(current_text)

    panel: list[dict[str, Any]] = []
    for sha, day in vintages.vintage_shas():
        blob = vintages._git("show", f"{sha}:{vintages.TRACKED}")
        if not blob.strip():
            continue
        old = _rows(blob)
        last_obs = max(old)
        diffs: dict[str, dict[str, str]] = {}
        for d, row in old.items():
            cur = current.get(d)
            if cur is None:
                # A day the vintage had that today's file lacks entirely
                # must ship whole, or reconstruction is impossible.
                diffs[d] = {c: row.get(c, "") for c in COLUMNS}
                continue
            delta = {c: row.get(c, "") for c in COLUMNS
                     if row.get(c, "") != cur.get(c, "")}
            if delta:
                diffs[d] = delta
        # Days that exist in TODAY's file but not in this vintage --
        # gaps that were healed after it published. Truncation alone
        # would smuggle them into the reconstruction, handing the
        # backtester data that did not exist on that morning: exactly
        # the look-ahead this product exists to prevent. The verifier
        # caught this on the first build (3285 vs 3289 days).
        absent = sorted(d for d in current
                        if d <= last_obs and d not in old)
        panel.append({
            "published": day,
            "sha": sha,
            "last_observation": last_obs,
            "n_rows": len(old),
            "n_diff_days": len(diffs),
            "absent_days": absent,
            "diffs": diffs,
        })

    return {"current_columns": COLUMNS, "vintages": panel}


def reconstruct(entry: dict[str, Any],
                current: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """The recipe a stranger follows, executed here so the panel is
    verified against git before it ever publishes."""
    absent = set(entry.get("absent_days", []))
    out = {d: dict(r) for d, r in current.items()
           if d <= entry["last_observation"] and d not in absent}
    for d, delta in entry["diffs"].items():
        out.setdefault(d, {"date": d}).update(delta)
    return out


def verify(panel: dict[str, Any]) -> int:
    """Every vintage must reconstruct byte-value-exactly from the recipe.
    A panel that is only mostly right is a look-ahead-bias generator with
    a trustworthy name, which is worse than nothing."""
    current = _rows((SITE_DATA / "history.csv").read_text(encoding="utf-8"))
    checked = 0
    for entry in panel["vintages"]:
        blob = vintages._git("show", f"{entry['sha']}:{vintages.TRACKED}")
        truth = _rows(blob)
        rebuilt = reconstruct(entry, current)
        if set(truth) != set(rebuilt):
            raise SystemExit(
                f"[panel] vintage {entry['published']}: day set mismatch "
                f"({len(truth)} vs {len(rebuilt)})")
        for d, row in truth.items():
            for c in COLUMNS:
                if row.get(c, "") != rebuilt[d].get(c, ""):
                    raise SystemExit(
                        f"[panel] vintage {entry['published']} {d} {c}: "
                        f"{row.get(c)!r} != {rebuilt[d].get(c)!r} -- the "
                        "recipe does not reproduce git truth; refusing to "
                        "publish a wrong panel")
        checked += 1
    return checked


def main() -> None:
    check = "--check" in sys.argv
    panel = build()
    n = verify(panel)

    from src import stamp_meta
    payload = {
        "_meta": {
            **stamp_meta.universal_fields("vintages_panel.json"),
            "what": (
                "Every published vintage of the daily series, as an exact "
                "reconstruction recipe: truncate the current history.csv "
                "at the vintage's last_observation, then overwrite the "
                "values in its diffs. Gives a backtester the numbers as "
                "they stood on any publish date -- the ALFRED property -- "
                "without twelve git invocations."),
            "reconstruction": (
                "rows = {d: r for d, r in current.items() if d <= "
                "last_observation and d not in absent_days}; then for "
                "each diff day, apply its channel values over the row. "
                "Verified exact against "
                "git for every vintage listed, on every build; the "
                "builder refuses to publish otherwise."),
            "why_diffs": (
                "10 of the vintages differ from today's series by nothing "
                "at all (vintages.json is the nightly proof), so a full "
                "panel would be >99% duplication. The two revised vintages "
                "carry their changed values inline."),
            "n_vintages": n,
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        **panel,
    }
    if not check:
        (SITE_DATA / "vintages_panel.json").write_text(
            json.dumps(payload, indent=1), encoding="utf-8")
    size = len(json.dumps(payload)) // 1024
    print(f"[panel] {n} vintages verified exact; payload ~{size}KB"
          + (" (check only)" if check else ""))


if __name__ == "__main__":
    main()
