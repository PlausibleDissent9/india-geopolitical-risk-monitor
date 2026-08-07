"""The decision queue must be a program, not a list.

The whole point of `src/decisions.py` is that no item is marked done by
hand. If an item's predicate does not actually read the repository, it is
a to-do list with extra steps -- and a to-do list is the artifact this
project keeps finding stale and deleting.

So: every item has a predicate, every predicate is exercised, and the
ones asserting a specific number are checked against the file that holds
it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from src import decisions

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def test_every_item_has_a_working_predicate():
    assert decisions.ITEMS, "the queue is empty"
    for item in decisions.ITEMS:
        assert callable(item.get("predicate")), (
            f"{item['id']} has no predicate; an item nobody can check does "
            "not belong on this page")
        blocked, detail = item["predicate"]()
        assert isinstance(blocked, bool), f"{item['id']} predicate is not a bool"
        assert detail and isinstance(detail, str), (
            f"{item['id']} gives no detail; the founder sees this string, so "
            "it must carry the number rather than an adjective")


def test_each_item_says_why_only_the_founder_can_do_it():
    """The queue is for authority, not labour. If an agent could do it, it
    belongs in a workflow, not on this page."""
    for item in decisions.ITEMS:
        assert item.get("why_only_you"), f"{item['id']} does not justify its place"
        assert item.get("why_it_matters"), f"{item['id']} does not say why it matters"


def test_the_predicates_agree_with_the_files_they_read():
    """Spot-check two against their sources. A predicate that reports a
    number it did not read is the failure this file exists to prevent."""
    blocked, detail = decisions._calibration_incomplete()
    p = json.loads((ROOT / "docs" / "data" / "precision.json").read_text(
        encoding="utf-8"))
    n, need = p["author_labels_n"], p["calibration_threshold"]
    assert blocked == (n < need)
    if blocked:
        assert f"{n} of {need}" in detail, (
            f"the detail says {detail!r} but precision.json says {n} of {need}")

    blocked, _ = decisions._doi_missing()
    has_doi = bool(re.search(r"^doi:", (ROOT / "CITATION.cff").read_text(
        encoding="utf-8"), re.M | re.I))
    assert blocked != has_doi


def test_an_item_clears_itself_when_the_fact_changes(tmp_path, monkeypatch):
    """The property that makes this a program: nobody edits a file to mark
    something done. Simulated by pointing the reader at a CITATION.cff
    that HAS a DOI and checking the item goes quiet on its own."""
    fake = tmp_path
    (fake / "CITATION.cff").write_text(
        'cff-version: 1.2.0\ndoi: 10.5281/zenodo.9999999\n', encoding="utf-8")
    monkeypatch.setattr(decisions, "ROOT", fake)
    blocked, detail = decisions._doi_missing()
    assert blocked is False, "the DOI item did not clear itself once minted"
    assert "10.5281/zenodo.9999999" in detail


def test_the_queue_runs_in_the_lane_and_before_the_stamp():
    daily = (WORKFLOWS / "daily.yml").read_text(encoding="utf-8")
    order = re.findall(r"python -m src\.(\w+)", daily)
    assert "decisions" in order, (
        "the decision queue is in no workflow, so it would freeze at "
        "whatever it said the day it was written -- which is precisely the "
        "stale-list failure it exists to avoid")
    assert order.index("decisions") < order.index("stamp_meta"), (
        "decisions writes a payload and must run before the stamp step")


def test_the_page_is_reachable():
    linkers = [p.name for p in sorted((ROOT / "docs").glob("*.html"))
               if p.name != "decisions.html"
               and 'href="decisions.html"' in p.read_text(encoding="utf-8")]
    assert "index.html" in linkers and len(linkers) >= 20, (
        f"only {len(linkers)} pages link to decisions.html")
