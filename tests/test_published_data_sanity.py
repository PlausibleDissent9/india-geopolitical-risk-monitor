"""Invariants on what the site actually serves.

Two classes of defect this catches, both found in this project rather
than imagined:

  * Bare NaN/Infinity. pandas returns NaN for an undefined correlation
    and json.dumps writes it as a bare token, which is NOT valid JSON --
    every strict parser rejects the whole file. wiki_hindi.json shipped
    that way for an hour on 2026-08-07.
  * Levels outside their range. A percentile is 0-100 by construction,
    so a value outside it means the transform broke, not that the world
    got louder.

The range checks are deliberately NARROW and named one by one. A first
draft matched any path containing "score" or "composite" and flagged
1,814 values -- all of them legitimate: score CHANGES are signed, the
attention-pricing GAP is a difference of two percentiles, and a "months"
count matched because its parent key was "composite". A check that cries
wolf gets deleted, so this one only asserts what it can actually
defend.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

SITE_DATA = Path(__file__).resolve().parents[1] / "docs" / "data"


def _strict(path: Path):
    """Parse rejecting NaN/Infinity, exactly as a strict client would."""
    def reject(const):
        raise ValueError(f"invalid JSON constant {const!r}")
    return json.loads(path.read_text(encoding="utf-8"),
                      parse_constant=reject)


def _payloads():
    return sorted(SITE_DATA.glob("*.json"))


def test_every_payload_is_strictly_valid_json():
    """Python's json accepts NaN; the JSON spec does not, and neither
    does Go, Rust, or a browser's JSON.parse. A payload that only
    Python can read is not a published dataset."""
    broken = []
    for p in _payloads():
        try:
            _strict(p)
        except ValueError as e:
            broken.append(f"{p.name}: {e}")
    assert not broken, f"payloads no strict JSON parser can read: {broken}"


def test_latest_scores_are_percentiles():
    d = _strict(SITE_DATA / "latest.json")
    for ch, blk in d["channels"].items():
        v = blk.get("score")
        if v is not None:
            assert 0 <= v <= 100, f"latest {ch} score {v} is not a percentile"
    for key in ("composite", "composite7"):
        v = d.get(key)
        if v is not None:
            assert 0 <= v <= 100, f"latest {key} {v} is not a percentile"


def test_history_series_stay_in_range_and_align():
    d = _strict(SITE_DATA / "history.json")
    dates = d["dates"]
    assert dates == sorted(dates), "history dates are not in order"
    assert len(set(dates)) == len(dates), "history has duplicate dates"
    series = {"composite": d["composite"]}
    series.update({k: v for k, v in (d.get("channels") or {}).items()})
    for name, vals in series.items():
        assert len(vals) == len(dates), (
            f"history {name} has {len(vals)} values for {len(dates)} dates")
        bad = [v for v in vals if v is not None and not 0 <= v <= 100]
        assert not bad, f"history {name} has non-percentile values: {bad[:5]}"


def test_shares_are_non_negative_percentages():
    """A share of a corpus cannot be negative, and a channel taking more
    than the whole corpus would mean the denominator broke."""
    import csv
    p = SITE_DATA / "shares.csv"
    if not p.exists():
        pytest.skip("shares.csv not built")
    with p.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    channels = [c for c in rows[0] if c not in ("date", "source")]
    for r in rows:
        for ch in channels:
            raw = r.get(ch)
            if not raw:
                continue
            v = float(raw)
            assert v >= 0, f"{r['date']} {ch} share is negative: {v}"
            assert v <= 100, f"{r['date']} {ch} share exceeds corpus: {v}"


def test_the_headline_day_is_not_in_the_future():
    """A published day ahead of the clock means a date-handling bug, and
    it would be quoted before anyone noticed."""
    from datetime import date, timedelta
    d = _strict(SITE_DATA / "latest.json")
    day = date.fromisoformat(d["date"])
    # One day of slack for UTC/IST straddling the boundary.
    assert day <= date.today() + timedelta(days=1), (
        f"latest.json publishes {day}, which is in the future")


def test_monthly_refusals_never_carry_values():
    """Pinned in its own module's tests too; repeated here against the
    served artifact, because that is what a user downloads."""
    import csv
    p = SITE_DATA / "monthly.csv"
    if not p.exists():
        pytest.skip("monthly.csv not built")
    with p.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("refused_reason"):
                vals = [v for k, v in r.items()
                        if k.startswith("share_") and v]
                assert not vals, (
                    f"{r['month']} was refused but still published "
                    f"{len(vals)} means")
