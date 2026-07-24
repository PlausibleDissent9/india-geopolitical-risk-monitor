"""The composed GDELT queries must stay within the DOC API's grammar
(one un-nested paren group, OR only inside it, anchor AND'ed outside)
AND its measured length budget (QUERY_MAX_CHARS)."""
from __future__ import annotations

import json
from pathlib import Path

from src.fetch_gdelt import QUERY_MAX_CHARS, build_queries, build_query

ROOT = Path(__file__).resolve().parents[1]

DICT_FILES = ["dictionaries.json", "dictionaries_alt.json", "dictionaries_placebo.json"]


def _specs():
    for name in DICT_FILES:
        with open(ROOT / name, encoding="utf-8") as f:
            d = json.load(f)
        stack = [(name, d)]
        while stack:
            where, node = stack.pop()
            for k, v in node.items():
                if k.startswith("_"):
                    continue
                if isinstance(v, dict) and "terms" in v:
                    yield f"{where}:{k}", v
                elif isinstance(v, dict):
                    stack.append((f"{where}:{k}", v))


def test_real_queries_are_grammatical_and_within_budget():
    for where, spec in _specs():
        queries = build_queries(spec["terms"], spec.get("anchor"))
        seen_terms: list[str] = []
        for q in queries:
            assert len(q) <= QUERY_MAX_CHARS, f"{where}: {len(q)} chars"
            assert q.count("(") == 1 and q.count(")") == 1, f"{where}: nested parens"
            assert q.endswith(")"), f"{where}: anchor must precede the group"
            assert " OR " not in q[:q.index("(")], f"{where}: OR outside parens"
            for piece in q[q.index("(") + 1:q.rindex(")")].split(" OR "):
                assert piece.startswith('"') and piece.endswith('"'), (
                    f"{where}: {piece!r} mixes AND into the OR group"
                )
                seen_terms.append(piece)
        assert seen_terms == spec["terms"], f"{where}: partition altered terms"


def test_anchor_composition():
    assert build_query(['"a b"', '"c"']) == '("a b" OR "c")'
    assert build_query(['"a b"'], anchor="India") == 'India ("a b")'


def test_partition_splits_long_channels():
    terms = [f'"term number {i}"' for i in range(20)]
    queries = build_queries(terms)
    assert len(queries) > 1
    assert all(len(q) <= QUERY_MAX_CHARS for q in queries)
