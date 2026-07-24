"""
CI enforcement of the dictionary rules (IGRM_MAX_SPEC.md section V.1 and
methodology.md section 2), across the primary, robustness-variant, and
placebo dictionaries.

The ex-ante rule is the load-bearing one: a spike at a known episode must
be DETECTED by structural terms, never baked in by naming the event.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Retrospective event names. Word-bounded regex so 'uri' does not match
# 'security'. Extend this list; never shrink it.
BANNED_EVENT_NAMES = [
    r"\bgalwan\b",
    r"\bpulwama\b",
    r"\bbalakot\b",
    r"\bsindoor\b",
    r"\bkargil\b",
    r"\buri\b",
    r"26/11",
    r"\bdoklam\b",
    r"\bpathankot\b",
    r"\bpahalgam\b",
    r"\bmumbai attacks?\b",
    r"\bparliament attack\b",
    r"\bgalaxy leader\b",
    r"\boperation\s+\w+",
]

# One quoted phrase, nothing outside the quotes. GDELT's DOC API cannot
# express per-term AND anchors inside an OR group (no nesting, no AND/OR
# mixing), so disambiguation lives in the channel-level 'anchor' word.
PURE_PHRASE = re.compile(r'^"[^"]+"$')


def load(name: str) -> dict:
    with open(ROOT / name, encoding="utf-8") as f:
        return json.load(f)


def channel_specs(name: str):
    d = load(name)
    if name == "dictionaries_alt.json":
        for variant, chans in d.items():
            if variant.startswith("_"):
                continue
            for ch, spec in chans.items():
                yield f"{name}:{variant}:{ch}", spec
    else:
        for ch, spec in d.items():
            if ch.startswith("_"):
                continue
            yield f"{name}:{ch}", spec


ALL_FILES = ["dictionaries.json", "dictionaries_alt.json", "dictionaries_placebo.json"]


def all_terms():
    for name in ALL_FILES:
        for where, spec in channel_specs(name):
            for term in spec["terms"]:
                yield where, term


def test_ex_ante_rule_no_event_names():
    violations = []
    for where, term in all_terms():
        low = term.lower()
        for pattern in BANNED_EVENT_NAMES:
            if re.search(pattern, low):
                violations.append(f"{where}: {term!r} matches banned {pattern!r}")
    assert not violations, "Ex-ante rule violated:\n" + "\n".join(violations)


# The rule extends to EVERY source's query list, not just GDELT terms: a
# banned event name in a Wikipedia article title or a Trends search
# phrase bakes detection of that event into the series exactly the same
# way ('Galwan River' was caught here in review, 2026-07-24 -- the page's
# attention exists almost entirely because of a validation episode).
SOURCE_LIST_FILES = ["wikipedia_articles.json", "trends_terms.json"]


def test_ex_ante_rule_covers_all_source_lists():
    violations = []
    for name in SOURCE_LIST_FILES:
        data = load(name)
        for ch, items in data.items():
            if ch.startswith("_"):
                continue
            for item in items:
                low = item.lower()
                for pattern in BANNED_EVENT_NAMES:
                    if re.search(pattern, low):
                        violations.append(
                            f"{name}:{ch}: {item!r} matches banned {pattern!r}"
                        )
    assert not violations, "Ex-ante rule violated:\n" + "\n".join(violations)


def test_terms_are_pure_quoted_phrases():
    violations = [
        f"{where}: {term!r}"
        for where, term in all_terms()
        if not PURE_PHRASE.match(term)
    ]
    assert not violations, (
        "Terms must each be a single quoted phrase (GDELT cannot mix AND "
        "into an OR group; use the channel-level anchor instead):\n"
        + "\n".join(violations)
    )


def test_anchor_is_a_single_bare_word():
    for name in ALL_FILES:
        for where, spec in channel_specs(name):
            anchor = spec.get("anchor")
            if anchor is not None:
                assert re.match(r"^\w+$", anchor), (
                    f"{where}: anchor {anchor!r} must be one bare word"
                )


def test_every_channel_has_label_and_terms():
    for name in ALL_FILES:
        for where, spec in channel_specs(name):
            assert spec.get("label"), f"{where}: missing label"
            assert spec.get("terms"), f"{where}: no terms"


def test_primary_terms_all_have_rationale():
    for where, spec in channel_specs("dictionaries.json"):
        missing = set(spec["terms"]) - set(spec.get("rationale", {}))
        extra = set(spec.get("rationale", {})) - set(spec["terms"])
        assert not missing, f"{where}: terms without rationale: {sorted(missing)}"
        assert not extra, f"{where}: rationale for absent terms: {sorted(extra)}"


def test_no_term_in_two_primary_channels():
    # Silent double-counting inflates the composite (methodology s2).
    seen: dict[str, str] = {}
    for where, spec in channel_specs("dictionaries.json"):
        for term in spec["terms"]:
            key = term.lower()
            assert key not in seen, f"{term!r} in both {seen[key]} and {where}"
            seen[key] = where


def test_frozen_primary_dictionaries_are_properly_sized():
    d = load("dictionaries.json")
    if not d.get("_meta", {}).get("frozen_on"):
        pytest.skip("dictionaries not frozen yet")
    for where, spec in channel_specs("dictionaries.json"):
        n = len(spec["terms"])
        assert 8 <= n <= 15, (
            f"{where}: {n} terms; frozen dictionaries need 8-15 "
            "(below 8 recall is thin, above 15 contamination grows)"
        )
