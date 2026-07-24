"""The composed GDELT queries must stay within the DOC API's grammar:
one un-nested paren group, OR only inside it, anchor AND'ed outside."""
from __future__ import annotations

import json
from pathlib import Path

from src.fetch_gdelt import build_query

ROOT = Path(__file__).resolve().parents[1]


def test_real_queries_are_grammatical():
    with open(ROOT / "dictionaries.json", "r", encoding="utf-8") as f:
        d = json.load(f)
    for ch, spec in d.items():
        if ch.startswith("_"):
            continue
        q = build_query(spec["terms"], spec.get("anchor"))
        assert q.count("(") == 1 and q.count(")") == 1, f"{ch}: nested parens"
        assert q.endswith(")"), f"{ch}: anchor must precede the group"
        inside = q[q.index("(") + 1:q.rindex(")")]
        outside = q[:q.index("(")]
        assert " OR " not in outside, f"{ch}: OR outside parens"
        for piece in inside.split(" OR "):
            assert piece.startswith('"') and piece.endswith('"'), (
                f"{ch}: {piece!r} mixes AND into the OR group"
            )


def test_anchor_composition():
    assert build_query(['"a b"', '"c"']) == '("a b" OR "c")'
    assert build_query(['"a b"'], anchor="India") == 'India ("a b")'
