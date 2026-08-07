"""
What did the index say on the day it said it? (referee finding #13,
2026-08-07)

Anyone using this series in real-time research needs to know whether a
value they read on day D is still the value the site shows for day D
today. If published numbers are quietly revised, every backtest built on
the current file has look-ahead bias baked in and nobody can tell.

The archive already exists and always did: every daily publish is a
commit, so `docs/data/history.csv` at commit SHA is exactly what the
site served that morning. What was missing is the measurement -- nobody
had ever diffed the vintages against each other, so "we don't revise"
was a belief rather than a finding.

Measured across every published vintage:

    2026-07-29 onward   0 changed values in every vintage
    2026-07-27          101 changed values, max 99.4 percentile points

The single revision episode sits exactly on methodology v1.0.1
(2026-07-29), which changed the percentile computation and is recorded
in the changelog. Since then the series is append-only in practice: days
are added, never rewritten.

THIS IS ALSO A TRIPWIRE
-----------------------
The value of measuring it every night is not the reassuring number. It
is that a future silent revision -- a rebuilt store, a dictionary change
applied retroactively, a splice ratio quietly adopted -- shows up here
as a non-zero count the next morning, instead of being discovered by a
user whose results stopped replicating. A claim that goes unchecked
stops being evidence.

RETRIEVING A VINTAGE
--------------------
    git log --format='%H %ad' --date=short -- docs/data/history.csv
    git show <SHA>:docs/data/history.csv > history_as_of_that_day.csv

No special tooling, no server, no cooperation from this project
required. That is the point.

  python -m src.vintages     writes docs/data/vintages.json
"""
from __future__ import annotations

import csv
import io
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"
TRACKED = "docs/data/history.csv"
COLUMNS = ["composite", "pakistan_west", "china_east", "gulf_energy",
           "us_trade", "shipping"]

# Vintages published on these dates are KNOWN to differ from the current
# series, with a published cause. 2026-07-27 predates methodology
# v1.0.1 (2026-07-29), which changed the percentile computation and is
# recorded in the changelog.
#
# Adding a date here is a deliberate act and must be accompanied by a
# changelog entry naming the change. That is the whole mechanism: a
# revision with a dated published cause is a version, a revision without
# one is a defect, and this list is where the difference is declared.
# `--check` fails on any revision not listed, so a silent rebuild cannot
# pass quietly.
REGISTERED_REVISIONS = {"2026-07-27"}


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True).stdout


def _unshallow_if_needed() -> None:
    """CI checkouts are shallow (fetch-depth 1), so `git log` would see
    a single commit and this module would cheerfully report one clean
    vintage and zero revisions -- a tripwire that always passes, which
    is worse than no tripwire. Same self-heal as
    scripts/build_reliability.py."""
    shallow = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT,
        capture_output=True, text=True).stdout.strip()
    if shallow == "true":
        print("[vintages] shallow checkout; unshallowing for real history")
        subprocess.run(["git", "fetch", "--quiet", "--unshallow", "origin"],
                       cwd=ROOT, check=False)


def vintage_shas() -> list[tuple[str, str]]:
    _unshallow_if_needed()
    out = _git("log", "--format=%H %ad", "--date=short", "--", TRACKED)
    rows = []
    for line in out.strip().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            rows.append((parts[0], parts[1]))
    return rows


def _rows(text: str) -> dict[str, dict[str, str]]:
    return {r["date"]: r for r in csv.DictReader(io.StringIO(text))}


def compare() -> list[dict[str, Any]]:
    current = _rows((SITE_DATA / "history.csv").read_text(encoding="utf-8"))
    out: list[dict[str, Any]] = []
    for sha, day in vintage_shas():
        blob = _git("show", f"{sha}:{TRACKED}")
        if not blob.strip():
            continue
        old = _rows(blob)
        common = set(old) & set(current)
        changed_days: set[str] = set()
        n_changed = 0
        max_diff = 0.0
        for d in common:
            for col in COLUMNS:
                a, b = old[d].get(col, ""), current[d].get(col, "")
                if a == "" or b == "" or a == b:
                    continue
                n_changed += 1
                changed_days.add(d)
                try:
                    max_diff = max(max_diff, abs(float(a) - float(b)))
                except ValueError:
                    pass
        out.append({
            "published": day,
            "sha": sha,
            "n_rows": len(old),
            "n_overlapping_days": len(common),
            "n_changed_values": n_changed,
            "n_changed_days": len(changed_days),
            "max_abs_change": round(max_diff, 4) if n_changed else 0.0,
            # Capped: a vintage that revised everything would otherwise
            # write a payload larger than the series.
            "changed_days_sample": sorted(changed_days)[:25],
            "retrieve": f"git show {sha}:{TRACKED}",
        })
    return out


def main() -> None:
    rows = compare()
    if not rows:
        raise SystemExit("[vintages] no vintages found; refusing to publish")

    revised = [r for r in rows if r["n_changed_values"] > 0]
    clean = [r for r in rows if r["n_changed_values"] == 0]
    latest_revision = max((r["published"] for r in revised), default=None)

    # Fourth module to need this. stamp_meta cannot reach a payload
    # written after it runs, and this one is written by the last step in
    # the lane. Carrying the fields here removes the ordering dependency
    # instead of relying on step order staying correct forever.
    from src import stamp_meta
    payload = {
        "_meta": {
            **stamp_meta.universal_fields("vintages.json"),
            "what": (
                "Every published vintage of the daily series, diffed "
                "against what the site serves today. Answers whether a "
                "value read on day D is still the value shown for day D "
                "now -- the question that decides whether a backtest "
                "built on the current file has look-ahead bias in it."),
            "how": (
                "Each daily publish is a commit, so history.csv at a "
                "given SHA is exactly what was served that morning. This "
                "compares every such vintage to the current file on "
                "their overlapping dates, across composite and all five "
                "channels."),
            "finding": (
                f"{len(clean)} of {len(rows)} vintages show zero changed "
                "values. The series is append-only in practice: days are "
                "added, not rewritten." if clean else
                "Revisions detected in every vintage."),
            "revisions": (
                f"The revision episodes are dated {sorted({r['published'] for r in revised})} "
                "and correspond to methodology changelog entries -- "
                "notably v1.0.1 (2026-07-29), which changed the "
                "percentile computation. A revision with a dated, "
                "published cause is a version; a revision without one is "
                "a defect." if revised else
                "No revision has ever been detected."),
            "this_is_a_tripwire": (
                "The point of recomputing this nightly is not the "
                "reassuring number. A future silent revision -- a "
                "rebuilt store, a dictionary applied retroactively, a "
                "splice ratio quietly adopted -- appears here as a "
                "non-zero count the next morning, rather than being "
                "found by a user whose results stopped replicating."),
            "retrieve_any_vintage": (
                "git log --format='%H %ad' --date=short -- "
                f"{TRACKED}  then  git show <SHA>:{TRACKED}"),
            "n_vintages": len(rows),
            "n_vintages_clean": len(clean),
            "n_vintages_revised": len(revised),
            "most_recent_revision": latest_revision,
            "columns_compared": COLUMNS,
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "vintages": rows,
    }
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / "vintages.json").write_text(json.dumps(payload, indent=1),
                                             encoding="utf-8")
    print(f"[vintages] {len(rows)} vintages: {len(clean)} unchanged, "
          f"{len(revised)} revised"
          + (f" (most recent {latest_revision})" if latest_revision else ""))
    for r in revised:
        known = "registered" if r["published"] in REGISTERED_REVISIONS \
            else "UNREGISTERED"
        print(f"[vintages]   {r['published']} {r['sha'][:8]}: "
              f"{r['n_changed_values']} values on {r['n_changed_days']} days, "
              f"max {r['max_abs_change']}  [{known}]")

    unregistered = [r for r in revised
                    if r["published"] not in REGISTERED_REVISIONS]
    if unregistered:
        for r in unregistered:
            print(f"[vintages] SILENT REVISION: the vintage published "
                  f"{r['published']} ({r['sha'][:8]}) differs from the "
                  f"current series on {r['n_changed_days']} days, "
                  f"max {r['max_abs_change']}, with no registered cause. "
                  f"Inspect with: git show {r['sha']}:{TRACKED}")
        raise SystemExit(
            "[vintages] published history was rewritten without a "
            "registered cause. Either this was a mistake and the series "
            "must be restored, or it was a deliberate methodology change "
            "-- in which case add the date to REGISTERED_REVISIONS and "
            "write the changelog entry. Do not silence this by doing the "
            "former to avoid the latter.")


if __name__ == "__main__":
    main()
