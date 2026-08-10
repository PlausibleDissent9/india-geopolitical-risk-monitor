"""The headline detection figure must travel with the baseline that deflates it.

WHAT THE SWEEP FOUND (2026-08-10)
`docs/data/detection_baselines.json` publishes four numbers over the same 29
registered episodes:

    registered corresponding-channel   24
    naive any-channel                  26
    strict start-based timing          19
    expected by chance                  6.8

A naive detector that asks only "did ANY channel move" scores TWO EVENTS
HIGHER than the registered one. So "24 of 29 (83%)" is not evidence that the
index detects events -- detection is cheap. It is evidence that the index
detects them in the RIGHT CHANNEL, which is the part the naive rule cannot do.

The sweep counted where each number appeared across the reader-facing surface:

    "24 of 29" / "24/29"    18 occurrences
    the naive baseline       3 of them

The flattering number was in both paper abstracts, the README, the
methodology, and both external dataset listings. The deflating one was in the
datasheet's negative-results section and one row of the reviewer's guide.
Nothing was false. Every sentence was individually defensible. The corpus as a
whole still read as a stronger result than the payload supports, because the
favourable number travelled and the unfavourable one did not.

That is the failure mode this file exists to catch, and it is not one a
banned-substring check can find: there is no bad word to grep for. The defect
is an ABSENCE, and it is only visible as a ratio.

WHY THE NUMBERS ARE READ FROM THE PAYLOAD
Hard-coding 26 here would mean that the day the payload changes, the prose
goes stale and this test keeps passing -- the exact "true when typed" fuse
`test_page_claims_match_payloads.py` was written about. So the expected
strings are derived from the payload. If a recomputation moves the baseline,
every prose site fails at once and names itself in the message. That is
correct: publishing last week's baseline beside this week's headline is the
harm.

THE PREMISE IS ALSO ASSERTED
The prose this file guards says the naive rule scores HIGHER. If that ever
stops being true, those sentences become false in the other direction, and a
test that only checked co-occurrence would happily keep enforcing a lie.
`test_the_naive_rule_still_beats_the_registered_one` fails in that case and
sends the writer back to the prose rather than letting it pass.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINES = ROOT / "docs" / "data" / "detection_baselines.json"

# How much room a sentence gets to bring its baseline along. Generous on
# purpose: the point is that a reader meets both numbers in the same breath,
# not that they sit in the same clause.
WINDOW = 1200

# Reader-facing prose. Generated payloads are excluded because they are not
# where a human reads a claim; their generators are in scope instead (see
# scripts/generate_api_contract.py, whose string machine-copies into both
# docs/data/api_contract.json and docs/openapi.json).
GLOBS = (
    "docs/*.html",
    "docs/*.md",
    "paper/*.md",
    "nef/*.md",
    "listings/*",
    "README.md",
    "methodology.md",
    "scripts/generate_api_contract.py",
)

# Sites where the headline figure appears WITHOUT its baseline and that is
# correct. Each entry is (file, anchoring snippet, argument).
#
# Anchored by SENTENCE rather than by line or by file, deliberately, and for
# two reasons. A file-wide exemption would also switch off enforcement on the
# sentences in that file that were fixed -- founder_interview.md holds both.
# A line number would drift silently. An anchor dies when the sentence it
# licenses is rewritten, which is exactly when the argument below needs
# re-reading. Same shape as KNOWN_VIOLATIONS in test_claims_discipline.py.
#
# This list is short on purpose: an exemption is an argument, not a backlog.
EXEMPT: tuple[tuple[str, str, str], ...] = (
    ("paper/WORKING_PAPER.md", "SUPERSEDED 2026-08-06",
     "A banner listing what the superseding paper carries. It points at "
     "IGRM_paper_v1.md rather than asserting a result, and that paper now "
     "states the baselines in its own abstract."),
    ("paper/founder_interview.md", "Hit rate **0.069**",
     "Here 24 of 29 is the COMPARATOR, cited to show the four-source gauge "
     "failing at 2 of 29. The number is doing unflattering work already; "
     "adding the naive baseline would blunt a negative result, not sharpen "
     "it."),
    ("paper/founder_interview.md", "| Claim | File |",
     "A claim-to-payload index table. Each row is a pointer telling a reader "
     "which file to open, not a sentence asserting the finding."),
)


def _baselines() -> dict:
    return json.loads(BASELINES.read_text(encoding="utf-8"))["hit_rate_context"]


def _figure(hits: int, n: int) -> re.Pattern:
    """'24 of 29' and '24/29' are the same claim written two ways."""
    return re.compile(rf"\b{hits}\s*(?:/|\s+of\s+)\s*{n}\b")


def _surfaces() -> list[Path]:
    out: list[Path] = []
    for pattern in GLOBS:
        out.extend(sorted(ROOT.glob(pattern)))
    return [p for p in out if p.is_file()]


def test_the_naive_rule_still_beats_the_registered_one() -> None:
    """The premise every sentence this file guards is built on.

    The published prose says the naive any-channel detector scores higher.
    If a recomputation flips that, those sentences are false and the fix is
    to rewrite them -- not to keep enforcing their co-occurrence."""
    ctx = _baselines()
    naive, registered = ctx["naive_any_channel_hits"], ctx["registered_criterion_hits"]
    assert naive > registered, (
        f"the naive any-channel detector now scores {naive} against the "
        f"registered {registered}, so it no longer beats the registered rule. "
        "The prose in methodology.md, paper/IGRM_paper_v1.md, "
        "paper/founder_interview.md, listings/ and "
        "scripts/generate_api_contract.py says that it does. Rewrite those "
        "sentences to match the payload, then update this assertion; do not "
        "delete it.")


def test_the_headline_figure_never_travels_without_its_baseline() -> None:
    ctx = _baselines()
    n = ctx["n_events"]
    headline = _figure(ctx["registered_criterion_hits"], n)
    naive = _figure(ctx["naive_any_channel_hits"], n)

    bare: list[str] = []
    for path in _surfaces():
        relative = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        anchors = [a for f, a, _ in EXEMPT if f == relative and a in text]
        for match in headline.finditer(text):
            window = text[max(0, match.start() - WINDOW): match.end() + WINDOW]
            if naive.search(window):
                continue
            # An exemption covers the paragraph its anchor sits in, not the
            # whole file: the anchor has to be near the figure it licenses.
            if any(a in text[max(0, match.start() - 400): match.end() + 400]
                   for a in anchors):
                continue
            line = text[: match.start()].count("\n") + 1
            bare.append(f"{relative}:{line}")

    assert not bare, (
        "the registered detection figure is published without the naive "
        "baseline that outscores it at:\n  " + "\n  ".join(bare) +
        f"\n\nThe payload records naive {ctx['naive_any_channel_hits']} of {n} "
        f"against registered {ctx['registered_criterion_hits']} of {n} "
        f"({ctx['chance_expected_hits']} expected by chance). Quoting the "
        "registered number alone reads as a detection result; it is a "
        "channel-attribution result. Either state the baseline within "
        f"{WINDOW} characters, or add the file to EXEMPT with the argument "
        "for why it is not a claim.")


def test_the_two_authoritative_documents_state_the_direction() -> None:
    """Co-occurrence is not enough for the documents a referee opens first.

    Both numbers can sit on a page and still leave a reader to work out which
    is larger. The methodology and the paper have to say it in words."""
    ctx = _baselines()
    naive = _figure(ctx["naive_any_channel_hits"], ctx["n_events"])
    for relative in ("methodology.md", "paper/IGRM_paper_v1.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert naive.search(text), (
            f"{relative} does not state the naive baseline anywhere. Before "
            "2026-08-10 neither of these documents mentioned it once, while "
            "both stated the registered figure.")
        assert re.search(r"\bnaive\b", text, re.IGNORECASE), (
            f"{relative} carries the number but never names it as the naive "
            "detector, so a reader cannot tell what it is a baseline for")
        assert re.search(r"attribution", text, re.IGNORECASE), (
            f"{relative} states the baseline but not what survives it. The "
            "licensed reading is that the apparatus contributes channel "
            "ATTRIBUTION, not detection; without that sentence the baseline "
            "reads as an unexplained embarrassment instead of the finding.")


def test_every_exemption_still_matches_the_sentence_it_licenses() -> None:
    """A stale exemption silently widens the hole it was cut for.

    An anchor that no longer matches means the sentence was rewritten, and a
    rewritten sentence has not been argued for -- it needs re-reading, not
    inheriting the old argument."""
    for relative, anchor, _reason in EXEMPT:
        path = ROOT / relative
        assert path.exists(), (
            f"EXEMPT names a missing file: {relative}. Remove the entry "
            "rather than leaving a rule that matches nothing.")
        assert anchor in path.read_text(encoding="utf-8"), (
            f"the EXEMPT anchor {anchor!r} no longer appears in {relative}, "
            "so the sentence it licensed has changed. Re-read the argument "
            "in EXEMPT against the new sentence and either re-anchor it or "
            "state the baseline.")


def test_the_datasheet_keeps_reporting_it_as_a_negative_result() -> None:
    """The finding was already published honestly in one place. The sweep
    added the baseline elsewhere; it must not have quietly softened the
    place that had it right all along."""
    text = (ROOT / "docs" / "datasheet.md").read_text(encoding="utf-8")
    ctx = _baselines()
    assert _figure(ctx["naive_any_channel_hits"], ctx["n_events"]).search(text)
    assert "naive any-channel detector nearly matches" in text, (
        "the datasheet's negative-results heading for the naive baseline is "
        "gone; that section is where the project states its unflattering "
        "numbers together and it predates this test")
