"""The CSV and the JSON must be the same numbers.

Five payloads publish in both formats -- history, episodes, event_study,
monthly, shares -- and the codebook tells researchers to take whichever
suits them. That is a promise that the two are interchangeable, and until
now nothing checked it.

It is the two-copies-of-the-palette defect in its most expensive form.
When a stylesheet and its duplicate drift, a chart goes grey. When
history.csv and history.json drift, two people cite IGRM for the same day
and get different numbers, and neither can tell which of them is wrong --
including us, because both files are "published output".

Measured on 2026-08-07: 3,305 days x 6 columns, zero mismatches, and
latest.json agrees with the final row of the CSV. Nothing was broken.
The point is that nothing was CHECKING, and the pipeline writes these
files from separate code paths.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data"

CHANNELS = ["pakistan_west", "china_east", "gulf_energy", "us_trade", "shipping"]
COLUMNS = CHANNELS + ["composite"]


def _csv_rows(name: str) -> dict[str, dict[str, str]]:
    with (DATA / name).open(encoding="utf-8") as fh:
        return {r["date"]: r for r in csv.DictReader(fh)}


def _num(v) -> float | None:
    if v is None or v == "":
        return None
    return float(v)


def test_history_csv_and_json_are_the_same_series():
    rows = _csv_rows("history.csv")
    hj = json.loads((DATA / "history.json").read_text(encoding="utf-8"))

    assert len(hj["dates"]) == len(rows), (
        f"history.json has {len(hj['dates'])} dates, history.csv has "
        f"{len(rows)} rows")

    bad = []
    for i, day in enumerate(hj["dates"]):
        row = rows.get(day)
        if row is None:
            bad.append(f"{day}: in json, not in csv")
            continue
        for col in COLUMNS:
            j = (hj["composite"][i] if col == "composite"
                 else hj["channels"][col][i])
            c = _num(row.get(col))
            if j is None and c is None:
                continue
            if j is None or c is None or abs(j - c) > 1e-9:
                bad.append(f"{day} {col}: json={j} csv={c}")
    assert not bad, (
        f"{len(bad)} disagreements between history.json and history.csv, "
        f"first few: {bad[:5]}. Two people citing the same day would get "
        "different numbers.")


def test_latest_json_agrees_with_the_last_row_of_the_csv():
    """latest.json is what most API consumers read. If it drifts from the
    series, the headline number and the downloadable history disagree
    about today."""
    rows = _csv_rows("history.csv")
    lj = json.loads((DATA / "latest.json").read_text(encoding="utf-8"))
    day = lj["date"]
    assert day in rows, f"latest.json publishes {day}, absent from history.csv"

    row = rows[day]
    assert abs(lj["composite"] - _num(row["composite"])) < 1e-9, (
        f"latest.json composite {lj['composite']} vs history.csv "
        f"{row['composite']} on {day}")

    bad = []
    for ch, obj in (lj.get("channels") or {}).items():
        score = obj["score"] if isinstance(obj, dict) else obj
        want = _num(row.get(ch))
        if score is None or want is None or abs(score - want) > 1e-9:
            bad.append(f"{ch}: latest={score} csv={want}")
    assert not bad, f"latest.json disagrees with history.csv on {day}: {bad}"


def test_the_last_csv_row_is_the_day_latest_claims():
    """A latest.json pointing at an older day than the CSV holds means the
    headline is stale while the download is fresh -- the failure nobody
    notices, because the page still shows a plausible number."""
    rows = _csv_rows("history.csv")
    lj = json.loads((DATA / "latest.json").read_text(encoding="utf-8"))
    assert lj["date"] == max(rows), (
        f"latest.json says {lj['date']} but history.csv runs to "
        f"{max(rows)}; the headline and the download disagree about which "
        "day is current")


def test_every_paired_payload_has_both_formats():
    """The pairing itself is the promise. A CSV whose JSON vanished (or
    the reverse) breaks whichever half of the audience used it."""
    missing = []
    for stem in ("history", "episodes", "event_study", "monthly", "shares"):
        for ext in ("csv", "json"):
            if not (DATA / f"{stem}.{ext}").exists():
                missing.append(f"{stem}.{ext}")
    assert not missing, f"published pairs broken: {missing}"


def test_episodes_csv_and_json_hold_the_same_episodes():
    rows = list(csv.DictReader((DATA / "episodes.csv").open(encoding="utf-8")))
    ej = json.loads((DATA / "episodes.json").read_text(encoding="utf-8"))
    assert isinstance(ej, list), "episodes.json is no longer a bare array"
    assert len(rows) == len(ej), (
        f"episodes.csv has {len(rows)} rows, episodes.json has {len(ej)}")

    keyed_csv = {(r["channel"], r["start"], r["end"]) for r in rows}
    keyed_json = {(e["channel"], e["start"], e["end"]) for e in ej}
    assert keyed_csv == keyed_json, (
        "the two episode files describe different episodes; symmetric "
        f"difference: {sorted(keyed_csv ^ keyed_json)[:5]}")
