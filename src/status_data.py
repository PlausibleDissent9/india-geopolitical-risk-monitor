"""
Public status payload (M4, founder-approved 2026-08-05): each data
source's latest data day against an ex-ante freshness window, the
morning contract's measured record, and the pipeline lanes' last
evidence stamps. Everything derives from committed files -- the page
lets a reviewer watch the instrument work instead of being told it
works, and a stale source shows as stale by rule, not by adjective.

The freshness windows are stated in the payload itself. They are
operational expectations (how often the source publishes plus our
fetch cadence), not promises; the morning contract is the only
promise, and reliability.json carries its record.

  python -m src.status_data      writes docs/data/status.json
"""
from __future__ import annotations

import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
SITE_DATA = ROOT / "docs" / "data"

# (key, human name, role in the instrument, evidence file,
#  date extraction, expected-freshness window in days)
# Windows are ex-ante: source publish cadence + our fetch cadence,
# with slack for weekends/holidays where the source has them.
SOURCES: list[dict[str, Any]] = [
    {"key": "gdelt_salience", "name": "GDELT salience store",
     "role": "daily channel volumes — every score derives from this",
     "file": "data/raw/gdelt_volume.csv", "kind": "csv_last_date",
     "expect_days": 2},
    {"key": "events", "name": "GDELT Events stream",
     "role": "event counts for maps and the stress gauge (context)",
     "file": "data/raw/events_daily.csv", "kind": "csv_last_date",
     "expect_days": 5},
    {"key": "portwatch", "name": "IMF PortWatch",
     "role": "chokepoint transit counts (context beside shipping)",
     "file": "data/raw/portwatch_chokepoints.csv", "kind": "csv_last_date",
     "expect_days": 21},
    {"key": "comparators", "name": "Comparator salience",
     "role": "Indonesia/Vietnam placebo panel",
     "file": "data/raw/comparator_salience.csv", "kind": "csv_last_date",
     "expect_days": 7},
    {"key": "markets", "name": "Market outcomes (Yahoo, not redistributed)",
     "role": "event-study and priced-risk panels (beside, never inside)",
     "file": "docs/data/event_study.json", "kind": "json_generated",
     "expect_days": 4},
    {"key": "ucdp", "name": "UCDP GED (bulk)",
     "role": "conflict-event context (never in any score)",
     "file": "data/raw/ucdp_events.csv", "kind": "csv_last_date",
     "date_col": "date_start", "expect_days": 90},
    {"key": "expert_shelf", "name": "Expert attention shelf (RSS)",
     "role": "practitioner-institution titles (context)",
     "file": "data/raw/expert_attention.csv", "kind": "csv_last_date",
     "expect_days": 4},
    {"key": "wiki", "name": "Wikipedia attention",
     "role": "independent attention cross-check",
     "file": "data/raw/wiki_volume.csv", "kind": "csv_last_date",
     "expect_days": 7},
    {"key": "multilingual", "name": "Multilingual salience (V5)",
     "role": "Anglophone-lens bias audit",
     "file": "data/raw/multilingual_salience.csv", "kind": "csv_last_date",
     "expect_days": 14, "absent_note": "backfill in progress on CI"},
]

# Pipeline lanes: the last evidence stamp each one committed.
LANES: list[dict[str, str]] = [
    {"key": "daily_publish", "name": "Daily publish",
     "file": "docs/data/latest.json", "field": "date"},
    {"key": "receipts", "name": "Receipts (corpus scan)",
     "file": "docs/data/receipts.json", "field": "_meta.generated"},
    {"key": "uncertainty", "name": "Sampling bands",
     "file": "docs/data/uncertainty.json", "field": "_meta.generated"},
    {"key": "daily_brief", "name": "Machine brief",
     "file": "docs/data/daily_brief.json", "field": "_meta.generated"},
    {"key": "aptness", "name": "Aptness labels",
     "file": "docs/data/aptness.json", "field": "_meta.generated"},
    {"key": "drift", "name": "Weekly drift + robustness lane",
     "file": "docs/data/robustness_series.json", "field": "_meta.generated"},
    {"key": "reliability", "name": "Reliability record",
     "file": "docs/data/reliability.json", "field": "_meta.generated"},
    {"key": "permanence", "name": "Archive snapshots (twice daily)",
     "file": "docs/data/permanence.json", "field": "_meta.generated"},
]


def _csv_last_date(path: Path, date_col: str | None = None) -> str | None:
    """Max value of the date column -- files are append-ordered but
    healing can rewrite, so scan rather than tail."""
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        col = date_col or ("date" if reader.fieldnames
                           and "date" in reader.fieldnames else None)
        if col is None:
            return None
        best = ""
        for row in reader:
            v = (row.get(col) or "")[:10]
            if v > best:
                best = v
        return best or None


def _dig(obj: Any, dotted: str) -> Any:
    for part in dotted.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


def check_sources(today: date) -> list[dict[str, Any]]:
    out = []
    for s in SOURCES:
        path = ROOT / s["file"]
        latest: str | None = None
        if path.exists():
            if s["kind"] == "csv_last_date":
                latest = _csv_last_date(path, s.get("date_col"))
            else:
                data = json.loads(path.read_text(encoding="utf-8"))
                gen = _dig(data, "_meta.generated") or data.get("generated")
                latest = str(gen)[:10] if gen else None
        rec: dict[str, Any] = {
            "key": s["key"], "name": s["name"], "role": s["role"],
            "latest_data": latest, "expect_within_days": s["expect_days"],
        }
        if latest is None:
            rec["ok"] = False
            rec["note"] = s.get("absent_note", "no data present")
        else:
            age = (today - date.fromisoformat(latest)).days
            rec["age_days"] = age
            rec["ok"] = age <= s["expect_days"]
        out.append(rec)
    return out


def check_lanes() -> list[dict[str, Any]]:
    out = []
    for lane in LANES:
        path = ROOT / lane["file"]
        stamp = None
        if path.exists():
            try:
                stamp = _dig(json.loads(path.read_text(encoding="utf-8")),
                             lane["field"])
            except json.JSONDecodeError:
                stamp = None
        out.append({"key": lane["key"], "name": lane["name"],
                    "evidence": lane["file"], "last": stamp})
    return out


def main() -> None:
    today = datetime.now(timezone.utc).date()
    reliability = {}
    rel_path = SITE_DATA / "reliability.json"
    if rel_path.exists():
        r = json.loads(rel_path.read_text(encoding="utf-8"))
        reliability = {"on_time": r.get("on_time"),
                       "scored_days": r.get("scored_days"),
                       "rate": r.get("rate"),
                       "last_scored_day": (r.get("days") or [{}])[-1].get("day")}
    sources = check_sources(today)
    payload: dict[str, Any] = {
        "_meta": {
            "what": ("Per-source data freshness against ex-ante windows, "
                     "the morning contract's measured record, and each "
                     "pipeline lane's last evidence stamp. Derived "
                     "entirely from committed files; regenerated by the "
                     "daily run. Windows are operational expectations "
                     "stated in this payload, not promises — the morning "
                     "contract is the only promise, and reliability.json "
                     "is its record."),
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "sources": sources,
        "lanes": check_lanes(),
        "morning_contract": reliability,
    }
    (SITE_DATA / "status.json").write_text(json.dumps(payload),
                                           encoding="utf-8")
    ok = sum(1 for s in sources if s["ok"])
    print(f"[status] wrote status.json: {ok}/{len(sources)} "
          f"sources within window")


if __name__ == "__main__":
    main()
