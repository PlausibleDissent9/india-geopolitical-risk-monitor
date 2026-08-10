"""
Public status payload (M4, founder-approved 2026-08-05): each data
source's latest data day against an ex-ante freshness window, the
morning contract's measured record, selected lanes' write and measurement
dates, and registered cross-payload day alignments. Everything derives
from committed files -- the page
lets a reviewer watch the instrument work instead of being told it
works, and a stale source shows as stale by rule, not by adjective.

The freshness windows are stated in the payload itself. They are
operational expectations (how often the source publishes plus our
fetch cadence), not promises; the morning contract is the only
promise, and reliability.json carries its record.

  python -m src.status_data      writes docs/data/status.json
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
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
def _multilingual_progress() -> str:
    """Computed absent-note: how much of V5 actually exists.

    Kept deliberately failure-tolerant. This runs inside the status
    payload build, which must not be the thing that breaks the morning.
    """
    try:
        from src import multilingual
        total = len(multilingual.expected_keys())
        missing = len(multilingual.missing_keys())
        if not missing:
            return "complete"
        return (f"{total - missing} of {total} language-channel series "
                "stored; backfill resumes each run")
    except Exception:  # noqa: BLE001 -- a note must never break status
        return "backfill state unavailable"


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
    {"key": "markets", "name": "Market input vintage (Yahoo, not redistributed)",
     "role": "inputs to event-study and priced-risk panels (beside, never inside)",
     "file": "docs/data/event_study.json", "kind": "json_output_only",
     "expect_days": 4,
     "absent_note": (
         "maximum market-input date is not present in committed evidence; "
         "the separately shown output build date is not an input-freshness "
         "claim")},
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
     # The note used to be the fixed string "backfill in progress on
     # CI". It was true in the sense that runs were happening, and it
     # said exactly that for seven days while seventy of them completed
     # without ever writing a single series -- a hand-written note
     # cannot notice that the thing it describes has stalled. It is now
     # computed, so "0 of 15 series stored" says the quiet part.
     "expect_days": 14, "absent_note": _multilingual_progress},
    {"key": "country_china", "name": "China country monitor (V8)",
     "role": "comparator instrument; enters no India score",
     # Untracked until 2026-08-07, which is why its lane could fail
     # every night for days in complete silence. A monitor nobody
     # monitors is not a monitor.
     "file": "data/raw/country_china_volume.csv", "kind": "csv_last_date",
     "expect_days": 3,
     "absent_note": "registered and signed; store not yet collected"},
]

# Pipeline lanes: the last evidence stamp each one committed. Where a lane
# carries an explicit measurement day, keep that distinct from its write
# timestamp -- a file rewritten today can still describe yesterday.
LANES: list[dict[str, str]] = [
    {"key": "daily_publish", "name": "Daily publish",
     "file": "docs/data/latest.json", "field": "_meta.generated",
     "measured_field": "date"},
    {"key": "receipts", "name": "Receipts (corpus scan)",
     "file": "docs/data/receipts.json", "field": "_meta.generated",
     "measured_field": "date"},
    {"key": "uncertainty", "name": "Sampling bands",
     "file": "docs/data/uncertainty.json", "field": "_meta.generated"},
    {"key": "daily_brief", "name": "Machine brief (withdrawn)",
     "file": "docs/data/daily_brief.json", "field": "_meta.withdrawn"},
    {"key": "aptness", "name": "Aptness labels",
     "file": "docs/data/aptness.json", "field": "_meta.generated",
     "measured_field": "_meta.date"},
    {"key": "drift", "name": "Weekly drift + robustness lane",
     "file": "docs/data/robustness_series.json", "field": "_meta.generated"},
    {"key": "reliability", "name": "Reliability record",
     "file": "docs/data/reliability.json", "field": "_meta.generated"},
    {"key": "permanence", "name": "Archive snapshots (twice daily)",
     "file": "docs/data/permanence.json", "field": "_meta.generated"},
]

# Cross-payload joins that affect what readers can safely do. These are
# observability checks, not publish gates: upstream throttling can leave a
# legitimate older evidence day, but the state and its consequence may never
# be hidden behind a green write timestamp.
ALIGNMENTS: list[dict[str, str]] = [
    {
        "key": "receipts_to_final_scores",
        "name": "Receipts evidence vs final score day",
        "reference_file": "docs/data/latest.json",
        "reference_field": "date",
        "reference_label": "Final score day",
        "observed_file": "docs/data/receipts.json",
        "observed_field": "date",
        "observed_label": "Receipts evidence day",
        "effect": (
            "When days differ, evidence-dependent assistant answers refuse "
            "the join; final scores remain published with the mismatch "
            "visible."),
    },
    {
        "key": "aptness_to_receipts",
        "name": "Aptness labels vs receipts evidence day",
        "reference_file": "docs/data/receipts.json",
        "reference_field": "date",
        "reference_label": "Receipts evidence day",
        "observed_file": "docs/data/aptness.json",
        "observed_field": "_meta.date",
        "observed_label": "Aptness-label day",
        "effect": (
            "When days differ, the receipts page must ignore machine "
            "labels and show the evidence unfiltered."),
    },
]


def _static_final_message(state: dict[str, Any]) -> str:
    target = html.escape(str(state.get("target_date") or "unknown"))
    latest = html.escape(str(state.get("latest_finalized_date") or "none"))
    if state.get("finalized") is True:
        return (
            f"Final publication current: exact D-1 target <b>{target}</b> is "
            "finalized. A provisional nowcast is a separate, non-final measure."
        )
    if state.get("status") == "legacy_proof_limited":
        return (
            f"Bounded historical publication: target <b>{target}</b> remains "
            "visible because its cache, store, provenance, latest and history "
            "exactly match commit 9077ea4, and its cache structurally covers all "
            "48 half-hour windows. This byte identity has no source acquisition "
            "receipt, reconstructable English denominator, cache-to-store "
            "calibration/transform receipt, or store-to-public score derivation "
            "receipt; source-retention and redistribution rights review also "
            "remains pending. It is not new-contract final proof. A provisional "
            "nowcast remains separate and non-final."
        )
    labels = {
        "source_unavailable": "the registered source is unavailable",
        "acquisition_failed": "source acquisition or validation failed",
        "pipeline_failed": "publication validation failed",
        "delayed_final": "final publication is delayed",
        "legacy_proof_limited": (
            "the published legacy frame has an unreconstructable denominator"
        ),
    }
    label = labels.get(str(state.get("status")), "final publication is delayed")
    return (
        f"Delayed final: exact D-1 target <b>{target}</b> is not finalized "
        f"because {label}. The latest finalized measure remains "
        f"<b>{latest}</b>. A provisional nowcast is not a substitute for "
        "the missing final."
    )


def write_static_final_disclosure(
    state: dict[str, Any], root: Path = ROOT
) -> None:
    """Bake the current final-vs-target state into both no-JS surfaces."""

    for relative in ("docs/index.html", "docs/status.html"):
        path = root / relative
        path.write_bytes(
            static_final_disclosure_bytes(state, relative, path.read_bytes())
        )


def static_final_disclosure_bytes(
    state: dict[str, Any], relative: str, parent_bytes: bytes
) -> bytes:
    """Deterministically patch only the registered value-free HTML region."""

    message = _static_final_message(state)
    replacements = {
        "docs/index.html": (
            "final-publication-static",
            '<p class="final-publication-status" '
            f'id="final-publication-status">{message}</p>',
        ),
        "docs/status.html": (
            "final-publication-status-static",
            f'<p class="prose" id="final-publication-state">{message}</p>',
        ),
    }
    if relative not in replacements:
        raise RuntimeError(f"static final disclosure path invalid: {relative}")
    try:
        raw = parent_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(
            f"static final disclosure parent invalid: {relative}"
        ) from exc
    marker, content = replacements[relative]
    pattern = re.compile(
        rf"<!--{re.escape(marker)}:start-->.*?"
        rf"<!--{re.escape(marker)}:end-->",
        re.DOTALL,
    )
    replacement = f"<!--{marker}:start-->{content}<!--{marker}:end-->"
    updated, count = pattern.subn(replacement, raw)
    if count != 1:
        raise RuntimeError(f"static final disclosure marker invalid: {relative}")
    return updated.encode("utf-8")


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


def check_sources(today: date, root: Path | None = None) -> list[dict[str, Any]]:
    root = root or ROOT
    out = []
    for s in SOURCES:
        path = root / s["file"]
        latest: str | None = None
        output_generated: str | None = None
        if path.exists():
            if s["kind"] == "csv_last_date":
                latest = _csv_last_date(path, s.get("date_col"))
            elif s["kind"] == "json_output_only":
                data = json.loads(path.read_text(encoding="utf-8"))
                gen = _dig(data, "_meta.generated") or data.get("generated")
                output_generated = str(gen)[:10] if gen else None
        rec: dict[str, Any] = {
            "key": s["key"], "name": s["name"], "role": s["role"],
            "latest_data": latest, "expect_within_days": s["expect_days"],
        }
        if output_generated is not None:
            rec["output_generated"] = output_generated
        if latest is None:
            rec["ok"] = False
            note = s.get("absent_note", "no data present")
            # A note may be a callable so it can report live state. A
            # fixed string cannot notice that what it describes has
            # stalled, which is how "backfill in progress on CI" stayed
            # on this page for seven days of futile runs.
            rec["note"] = note() if callable(note) else note
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
        measured_day = None
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                stamp = _dig(payload, lane["field"])
                measured_field = lane.get("measured_field")
                if measured_field:
                    measured_day = _dig(payload, measured_field)
            except json.JSONDecodeError:
                stamp = None
        out.append({"key": lane["key"], "name": lane["name"],
                    "evidence": lane["file"], "last": stamp,
                    "measured_day": measured_day})
    return out


def _alignment_value(root: Path, file: str, field: str) -> tuple[Any, str | None]:
    path = root / file
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return None, "evidence file missing"
    except json.JSONDecodeError:
        return None, "evidence file is not valid JSON"
    value = _dig(payload, field)
    if value is None:
        return None, f"field {field!r} is absent"
    return value, None


def check_alignments(root: Path | None = None,
                     today: date | None = None) -> list[dict[str, Any]]:
    """Evaluate every registered measurement-day join from source bytes."""
    root = root or ROOT
    today = today or datetime.now(timezone.utc).date()
    out: list[dict[str, Any]] = []
    for spec in ALIGNMENTS:
        reference, reference_error = _alignment_value(
            root, spec["reference_file"], spec["reference_field"])
        observed, observed_error = _alignment_value(
            root, spec["observed_file"], spec["observed_field"])
        row: dict[str, Any] = {
            "key": spec["key"],
            "name": spec["name"],
            "reference": {
                "label": spec["reference_label"],
                "evidence": spec["reference_file"],
                "field": spec["reference_field"],
                "date": reference,
            },
            "observed": {
                "label": spec["observed_label"],
                "evidence": spec["observed_file"],
                "field": spec["observed_field"],
                "date": observed,
            },
            "effect": spec["effect"],
            "publish_blocking": False,
        }
        errors = [e for e in (reference_error, observed_error) if e]
        if errors:
            row.update({
                "aligned": None,
                "status": "unavailable",
                "day_difference": None,
                "reason": "; ".join(errors),
            })
            out.append(row)
            continue
        try:
            reference_text = str(reference)
            observed_text = str(observed)
            reference_day = date.fromisoformat(reference_text)
            observed_day = date.fromisoformat(observed_text)
        except ValueError:
            row.update({
                "aligned": None,
                "status": "invalid",
                "day_difference": None,
                "reason": (
                    "one or both declared dates are not exact ISO-8601 "
                    "days"),
            })
            out.append(row)
            continue
        if (reference_day.isoformat() != reference_text
                or observed_day.isoformat() != observed_text):
            row.update({
                "aligned": None,
                "status": "invalid",
                "day_difference": None,
                "reason": "one or both fields are not exact ISO-8601 days",
            })
            out.append(row)
            continue
        if reference_day > today or observed_day > today:
            row.update({
                "aligned": None,
                "status": "invalid",
                "day_difference": None,
                "reason": "one or both declared dates are in the future",
            })
            out.append(row)
            continue
        difference = (reference_day - observed_day).days
        status = "aligned" if difference == 0 else (
            "lagging" if difference > 0 else "ahead")
        row.update({
            "aligned": difference == 0,
            "status": status,
            # Positive means the observed payload is behind its reference.
            "day_difference": difference,
        })
        out.append(row)
    return out


def main(today: date | None = None) -> None:
    today = today or datetime.now(timezone.utc).date()
    reliability = {}
    rel_path = SITE_DATA / "reliability.json"
    if rel_path.exists():
        r = json.loads(rel_path.read_text(encoding="utf-8"))
        reliability = {"on_time": r.get("on_time"),
                       "scored_days": r.get("scored_days"),
                       "rate": r.get("rate"),
                       "last_scored_day": (r.get("days") or [{}])[-1].get("day")}
    sources = check_sources(today)
    alignments = check_alignments()
    aligned_count = sum(1 for a in alignments if a["aligned"] is True)
    from src import final_publication, stamp_meta
    final_state = final_publication.public_status(today=today)
    payload: dict[str, Any] = {
        "_meta": {
            **stamp_meta.universal_fields("status.json"),
            "what": ("Per-source data freshness against ex-ante windows, "
                     "write-time and measurement-day pipeline stamps, "
                     "registered cross-payload day alignments, and the "
                     "morning contract's measured record. Derived "
                     "entirely from committed files; regenerated by the "
                     "daily run. Windows are operational expectations "
                     "stated in this payload, not promises — the morning "
                     "contract is the only promise, and reliability.json "
                     "is its record."),
            "alignment_policy": (
                "A valid mismatch is published, not hidden and not treated "
                "as a pipeline crash. Features that require the mismatched "
                "join must refuse or fall back as stated in alignments[]."),
            "n_alignment_checks": len(alignments),
            "n_aligned": aligned_count,
            "n_not_aligned_or_unavailable": len(alignments) - aligned_count,
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "sources": sources,
        "lanes": check_lanes(),
        "alignments": alignments,
        "final_publication": final_state,
        "morning_contract": reliability,
    }
    (SITE_DATA / "status.json").write_text(
        json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    write_static_final_disclosure(final_state)
    ok = sum(1 for s in sources if s["ok"])
    print(f"[status] wrote status.json: {ok}/{len(sources)} "
          f"sources within window; "
          f"{aligned_count}/"
          f"{len(alignments)} measurement-day joins aligned")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-today", type=date.fromisoformat)
    parsed = parser.parse_args()
    main(today=parsed.contract_today)
