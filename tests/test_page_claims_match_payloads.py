"""Numbers written in prose must still be true of the files they came from.

The codebook and the methodology are the two documents that claim to be
authoritative, and both hand-type numbers a nightly lane recomputes:

    "10 of 12 vintages show zero changed values"      vintages.json
    "19,830 of 19,830 published values exactly"       replication.json
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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
DATA = DOCS / "data"


def _page(name: str) -> str:
    return DOCS.joinpath(name).read_text(encoding="utf-8")


def _payload(name: str) -> dict:
    return json.loads(DATA.joinpath(name).read_text(encoding="utf-8"))


def _says(page: str, *variants: str) -> bool:
    """Prose writes 19,830; JSON says 19830. Accept either."""
    text = _page(page)
    return any(v in text for v in variants)


def test_the_vintage_count_on_the_codebook_is_current():
    m = _payload("vintages.json")["_meta"]
    clean, total = m["n_vintages_clean"], m["n_vintages"]
    assert _says("codebook.html", f"{clean} of {total} vintages"), (
        f"vintages.json now reports {clean} of {total} clean vintages; the "
        "codebook still states an older pair. This count grows every time a "
        "publish rewrites history.csv, so it goes stale on its own.")


def test_the_replication_count_on_the_codebook_is_current():
    b = _payload("replication.json")["best"]
    n, total = b["n_agree"], b["n_compared"]
    assert _says("codebook.html", f"{n:,} of {total:,}", f"{n} of {total}"), (
        f"replication.json reports {n:,} of {total:,}; the codebook says "
        "something else. This is the strongest claim on the site and the "
        "one most worth keeping exactly true.")


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
