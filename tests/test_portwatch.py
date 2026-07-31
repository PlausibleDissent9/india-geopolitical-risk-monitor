"""PortWatch upsert: revisions win, order is stable, nothing is lost."""
from __future__ import annotations

from src.fetch_portwatch import upsert


def test_upsert_revises_and_sorts():
    existing = [
        {"date": "2026-07-01", "chokepoint": "suez", "n_total": 40,
         "n_tanker": 15, "n_cargo": 25, "capacity": 1},
        {"date": "2026-07-02", "chokepoint": "suez", "n_total": 41,
         "n_tanker": 16, "n_cargo": 25, "capacity": 1},
    ]
    new = [
        # revision of an existing day
        {"date": "2026-07-02", "chokepoint": "suez", "n_total": 44,
         "n_tanker": 18, "n_cargo": 26, "capacity": 2},
        # a new day, and a second chokepoint on an old day
        {"date": "2026-07-03", "chokepoint": "suez", "n_total": 39,
         "n_tanker": 14, "n_cargo": 25, "capacity": 1},
        {"date": "2026-07-01", "chokepoint": "hormuz", "n_total": 70,
         "n_tanker": 45, "n_cargo": 25, "capacity": 3},
    ]
    out = upsert(existing, new)
    assert len(out) == 4
    assert [(r["date"], r["chokepoint"]) for r in out] == [
        ("2026-07-01", "hormuz"), ("2026-07-01", "suez"),
        ("2026-07-02", "suez"), ("2026-07-03", "suez"),
    ]
    assert out[2]["n_total"] == 44  # the revision won
