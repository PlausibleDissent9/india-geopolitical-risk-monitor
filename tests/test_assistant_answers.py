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
    # Assert the payload is fetched, not the exact call spelling: the
    # first version pinned 'fetch("data/assistant_answers.json")' and
    # broke the moment a cache option was added -- brittle-string class.
    assert re.search(r'fetch\(\s*"data/assistant_answers\.json"', page)
    assert "no-store" in page, (
        "the nightly answer set must not be served from cache; a stale "
        "copy pairs yesterday's answers with today's scores")
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
    # Self-hosted-only, enforced against an EXACT allowlist rather than
    # by stripping prefixes. The prefix form -- .replace("https://igrm.in",
    # "") -- also silently accepted https://igrm.in.example.com/evil.js,
    # which is the one string this assertion most needs to reject.
    #
    # GDELT's link is on the list because its terms grant unlimited use
    # on a single condition: that any USE of the data cite the GDELT
    # Project and link https://www.gdeltproject.org/. IGRM is built on
    # GDELT, so the condition binds this page, and a licence obligation
    # outranks a self-imposed layout rule. The accommodation is one exact
    # URL, not a relaxation to "any external origin": pulling in
    # third-party content or linking out to unaudited claims -- what the
    # rule was written to prevent -- is still refused.
    ALLOWED = {"https://igrm.in/ask.html", "https://www.gdeltproject.org/"}
    origins = set(re.findall(r"https://[^\"'<> ]*", page))
    assert origins <= ALLOWED, (
        f"external origin on a self-hosted page: {sorted(origins - ALLOWED)}")


def test_the_page_is_in_the_sitemap():
    sitemap = (ROOT / "docs" / "sitemap.xml").read_text(encoding="utf-8")
    assert "ask.html" in sitemap

def test_the_page_router_refuses_what_the_planner_refuses():
    """The page claims "the same routing rules as the repository's
    evidence-locked assistant". It checked channels before the
    forbidden set, so "compare china and pakistan, which should I buy"
    was answered as a plain comparison with the advice refusal silently
    dropped -- the page more permissive than the instrument it mirrors.

    The planner tests _FORBIDDEN first; so must the page. This pins the
    precedence and the pattern parity, because the two live in
    different languages and drift silently."""
    import re as _re

    from src import evidence_assistant as ea

    page = PAGE.read_text(encoding="utf-8")
    js = _re.search(r"var FORBIDDEN = /\\b\(([^)]+)\)\\b/", page)
    assert js, "the page no longer tests a forbidden set before routing"
    page_terms = set(js.group(1).split("|"))
    planner_terms = set(
        _re.search(r"\\b\(([^)]+)\)\\b", ea._FORBIDDEN.pattern).group(1)
        .replace("\n", "").split("|"))
    assert page_terms == planner_terms, (
        f"page and planner forbidden sets diverged: "
        f"page-only {sorted(page_terms - planner_terms)}, "
        f"planner-only {sorted(planner_terms - page_terms)}")

    router = page.index("function route(")
    forbidden_at = page.index("if (FORBIDDEN.test(t))", router)
    for later in ("_CHANNEL", "hits.length", "compare &&"):
        idx = page.find(later, router)
        if idx != -1:
            assert forbidden_at < idx, (
                "a routing rule is tested before the forbidden set; the "
                "planner tests forbidden first and the page must too")
