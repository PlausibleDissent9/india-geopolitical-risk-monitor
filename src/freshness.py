"""
Every published payload, audited for staleness (2026-08-07).

The China and V5 lanes each failed silently for days. Both were caught
by accident. The generalisation of what caught them is this: a payload
that stops being rewritten does not break, it keeps serving its last
value, and a stale number is quoted exactly as confidently as a fresh
one. status.json watches ten upstream SOURCES; the site serves seventy
endpoints, and nothing was watching those.

So: read every docs/data/*.json, take its `_meta.generated`, compare
against the cadence its lane is supposed to run at, and fail loudly on
anything past tolerance.

Three rules keep this honest rather than decorative:

  * A payload with NO timestamp is a failure, not a pass. Three
    payloads (alt_specs, seasonality, priced_risk) had no `generated`
    field at all, which meant no audit -- this one included -- could
    ever have told whether they were current. They were stamped before
    this module was written, because an auditor that silently skips
    what it cannot read is worse than no auditor.
  * Exemptions carry a written reason and are checked against a list
    that is short by design. "It doesn't need checking" is a claim.
  * It runs in the enrichment lane, never the 06:00 contract. A
    staleness report must never be the thing that stops a publish.

  python -m src.freshness            audit, publish, exit non-zero if stale
  python -m src.freshness --report   audit and print, always exit 0
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"

# Daily lanes. Three days of slack absorbs a dropped cron plus a
# weekend of GitHub weather without crying wolf.
DEFAULT_MAX_AGE_DAYS = 3

# Lanes that legitimately run less often than daily. Each number is the
# cadence plus slack, not a wish.
MAX_AGE_DAYS: dict[str, int] = {
    "datapack.json": 10,  # weekly, Fridays
    "back_extension.json": 40,  # BigQuery lane, monthly-ish
    "gpr_comparison.json": 40,  # external index updates monthly
    "cow_mids.json": 400,  # frozen historical release
    "ucdp_context.json": 400,  # pinned annual release
    "jodi_energy.json": 45,  # JODI reports with a 1-3 month lag
    "retest.json": 45,  # founder-paced human labelling
    "permanence.json": 10,  # archive snapshots, weekly-ish
    "syndication.json": 5,
    "wiki_hindi.json": 10,
    "vintages.json": 5,
    "detector_blindness.json": 5,
    "monthly.json": 5,
    "seasonality.json": 10,
    "alt_specs.json": 10,
    "priced_risk.json": 10,
    "multilingual.json": 30,  # V5 still backfilling
}

# Exempt, each with the reason it is exempt. Short on purpose.
EXEMPT: dict[str, str] = {
    "daily_brief.json": (
        "withdrawn 2026-08-08 after factual-grounding failures; the fixed "
        "null tombstone remains through at least 2026-11-06 under the API "
        "v2 deprecation window and must not be refreshed as generated prose"
    ),
    "ai_gpr_benchmark.json": (
        "a hash-pinned, one-shot registered benchmark vintage; rewriting it "
        "on a cadence would violate the public registration"
    ),
    "api_contract.json": (
        "a frozen promise, not a readout -- it is regenerated only when a "
        "maintainer deliberately freezes a baseline, and a rolling "
        "timestamp on it would defeat the point"
    ),
    "product_catalog.json": (
        "a versioned public-route contract, not a daily readout; it changes "
        "only when the protected product surface changes, so daily aging "
        "would falsely label a stable catalog as stale"
    ),
    "knowledge_replay_demo.json": (
        "a deterministic synthetic two-release conformance demonstration, not "
        "a live world-state lane; its fixed time is part of the public test vector"
    ),
    "sensor_fusion_demo.json": (
        "a deterministic synthetic eight-lane conformance demonstration, not "
        "a live sensor feed; its fixed time is part of the public test vector"
    ),
    "exposure_dna_demo.json": (
        "a deterministic synthetic two-vintage Exposure DNA conformance demonstration, "
        "not a live entity-exposure feed; its fixed time is part of the public test vector"
    ),
    "notes.json": "the author's weekly writing; cadence is human",
    "note_latest.json": "the author's weekly writing; cadence is human",
    "episodes.json": (
        "a bare JSON array with nowhere to carry _meta; it is written by "
        "the same lane and in the same commit as history.json and "
        "latest.json, whose freshness is checked"
    ),
    "status.json": (
        "the freshness surface itself; it is checked by its own lane "
        "and auditing it here would be circular"
    ),
    "predictions.json": (
        "the Prediction Archive is append-only and event-driven: it "
        "changes when a prediction is registered or graded, not on a "
        "cadence. Ships honest-empty by design, so an unchanged file is "
        "the correct state rather than a stalled lane"
    ),
    "divergence_register.json": (
        "append-only and event-driven: it changes when a registered comparison "
        "produces a qualifying row, not on a daily cadence"
    ),
    "freshness.json": "this audit's own output",
}

# CSV exemptions, same discipline as the JSON ones: a written reason,
# and the list stays short.
EXEMPT_CSV: dict[str, str] = {
    "event_study.csv": (
        "not a series -- one row per channel x outcome x window, with no "
        "date column to age. It is recomputed from episodes.json in the "
        "same lane, and episodes' own freshness is checked"
    ),
}

# Cadence for the dated CSVs, where it differs from daily.
MAX_AGE_DAYS.update(
    {
        "monthly.csv": 70,  # monthly series; a new month lands once a month
        "episodes.csv": 90,  # event-driven -- a quiet quarter is not a stall
    }
)

TIMESTAMP_KEYS = ("generated", "generated_at", "resolved_at")
MEASURED_DATE_FIELDS = ("date", "_meta.date")


def _json_dict(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _dig(obj: Any, dotted: str) -> Any:
    for part in dotted.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


def _generated(path: Path) -> str | None:
    data = _json_dict(path)
    if data is None:
        return None
    meta = data.get("_meta")
    if not isinstance(meta, dict):
        return None
    for key in TIMESTAMP_KEYS:
        v = meta.get(key)
        if isinstance(v, str) and len(v) >= 10:
            return v[:10]
    return None


def _measured_date(path: Path) -> tuple[str | None, str | None]:
    """Return an explicitly carried measurement day and its field.

    A payload can be rewritten today while still describing yesterday.
    That is a legitimate upstream state, not a write-cadence failure, but
    it has to travel separately from ``_meta.generated``. Only explicit
    date fields are read: absence means the payload does not declare one,
    never that its write day should be guessed as its measurement day.
    """
    data = _json_dict(path)
    if data is None:
        return None, None
    for field in MEASURED_DATE_FIELDS:
        value = _dig(data, field)
        if value is not None:
            return str(value), field
    return None, None


def _attach_measurement_date(row: dict[str, Any], path: Path, today: date) -> None:
    measured, field = _measured_date(path)
    if measured is None or field is None:
        row["measurement_status"] = "not_declared"
        return
    row["measured_date"] = measured
    row["measured_date_field"] = field
    try:
        measured_age = (today - date.fromisoformat(measured)).days
    except ValueError:
        row["measurement_status"] = "invalid"
        row["status"] = "undatable"
        row["reason"] = f"unparseable declared measurement date {measured!r} at {field}"
        return
    if len(measured) != 10 or date.fromisoformat(measured).isoformat() != measured:
        row["measurement_status"] = "invalid"
        row["status"] = "undatable"
        row["reason"] = (
            f"declared measurement date {measured!r} at {field} is not an exact ISO-8601 day"
        )
        return
    if measured_age < 0:
        row["measurement_status"] = "future"
        row["status"] = "undatable"
        row["reason"] = f"declared measurement date {measured!r} at {field} is in the future"
        return
    row["measured_age_days"] = measured_age
    row["measurement_status"] = "declared"


# A published CSV has nowhere to carry _meta, so its freshness is the
# latest value in whichever column dates its rows. Checked in order; the
# first present wins.
#
# The first version looked only for "date" and reported three of the five
# as undatable -- which this module treats as a failure, correctly, but
# the failure would have been mine rather than the lane's. episodes.csv
# dates rows by `end`, monthly.csv by `month`.
CSV_DATE_COLUMNS = ("date", "end", "month")


def _csv_last_date(path: Path) -> str | None:
    try:
        with path.open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            cols = reader.fieldnames or []
            col = next((c for c in CSV_DATE_COLUMNS if c in cols), None)
            if col is None:
                return None
            last = None
            for row in reader:
                v = (row.get(col) or "").strip()
                if v and (last is None or v > last):
                    last = v
        if not last:
            return None
        # "2026-08" is a month, not a day. Age it from the month's start:
        # a monthly series is current if its newest month is recent, and
        # padding to the 1st is the conservative reading.
        return f"{last}-01" if len(last) == 7 else last[:10]
    except Exception:  # noqa: BLE001 -- an unreadable payload is undatable
        return None


def audit_csvs(today: date | None = None) -> list[dict[str, Any]]:
    """The five CSVs published alongside the JSON.

    They were outside this audit entirely, because the loop globbed
    "*.json". Two of them -- shares.csv and monthly.csv -- are written by
    steps marked continue-on-error, so their lane can fail without
    turning anything red, and nothing was checking that the file still
    moved. shares.csv is the one referee finding #N promoted to "a
    first-class published artifact"; a frozen copy of it serves plausible
    numbers indefinitely.
    """
    today = today or date.today()
    rows: list[dict[str, Any]] = []
    for path in sorted(SITE_DATA.glob("*.csv")):
        name = path.name
        if name in EXEMPT_CSV:
            rows.append({"payload": name, "status": "exempt", "reason": EXEMPT_CSV[name]})
            continue
        limit = MAX_AGE_DAYS.get(name, DEFAULT_MAX_AGE_DAYS)
        last = _csv_last_date(path)
        if last is None:
            rows.append(
                {
                    "payload": name,
                    "status": "undatable",
                    "max_age_days": limit,
                    "reason": "no date column; cannot be aged",
                }
            )
            continue
        try:
            age = (today - date.fromisoformat(last)).days
        except ValueError:
            rows.append(
                {
                    "payload": name,
                    "status": "undatable",
                    "max_age_days": limit,
                    "reason": f"unparseable last date {last!r}",
                }
            )
            continue
        if age < 0:
            rows.append(
                {
                    "payload": name,
                    "status": "undatable",
                    "max_age_days": limit,
                    "reason": f"last measured row {last!r} is future",
                }
            )
            continue
        rows.append(
            {
                "payload": name,
                "generated": last,
                "age_days": age,
                # A dated CSV exposes its last measured row but carries no
                # embedded write timestamp. Preserve the legacy keys while
                # stating which clock is actually available.
                "measured_date": last,
                "measured_age_days": age,
                "measurement_status": "declared",
                "write_time_status": "not_embedded_in_csv",
                "max_age_days": limit,
                "status": "fresh" if age <= limit else "STALE",
            }
        )
    return rows


def audit(today: date | None = None) -> list[dict[str, Any]]:
    today = today or date.today()
    rows: list[dict[str, Any]] = []
    for path in sorted(SITE_DATA.glob("*.json")):
        name = path.name
        if name in EXEMPT:
            rows.append({"payload": name, "status": "exempt", "reason": EXEMPT[name]})
            continue
        gen = _generated(path)
        limit = MAX_AGE_DAYS.get(name, DEFAULT_MAX_AGE_DAYS)
        if gen is None:
            # Not a pass. A payload nobody can date is a payload nobody
            # can trust, and it is the easiest possible thing to fix.
            rows.append(
                {
                    "payload": name,
                    "status": "undatable",
                    "max_age_days": limit,
                    "reason": "no _meta.generated; add one",
                }
            )
            continue
        try:
            age = (today - date.fromisoformat(gen)).days
        except ValueError:
            rows.append(
                {
                    "payload": name,
                    "status": "undatable",
                    "max_age_days": limit,
                    "reason": f"unparseable timestamp {gen!r}",
                }
            )
            continue
        if age < 0:
            rows.append(
                {
                    "payload": name,
                    "status": "undatable",
                    "max_age_days": limit,
                    "reason": f"write timestamp {gen!r} is future",
                }
            )
            continue
        row: dict[str, Any] = {
            "payload": name,
            "generated": gen,
            "age_days": age,
            # Additive, explicit names. ``generated``/``age_days`` remain
            # for API compatibility; they have always meant write time.
            "written_date": gen,
            "write_age_days": age,
            "max_age_days": limit,
            "status": "fresh" if age <= limit else "STALE",
        }
        _attach_measurement_date(row, path, today)
        rows.append(row)
    return rows


def main() -> None:
    # The CSVs were outside this audit until 2026-08-07, because the loop
    # globbed "*.json". Five published files, two of them written by
    # continue-on-error steps, none of them checked for having moved.
    rows = audit() + audit_csvs()
    bad = [r for r in rows if r["status"] in ("STALE", "undatable")]
    fresh = [r for r in rows if r["status"] == "fresh"]
    exempt = [r for r in rows if r["status"] == "exempt"]
    measured = [r for r in rows if r.get("measurement_status") == "declared"]

    # This module writes the LAST payload of the run, so a stamping step
    # that ran before it would always miss this file -- and did, on the
    # first attempt. Carrying the universal fields itself makes the
    # result independent of step order rather than dependent on getting
    # the order right forever.
    from src import stamp_meta

    payload = {
        "_meta": {
            **stamp_meta.universal_fields("freshness.json"),
            "what": (
                "Write-time age of every non-exempt JSON payload against the "
                "cadence its lane is supposed to run at, with every exemption "
                "listed, plus the separately declared measurement day "
                "wherever the payload carries one. Dated "
                "CSVs expose their last measured row and explicitly state "
                "that no embedded write timestamp exists. "
                "A file can be rewritten today while still describing an "
                "older day; generated/written_date and measured_date must "
                "never be treated as synonyms."
            ),
            "measurement_policy": (
                "Write-time staleness fails this audit. A valid older "
                "measurement day is published as state rather than treated "
                "as a pipeline crash; cross-payload day alignment and its "
                "reader-visible effect are reported in status.json."
            ),
            "undatable_is_a_failure": (
                "A payload with no _meta.generated cannot be audited by "
                "anything, so it counts as a failure rather than a pass. "
                "An auditor that skips what it cannot read is worse than "
                "no auditor, because it reports green."
            ),
            "default_max_age_days": DEFAULT_MAX_AGE_DAYS,
            "n_payloads": len(rows),
            "n_fresh": len(fresh),
            "n_stale_or_undatable": len(bad),
            "n_exempt": len(exempt),
            "n_with_declared_measurement_date": len(measured),
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "payloads": rows,
    }
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / "freshness.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print(
        f"[freshness] {len(fresh)} fresh, {len(bad)} stale/undatable, "
        f"{len(exempt)} exempt, {len(rows)} total"
    )
    for r in bad:
        detail = r.get("reason") or (f"{r.get('age_days')} days old, limit {r.get('max_age_days')}")
        print(f"[freshness] {r['status']}: {r['payload']} ({detail})")

    if bad and "--report" not in sys.argv:
        raise SystemExit(
            f"[freshness] {len(bad)} payload(s) stale or undatable. A lane "
            "has stopped writing, or a payload needs a timestamp. The site "
            "is still serving them either way."
        )


if __name__ == "__main__":
    main()
