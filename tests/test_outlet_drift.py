"""Outlet drift (F15): the Jaccard matrices are honest matrices.

Arithmetic-consistency checks on the SHIPPED payload (bounds, symmetry,
diagonal), a cardinality guard so the product cannot go vacuous
quietly, and payload == compute() so the published file is exactly what
the committed day-caches produce. No page-prose assertions: no page
exists for this payload yet.
"""
from __future__ import annotations

import json
from pathlib import Path

from src import outlet_drift, receipts_ngrams

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "docs" / "data" / "outlet_drift.json"


def _payload() -> dict:
    return json.loads(PAYLOAD.read_text(encoding="utf-8"))


def test_outlet_sets_use_anchor_arithmetic(monkeypatch):
    """Same fixture shape as spike_breadth's test: the anchor drops the
    un-anchored article, and www.alpha / alpha collapse to one domain."""
    monkeypatch.setattr(receipts_ngrams, "CHANNELS", ["ch"])
    monkeypatch.setattr(
        receipts_ngrams, "group_specs",
        lambda: {"ch/q1": {"channel": "ch", "anchor": "india",
                           "phrases": []}})
    cache = {
        "matched": {"ch/q1": ["t:1", "t:2", "t:3"]},
        "india": ["t:1", "t:2"],  # t:3 fails the anchor and must drop
        "meta": {
            "t:1": {"url": "https://www.alpha.example/a"},
            "t:2": {"url": "https://alpha.example/b"},  # same domain
            "t:3": {"url": "https://beta.example/c"},
        },
    }
    sets = outlet_drift.day_outlet_sets(cache)
    assert sets == {"ch": {"alpha.example"},
                    "overall": {"alpha.example"}}


def test_jaccard_arithmetic():
    assert outlet_drift.jaccard({"a", "b"}, {"b", "c"}) == round(1 / 3, 4)
    assert outlet_drift.jaccard({"a"}, {"a"}) == 1.0
    assert outlet_drift.jaccard({"a"}, {"b"}) == 0.0
    assert outlet_drift.jaccard(set(), {"a"}) is None
    assert outlet_drift.jaccard(set(), set()) is None


def test_matrices_bounded_symmetric_unit_diagonal():
    p = _payload()
    days = p["days"]
    n = len(days)
    for name, block in p["channels"].items():
        m = block["jaccard"]
        assert len(m) == n and all(len(row) == n for row in m), name
        for i in range(n):
            for j in range(n):
                v = m[i][j]
                assert v is None or 0.0 <= v <= 1.0, (name, i, j, v)
                assert m[i][j] == m[j][i], (name, i, j)
        for i, day in enumerate(days):
            if block["n_outlets"][day] > 0:
                assert m[i][i] == 1.0, (name, day)
            else:
                assert m[i][i] is None, (name, day)


def test_null_exactly_where_a_set_is_empty():
    p = _payload()
    days = p["days"]
    for name, block in p["channels"].items():
        for i, di in enumerate(days):
            for j, dj in enumerate(days):
                empty = (block["n_outlets"][di] == 0
                         or block["n_outlets"][dj] == 0)
                assert (block["jaccard"][i][j] is None) == empty, (
                    name, di, dj)


def test_cardinality_not_vacuous():
    p = _payload()
    days = p["days"]
    cov = p["_meta"]["coverage"]
    assert cov["n_units"] == len(days) >= 2
    assert cov["first_day"] == days[0]
    assert cov["last_day"] == days[-1]
    assert days == sorted(days)
    assert set(p["n_samples"]) == set(days)
    # Every registered channel appears, plus the overall union, and the
    # overall set is non-empty on every archived day: an all-empty day
    # would mean the cache shape changed under this module.
    assert set(p["channels"]) == set(receipts_ngrams.CHANNELS) | {
        outlet_drift.OVERALL}
    overall = p["channels"][outlet_drift.OVERALL]["n_outlets"]
    assert all(overall[d] > 0 for d in days)


def test_adjacent_day_summary_matches_matrix():
    p = _payload()
    days = p["days"]
    for name, s in p["adjacent_day"].items():
        m = p["channels"][name]["jaccard"]
        vals = [m[i][i + 1] for i in range(len(days) - 1)
                if m[i][i + 1] is not None]
        assert s["n_pairs"] == len(vals), name
        if vals:
            assert s["mean"] == round(sum(vals) / len(vals), 4), name
            assert s["min"] == min(vals) and s["max"] == max(vals), name
        else:
            assert s["mean"] is None


def test_payload_equals_compute():
    """Scoped to the payload's OWN day list. The staging boundary banks
    a new raw day-cache while refusing the regenerated payload on a
    failed run, so disk legitimately holds more days than the payload
    between a failure and the next green run -- that lag belongs to
    freshness.py. Unscoped, this test reddened every evidence commit
    and all three morning shots (cross-review 2026-08-08, proven with
    one extra cache day). Rewrites still fail loud: compute() refuses
    a day list the archive no longer holds."""
    disk = _payload()
    disk["_meta"].pop("generated")
    assert disk == outlet_drift.compute(only_days=disk["days"])
