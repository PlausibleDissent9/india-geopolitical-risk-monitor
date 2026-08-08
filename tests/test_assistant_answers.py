"""Ask IGRM v0: the published answers must be the assistant's answers.

The page's entire claim is that no model wrote its text and every value
was verified at build time. That holds only if the payload is exactly
what src/evidence_assistant.py produces for the registered question
set -- a hand-edited answer would wear the evidence ledger of the
machine one.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from src import assistant_answers as aa

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "docs" / "data" / "assistant_answers.json"
PAGE = ROOT / "docs" / "ask.html"


def _payload() -> dict:
    return json.loads(PAYLOAD.read_text(encoding="utf-8"))


def test_the_payload_is_exactly_what_the_assistant_answers():
    disk = _payload()
    fresh = aa.build()
    assert [a["question"] for a in disk["answers"]] == \
        [a["question"] for a in fresh["answers"]]
    for d, f in zip(disk["answers"], fresh["answers"]):
        assert d["status"] == f["status"], d["question"]
        assert d["text"] == f["text"], d["question"]
        assert d["evidence"] == f["evidence"], d["question"]


def test_counts_are_derived_and_coherent():
    p = _payload()
    m = p["_meta"]
    answered = sum(1 for a in p["answers"] if a["status"] == "answered")
    refused = sum(1 for a in p["answers"] if a["status"] != "answered")
    assert m["n_answered"] == answered
    assert m["n_refused"] == refused
    assert m["n_questions"] == answered + refused == len(p["answers"])
    assert answered >= 1, "an all-refusal set must fail the build, not publish"
    assert refused >= 3, (
        "the deliberate refusal exemplars (forecast, advice, superiority) "
        "must stay published; refusals are part of the product")


def test_every_answer_is_grounded_and_every_refusal_is_coded():
    for a in _payload()["answers"]:
        if a["status"] == "answered":
            assert a["evidence"], f"answered without evidence: {a['question']}"
            assert a["refusal_code"] is None
        else:
            assert a["refusal_code"], f"refusal without code: {a['question']}"
            assert a["evidence"] == []


def test_no_forecast_language_in_any_published_text():
    for a in _payload()["answers"]:
        for banned in ("will rise", "will fall", "we forecast", "predicts that"):
            assert banned not in a["text"].lower(), a["question"]


def test_the_page_renders_the_payload_and_nothing_else():
    page = PAGE.read_text(encoding="utf-8")
    assert 'fetch("data/assistant_answers.json")' in page
    assert "no language model" in page.lower()
    assert 'id="ask-input"' in page, "the free-text ask box is the product"
    assert "Refusals are part of the product" in page
    assert "nothing is sent anywhere" in page.lower() or \
        "stays in your browser" in page.lower()
    # No hardcoded answer counts in the HTML source: the counts span is
    # a JS-filled placeholder (the stale-prose discipline from
    # analysis/prose_number_audit_2026-08-08.md).
    counts = re.search(r'id="counts"[^>]*>([^<]*)<', page)
    assert counts and not re.search(r"\d", counts.group(1))
    assert 'http-equiv="Content-Security-Policy"' in page
    assert "https://" not in re.sub(
        r'href="https://igrm\.in/ask\.html"', "", page).replace(
        "https://igrm.in", ""), "external origin on a self-hosted page"


def test_the_page_is_in_the_sitemap():
    sitemap = (ROOT / "docs" / "sitemap.xml").read_text(encoding="utf-8")
    assert "ask.html" in sitemap
