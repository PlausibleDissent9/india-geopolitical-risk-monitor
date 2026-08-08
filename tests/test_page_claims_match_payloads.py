"""Numbers written in prose must still be true of the files they came from.

The codebook and the methodology are the two documents that claim to be
authoritative, and both hand-type numbers a nightly lane recomputes:

    "10 of 12 vintages show zero changed values"      vintages.json
    "every published ... score cell must match"        replication.json
    "24 of 29 (83%)"                                  validation.json
    "5 of 5 channels"                                 wiki_hindi.json

Every one of them was correct when typed. That is exactly the problem:
so was "one easing", so was "the licence appears in every payload", so
was the spacing scale this document described. A number that was true
when written and is recomputed by something else every night is a stale
claim with a delay fuse in it -- and these sit on the pages a referee
would check first.

`n_vintages` in particular grows whenever a publish rewrites
history.csv. The page says twelve. Nothing but this file will notice
when it is thirteen.

Where a prose number is a DATED LEDGER ENTRY it is left alone, and the
distinction matters: corrections.html records "the gauge scored 1 of 21"
under a 2026-07-31 heading. That was true on 2026-07-31, the gauge now
scores 2 of 29, and updating the ledger would be falsifying a record
rather than fixing a claim. History is not stale; it is history.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
DATA = DOCS / "data"


def _page(name: str) -> str:
    return DOCS.joinpath(name).read_text(encoding="utf-8")


def _payload(name: str) -> dict:
    return json.loads(DATA.joinpath(name).read_text(encoding="utf-8"))


def _says(page: str, *variants: str) -> bool:
    """Prose may use thousands separators while JSON does not."""
    text = _page(page)
    return any(v in text for v in variants)


def test_the_vintage_count_on_the_codebook_is_current():
    m = _payload("vintages.json")["_meta"]
    clean, total = m["n_vintages_clean"], m["n_vintages"]
    assert _says("codebook.html", f"{clean} of {total} vintages"), (
        f"vintages.json now reports {clean} of {total} clean vintages; the "
        "codebook still states an older pair. This count grows every time a "
        "publish rewrites history.csv, so it goes stale on its own.")


def test_the_replication_claim_requires_the_full_published_denominator():
    b = _payload("replication.json")["best"]
    assert b["n_published"] == b["n_compared"] == b["n_agree"]
    assert b["n_missing"] == 0

    text = _page("codebook.html")
    assert "Every published daily channel and composite score cell must match" in text
    assert "missing reconstructed cells count as failures" in text
    assert "data/replication.json" in text
    assert "19,830 of 19,830" not in text


def test_reproduction_collateral_never_upgrades_the_public_score_proof_to_full_pipeline():
    surfaces = [
        "README.md",
        "GOVERNANCE.md",
        "REPLICATION.md",
        ".github/ISSUE_TEMPLATE/adversarial-review.md",
        "listings/dbnomics_submission.md",
        "nef/REVIEWERS_GUIDE.md",
        "paper/IGRM_paper_v1.md",
        "paper/WORKING_PAPER.md",
        "paper/founder_interview.md",
    ]
    stale_claims = [
        "full reproducibility from a clean checkout",
        "complete reproducibility, including the raw store",
        "rebuilds every published payload",
        "fresh clone rebuilds every published number",
        "pipeline reproduces from a clean checkout",
        "19,830 of 19,830",
        "within a documented 0.06 band",
        "market-vintage tolerance",
    ]
    violations = []
    for relative in surfaces:
        text = (ROOT / relative).read_text(encoding="utf-8").lower()
        for claim in stale_claims:
            if claim.lower() in text:
                violations.append(f"{relative}: {claim}")
    assert not violations, (
        "Public score-cell reconstruction was inflated into full-pipeline "
        f"reproduction: {violations}"
    )


def test_the_hit_rate_in_the_methodology_is_current():
    h = _payload("validation.json")["hit_rate"]["overall"]
    hits, n = h["hits"], h["n"]
    assert _says("methodology.html", f"{hits} of {n}"), (
        f"validation.json reports {hits} of {n} episodes detected; "
        "methodology.html states a different pair.")

    pct = round(100 * hits / n)
    assert f"{pct}%" in _page("methodology.html"), (
        f"the stated percentage does not match {hits}/{n} = {pct}%")


def test_the_language_gap_claim_matches_the_measurement():
    ch = _payload("wiki_hindi.json")["channels_where_english_leads_on_both"]
    n = len(ch)
    total = len(_payload("wiki_hindi.json")["channels"])
    assert _says("codebook.html", f"{n} of {total} channels"), (
        f"English leads Hindi on {n} of {total} channels; the codebook "
        "states a different pair. This is the finding that qualifies what "
        "the index measures, so it has to be exact.")


def test_the_gauge_number_in_the_ledger_is_left_alone():
    """The opposite rule, and it is deliberate.

    corrections.html records under a 2026-07-31 heading that the gauge
    scored 1 of 21. The gauge now scores 2 of 29. The ledger entry must
    NOT be updated: it is a dated record of what was true and published
    that day, and rewriting it to match today would turn a corrections
    log into a fiction. This test exists so nobody 'fixes' it later --
    including me, since I checked it as a suspected stale number today.
    """
    text = _page("corrections.html")
    assert "2026-07-31: gauge validation scored 1 of 21" in text, (
        "the dated gauge ledger entry has been altered. A corrections log "
        "that is edited to agree with the present is not a corrections log.")

    live = _payload("stress_gauge.json")["validation"]
    assert (live["n_detected"], live["n_episodes"]) != (1, 21), (
        "the gauge has returned to 1 of 21, so this test's premise -- that "
        "the ledger entry is history rather than the current number -- "
        "needs rechecking rather than asserting.")


def test_current_dictionary_and_receipts_prose_follow_the_live_rules():
    """The current-method sections must not preserve superseded V1 rules."""
    dictionary = json.loads((ROOT / "dictionaries.json").read_text())
    shipping_terms = set(dictionary["shipping"]["terms"])
    assert '"maritime security"' not in shipping_terms

    method = (ROOT / "methodology.md").read_text(encoding="utf-8")
    current_dictionary = method.split("**Cross-channel bleed", 1)[0]
    assert "Two generic phrases" in current_dictionary
    assert 'and `"maritime security"`' not in current_dictionary

    from src import receipts, receipts_ngrams
    for page in (method, _page("methodology.html")):
        assert f"up to {receipts_ngrams.MAX_PUBLISHED}" in page
        assert f"at most {receipts.MAX_ARTICLES_PUBLISHED}" in page
        assert "capped at 25 per channel" not in page


def test_predictability_prose_uses_the_payload_without_copying_nightly_pvalues():
    pairs = _payload("predictability.json")["pairs"]
    salience_leads = [v["p_permutation"] for k, v in pairs.items()
                      if k.startswith("salience_leads_")]
    assert salience_leads and min(salience_leads) >= 0.05
    for page in ((ROOT / "methodology.md").read_text(encoding="utf-8"),
                 _page("methodology.html")):
        section = page.split("The predictability study", 1)[1]
        section = section.split("Receipts and source tiers", 1)[0]
        normalized = " ".join(section.split())
        assert "no salience-leading direction clears" in normalized
        assert "Exact values live in" in normalized
        assert not re.search(r"p 0\.\d+", normalized)


def test_citation_break_page_and_freshness_copy_follow_their_sources():
    cff = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    version = re.search(r'^version:\s*"?([^"\n]+)', cff, re.M).group(1)
    data_page = _page("data.html")
    bib = (DOCS / "igrm.bib").read_text()
    assert f"Version {version}" in data_page
    assert f"Version {version}" in bib
    page_title = re.search(
        r"(India Geopolitical Risk Monitor: .+?)\. Version", data_page,
        re.S).group(1)
    bib_title = re.search(r"title\s*=\s*\{(.+?)\},", bib, re.S).group(1)
    assert " ".join(page_title.split()) == " ".join(bib_title.split())

    n_episodes = _payload("validation.json")["hit_rate"]["overall"]["n"]
    assert f"{n_episodes} pre-registered episodes" in _page("break.html")

    codebook = _page("codebook.html")
    normalized = " ".join(codebook.split())
    assert "this watches every payload" in normalized
    assert "enumerated in <code>freshness.json</code>" in normalized
    assert not re.search(r"watches all\s*~?\d+\s*<em>payloads", codebook)
