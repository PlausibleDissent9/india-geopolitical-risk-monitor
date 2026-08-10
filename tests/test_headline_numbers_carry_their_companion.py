"""A favourable number must not travel further than the thing that qualifies it.

THE GENERAL DEFECT
`test_detection_figure_carries_its_baseline.py` documents one instance: the
registered detection figure appeared on 18 reader-facing surfaces and the naive
baseline that outscores it appeared beside 3 of them. Nothing was false. The
corpus still read stronger than the payloads support.

That is a *shape* of defect, not a one-off, and this file generalises it. Every
row below is a pair of committed numbers where one flatters the project and the
other qualifies it. The rule is that the first may not appear without the
second in reach.

WHY THIS CANNOT BE A SUBSTRING BAN
There is no bad word in "r = 0.484 in monthly levels". The sentence is true,
sourced, and carefully hedged. The defect is an ABSENCE, and an absence is only
visible as a ratio between two counts across a corpus. No amount of reading
individual sentences finds it -- the 2026-08-08 claims audit read this entire
surface line by line and did not, because each line was fine.

WHY COMPANIONS ARE A SET, NOT A STRING
An honest qualification can be prose rather than a number.
`listings/nasdaq_data_link_pitch.md` writes "indicating limited co-movement
between related measures rather than validation" and never quotes 0.232. That
is a correct qualification and must pass. A first pass of this scan flagged it
and two others as violations; reading them showed the scan was wrong, not the
prose. Each row therefore accepts several companion forms.

WHAT THIS FILE DOES NOT DO
It does not check that a number is TRUE of its payload -- that is
`test_page_claims_match_payloads.py`. It does not check for forbidden claim
language -- that is `test_claims_discipline.py`. It checks only that the
qualifier travels with the claim.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data"
WINDOW = 1200

GLOBS = ("docs/*.html", "docs/*.md", "paper/*.md", "nef/*.md",
         "listings/*", "README.md", "methodology.md")


def _payload(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _surfaces() -> list[Path]:
    out: list[Path] = []
    for pattern in GLOBS:
        out.extend(p for p in sorted(ROOT.glob(pattern)) if p.is_file())
    return out


def _pairs() -> list[tuple[str, re.Pattern, re.Pattern, tuple[str, ...], str]]:
    """(label, favourable, companion, exempt anchors, why it matters).

    Values are read from the payloads so that a recomputation cannot leave the
    prose stale while this file keeps passing -- the same reasoning as the
    detection test, and the same reason `test_page_claims_match_payloads.py`
    exists at all.
    """
    gpr = _payload("gpr_comparison.json")
    ai = _payload("ai_gpr_benchmark.json")
    back = _payload("back_extension.json")["overlap_audit"]

    # The COMPOSITE entry, explicitly. An earlier draft took the maximum
    # r_monthly_changes in the payload and got 0.276 (us_trade) instead of the
    # composite's 0.232 -- a test that enforces the wrong number is worse than
    # no test, because it makes correct prose look like a violation.
    composite = gpr["series"]["composite"]
    levels, changes = composite["r_levels"], composite["r_monthly_changes"]
    rho = ai["primary"]["rho"]
    ci_low = ai["primary"]["moving_block_bootstrap_95_ci"]["6"][0]
    published = (back["pakistan_west"]["r"], back["china_east"]["r"])
    refused = (back["us_trade"]["r"], back["gulf_energy"]["r"])

    return [
        (
            "GPR-India co-movement: levels correlation vs the weaker changes "
            "correlation",
            _num(levels),
            re.compile(rf"{_n(changes)}|in\s+changes|limited co-movement|"
                       r"not validation|rather than validation|"
                       r"convergent behavior", re.I),
            (),
            "Two trending series correlate in levels close to by construction. "
            f"The changes correlation is {changes}, less than half the levels "
            f"figure of {levels}, and it is the construction that carries "
            "information. Quoting levels alone overstates convergence.",
        ),
        (
            "AI-GPR registered benchmark: point estimate vs its 95% interval",
            re.compile(rf"\brho\s*=?\s*{_n(rho)}\b|ρ\s*{_n(rho)}\b|"
                       rf"\b{_n(rho)}\b(?=[^0-9]*Spearman)", re.I),
            # "95% interval of [0.050, 0.407]" is how methodology.md, the
            # datasheet and the paper all write it -- not "95% CI", and the
            # trailing zero defeats a \b after 0.05. A first draft of this
            # pattern flagged three correctly-written passages for both
            # reasons.
            re.compile(rf"{_n(ci_low)}|95\s*%?\s*(?:CI|interval)|"
                       r"confidence interval|moving-block", re.I),
            (),
            f"The registered moving-block 95% CI runs {ci_low}-"
            f"{ai['primary']['moving_block_bootstrap_95_ci']['6'][1]}. A lower "
            "bound that near zero is the finding; the point estimate alone is "
            "not.",
        ),
        (
            "Back-extension: the two channels that publish vs the two refused",
            re.compile("|".join(_n(v) for v in published)),
            re.compile("|".join(_n(v) for v in refused) +
                       r"|refus|DOES NOT PUBLISH|does not publish|withheld|"
                       r"pre-registered threshold", re.I),
            (),
            f"Four channels entered the overlap audit. Two replicate at "
            f"{published[0]} and {published[1]}; two scored {refused[0]} and "
            f"{refused[1]} and a pre-registered threshold refused them "
            "publication. The refusal is what makes the pair that passed "
            "mean anything.",
        ),
    ]


def _n(value: float) -> str:
    """Match a number as written in prose, which rounds. 0.484 is also
    written '0.48'; 0.893 is also written '0.89'."""
    text = f"{value:g}"
    if "." in text:
        whole, frac = text.split(".")
        if len(frac) >= 3:
            return rf"{whole}\.{frac[:2]}(?:{frac[2]})?"
    return re.escape(text)


def _num(value: float) -> re.Pattern:
    return re.compile(rf"\b{_n(value)}\b")


def test_every_favourable_number_travels_with_its_companion() -> None:
    failures: list[str] = []
    for label, favourable, companion, anchors, why in _pairs():
        bare: list[str] = []
        for path in _surfaces():
            relative = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            live = [a for a in anchors if a in text]
            for match in favourable.finditer(text):
                window = text[max(0, match.start() - WINDOW):
                              match.end() + WINDOW]
                if companion.search(window):
                    continue
                if any(a in text[max(0, match.start() - 400):
                                 match.end() + 400] for a in live):
                    continue
                bare.append(f"{relative}:{text[:match.start()].count(chr(10)) + 1}")
        if bare:
            failures.append(f"\n{label}\n  {why}\n  unaccompanied at:\n    " +
                            "\n    ".join(bare))
    assert not failures, (
        "a favourable number is published without the companion that "
        "qualifies it:" + "".join(failures) +
        "\n\nEither state the companion within "
        f"{WINDOW} characters of the claim, or -- if the sentence qualifies "
        "the number in prose instead -- add that phrasing to the row's "
        "companion pattern. Do not widen a pattern to make a bare claim pass.")


def test_the_pairs_still_point_at_real_payload_values() -> None:
    """Every row reads its numbers from a payload. A renamed field would make
    the row silently unenforceable, so the extraction is asserted separately
    rather than trusted to raise."""
    pairs = _pairs()
    assert len(pairs) == 3, "a row was added or dropped without updating this count"
    for label, favourable, companion, _anchors, why in pairs:
        assert favourable.pattern and companion.pattern
        assert why.strip(), f"{label} has no stated reason; a rule nobody can " \
                            "read the argument for gets deleted by the next " \
                            "person who hits it"
