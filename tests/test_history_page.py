"""Every number written on history.html must still be true of the data.

The 1979-2019 page is prose wrapped around a payload, and prose does not
recompute itself. This project has now shipped four sentences that were
true when typed and false later -- "one easing", "four durations", "the
licence appears in every payload", "spacing rhythm" -- so a page making
this many specific claims gets its claims checked against the file it
describes.

Two of the claims here were WRONG when first written and were caught by
measuring rather than by rereading:

  * "the first ten years are blank ... nothing to rank against until
    1989". The series actually begins 1983-12; the window reports after
    sixty months, not a hundred and twenty.
  * the 28-month hole at the GDELT 1.0/2.0 seam was not mentioned at
    all, which would have left a visible break in the middle of the
    chart with no explanation on a page whose entire argument is that
    nothing here is hidden.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "history.html"
PAYLOAD = ROOT / "docs" / "data" / "back_extension.json"

MONTHS = [None, "January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def _data() -> dict:
    return json.loads(PAYLOAD.read_text(encoding="utf-8"))


def test_the_overlap_thresholds_quoted_match_the_registration():
    """The page says 'publishes only if r >= 0.6' and 'below 0.4 it does
    not publish at all'. Those are the memo's frozen thresholds, and if
    the module's thresholds ever move, the page becomes a
    misdescription of a pre-registration -- the worst kind of stale
    sentence this project could ship."""
    from src.back_extension import OVERLAP_THRESHOLDS
    page = _page()
    assert f"{OVERLAP_THRESHOLDS['tracks']}" in page, (
        f"the page does not quote the registered 'tracks' threshold "
        f"({OVERLAP_THRESHOLDS['tracks']})")
    assert f"{OVERLAP_THRESHOLDS['partial']}" in page, (
        f"the page does not quote the registered 'partial' threshold "
        f"({OVERLAP_THRESHOLDS['partial']})")


def test_only_channels_that_cleared_the_bar_have_a_series():
    """The publication rule, checked against the payload rather than
    trusted. A channel with a series but a failing correlation would be
    the exact thing the registration existed to prevent."""
    d = _data()
    tracks = 0.6
    for ch, audit in d["overlap_audit"].items():
        has_series = ch in d["series"]
        if audit["r"] >= tracks:
            assert has_series, f"{ch} cleared r={audit['r']} but has no series"
        else:
            assert not has_series, (
                f"{ch} publishes a historical series on r={audit['r']}, "
                f"below the registered threshold of {tracks}. The negative "
                "finding IS the result; publishing anyway retracts it.")


def test_the_anchor_score_is_reported_honestly():
    """Six of nine. Reported over nine and not over eight, because
    dropping the mis-specified Blue Star anchor after seeing it fail is
    choosing the denominator from the answer."""
    d = _data()
    grades = d["anchor_grades"]
    passed = sum(1 for g in grades if g["top_decile"])
    page = _page()
    assert len(grades) == 9 and passed == 6, (
        f"the anchor result moved to {passed} of {len(grades)}; the page "
        "still says six of nine")
    assert "six of nine" in page.lower(), (
        "the page no longer states the anchor score in words")
    # An `assert "six of eight" not in page` stood here and FAILED on
    # correct prose: the page contains that phrase inside the sentence
    # explaining why the score is not reported that way. A banned-
    # substring check cannot tell a claim from a discussion of the
    # claim, and a test that fires on the right answer trains people to
    # ignore it. The assertion above -- the reported ratio must equal
    # the computed one -- is the check that actually has teeth.


def test_the_series_start_and_the_source_seam_are_stated_correctly():
    """Both of these were wrong or missing in the first draft."""
    d = _data()
    page = _page()
    for ch, series in d["series"].items():
        months, vals = series["months"], series["pctl_10y"]
        first = next(i for i, v in enumerate(vals) if v is not None)
        start = months[first]
        # Prose writes "December 1983"; the payload says "1983-12".
        # Accept either, because forcing the ISO form into a sentence
        # would be a test dictating style rather than checking a fact.
        year, month = start.split("-")
        long_form = f"{MONTHS[int(month)]} {year}"
        assert start in page or long_form in page, (
            f"{ch} begins {start} ({long_form}), which the page does not "
            "say. The first draft claimed 1989 by reasoning about a "
            "ten-year window instead of reading the series.")

        interior = [months[i] for i in range(first, len(vals))
                    if vals[i] is None]
        if interior:
            assert str(len(interior)) in page, (
                f"{ch} has a {len(interior)}-month interior gap starting "
                f"{interior[0]}, and the page does not account for it. An "
                "unexplained break in the middle of the chart is the one "
                "thing this page cannot afford.")
            assert interior[0] in page or interior[0][:4] in page, (
                f"the gap starts {interior[0]} and the page does not say so")


def test_the_page_never_invites_splicing():
    """The construct is different and the memo forbids joining it to the
    live index. A page that hedges on this is how somebody ends up with
    a forty-year 'IGRM' line in a slide deck."""
    page = _page().lower()
    assert "never spliced" in page or "not the index extended" in page, (
        "the page does not state that this series must not be joined to "
        "the live index")
    # No forecast language, same rule as everywhere else.
    # "will rise"/"will fall" were in this list and are ordinary English:
    # a DISCLAIMER ("does not say the index will rise") would trip them.
    # The audit found this file already contains a five-line comment about
    # exactly that failure, on the function directly above -- the lesson
    # was applied to one function and not its neighbour. Only phrases that
    # cannot appear in honest prose stay banned.
    for banned in ("we forecast", "predicts that"):
        assert banned not in page, f"forecast language on history.html: {banned}"


def test_the_page_is_reachable_from_the_rest_of_the_site():
    """An orphan page is a page nobody reads. This one is the biggest
    substantive artifact on the site and shipped linked from nothing at
    all until the nav was wired."""
    linkers = [p.name for p in sorted((ROOT / "docs").glob("*.html"))
               if p.name != "history.html"
               and re.search(r'href="history\.html"', p.read_text(encoding="utf-8"))]
    assert len(linkers) >= 20, (
        f"only {len(linkers)} pages link to history.html: {linkers}")
    assert "index.html" in linkers, "the front page does not link to it"


def test_every_current_description_names_the_full_published_range():
    data = _data()
    starts = [series["months"][0] for series in data["series"].values()]
    ends = [series["months"][-1] for series in data["series"].values()]
    label = f"{min(starts)[:4]}–{max(ends)[:4]}"
    ascii_label = label.replace("–", "-")
    surfaces = [
        data["_meta"]["what"],
        (ROOT / "docs" / "codebook.md").read_text(encoding="utf-8"),
        (ROOT / "docs" / "codebook.html").read_text(encoding="utf-8"),
        (ROOT / "docs" / "research" / "history.html").read_text(
            encoding="utf-8"),
    ]
    for surface in surfaces:
        assert label in surface or ascii_label in surface, (
            f"historical description does not name published range {label}")
