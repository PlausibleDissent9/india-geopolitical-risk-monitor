"""No committed reader-facing surface states an unlicensed claim.

IGRM measures press salience. The licensed record (README, methodology
section 1, validation.html, vs-gpr.html:125-126) licenses NO statement
of: construct validity ("measures risk", a "validated" methodology or
index, "proven"); superiority over another index; prediction; or a
precision/recall/placebo RESULT as established -- precision is
UNCALIBRATED at 16 of 100 author labels, recall is unfielded, and the
placebo overlap is 0.452, which the founder interview itself lists as
"not a pass".

CALIBRATION, learned the hard way in tests/test_history_page.py:88-95:
a banned-substring check cannot tell a claim from a discussion of the
claim. "Not a validated headline measure" and the vs-gpr list of
forbidden claims are HONEST prose and must never fire. So every pattern
here is narrow, most carry a negation/discussion guard, and each one
documents its nearest honest miss in the committed corpus -- the string
that proves the pattern does not fire on the right answer. A test that
fires on honest prose trains people to ignore it, which is worse than
no test.

KNOWN VIOLATIONS LEDGER: analysis/claims_audit_2026-08-08.md records
the six sentences found by the audit. All six were rewritten in the
same commit that emptied the pin list below; no reader-facing claim is
grandfathered. Future temporary pins must tolerate one exact sentence
only and must be removed with its fix.
"""
import html as html_mod
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The reader-facing committed surface. Design documents (IGRM_MAX_SPEC,
# DESIGN_*, NOTES_FOR_ISHAN, CONTINUITY) are working notes, not reader
# surfaces, and are excluded on purpose.
MD_FILES = (
    ["README.md", "methodology.md", "package/README.md"]
    + sorted(str(p.relative_to(ROOT)) for p in (ROOT / "docs").glob("*.md"))
    + sorted(str(p.relative_to(ROOT)) for p in (ROOT / "paper").glob("*.md"))
    + sorted(str(p.relative_to(ROOT)) for p in (ROOT / "nef").glob("*.md"))
    + sorted(str(p.relative_to(ROOT)) for p in (ROOT / "listings").glob("*.md"))
)
HTML_FILES = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "docs").glob("*.html"))
JSON_FILES = sorted(
    str(p.relative_to(ROOT)) for p in (ROOT / "docs" / "data").glob("*.json")
) + ["listings/kaggle_dataset_metadata.json"]

# JSON keys that hold IGRM-authored framing prose. Article titles,
# episode names and other third-party press content live under other
# keys and are quoted material, not IGRM claims.
PROSE_KEYS = {
    "what", "why", "reading", "note", "notes", "caveat", "caveats",
    "definition", "description", "finding", "interpretation", "framing",
    "disclaimer", "headline", "summary",
}

# Words that mark the surrounding sentence as negating or DISCUSSING a
# claim rather than making it. Quote characters count: a claim inside
# quotation marks on these surfaces is being cited, listed as forbidden,
# or denied (vs-gpr.html:125-126, founder_interview.md:210-219).
_NEG = re.compile(
    # Quotation marks only, never the apostrophe: "IGRM's" must not
    # excuse whatever follows it.
    r"\b(?:not|never|no|nor|cannot|can't|isn't|aren't|wasn't|doesn't|"
    r"don't|without|forbidden|banned|dishonest|than)\b|[\"“”‘«]",
    re.IGNORECASE,
)


def _guarded(text: str, start: int, before: int = 100, after: int = 0) -> bool:
    """True when the match sits in a negated or quoted/discussed span."""
    lo = max(0, start - before)
    if _NEG.search(text[lo:start]):
        return True
    return bool(after and _NEG.search(text[start:start + after]))


# (name, pattern, before-window, after-window). A window of 0 means the
# pattern is safe bare. Every nearest-miss cited below was verified
# against the committed corpus while writing this file.
PATTERNS = [
    # -- (a) construct validity -------------------------------------
    # Nearest miss: "not a validated headline measure"
    # (methodology.md:345, docs/data.html:87) -- "headline" breaks the
    # adjacency AND the negation guard catches the "not".
    ("validated-thing",
     re.compile(r"\bvalidated (?:methodology|methodologies|instrument|index|measure|series)\b",
                re.IGNORECASE), 60, 0),
    # Nearest misses: "are validated against a pre-registered episode
    # list" (paper/WORKING_PAPER.md:62; scoped to the episode study,
    # classed AMBIGUOUS in the audit, excluded by the lookahead) and
    # "was cross-validated against English Wikipedia"
    # (methodology.md:490; "cross-validated" is a different token).
    ("is-validated",
     re.compile(r"\b(?:is|are|was|were|been|fully) validated\b(?!\s+against)",
                re.IGNORECASE), 60, 0),
    # Nearest miss: '"confirms IGRM measures risk" are forbidden under
    # every outcome' (docs/vs-gpr.html:126) -- quoted, so the guard's
    # quote-character rule catches it. The Caldara-Iacoviello paper
    # title "Measuring Geopolitical Risk" is a gerund and never matches.
    ("measures-risk",
     re.compile(r"\b(?:measures?|tracks?|captures?|quantif(?:y|ies)|gauges?) "
                r"(?:the )?(?:geopolitical |political |actual )?risk\b",
                re.IGNORECASE), 100, 0),
    # Nearest miss: "It is not a measure of risk" (docs/start.html:53,
    # nef attribution blocks) -- the "not" between "is" and "a" breaks
    # adjacency, so this needs no guard window at all.
    ("is-a-measure-of-risk",
     re.compile(r"\b(?:is|as) an? (?:direct )?(?:measure|index|gauge) of "
                r"(?:geopolitical )?risk\b", re.IGNORECASE), 60, 0),
    # No honest use of "external validation" exists on the surface; the
    # three occurrences are all pinned violations (audit items 2-4).
    ("external-validation",
     re.compile(r"\bexternal(?:ly)? validat\w*", re.IGNORECASE), 0, 0),
    # Nearest miss: none on the surface today. Guarded anyway so a
    # future "nothing here is proven" stays honest and quiet.
    ("proven",
     re.compile(r"\bproven\b", re.IGNORECASE), 60, 0),
    # -- (b) superiority --------------------------------------------
    # Requires a comparator object, so "barely beats chance as a
    # detector" (docs/datasheet.md:350) and "better than it measures
    # Indian-language attention" (paper/IGRM_paper_v1.md:353) never
    # match: chance and "it" are not indices. Nearest miss that DOES
    # match the regex: "IGRM does not claim to beat GPR or AI-GPR"
    # (docs/vs-gpr.html) -- the guard's "not" catches it.
    ("superiority-over-index",
     re.compile(r"\b(?:outperforms?|beats?|superior to|better than|more accurate than) "
                r"(?:the |any |every |all )?(?:other |another |competing )?"
                r"(?:GPR\w*|Caldara\S*|ind(?:ex|ices)|instruments?|benchmarks?)\b",
                re.IGNORECASE), 100, 0),
    # Nearest miss: 'Claims such as "outperforms", "more accurate",'
    # (docs/vs-gpr.html:125) -- quoted, caught by the guard.
    ("superiority-bare",
     re.compile(r"\boutperforms?\b|\bsuperiority over\b", re.IGNORECASE), 100, 0),
    # -- (c) prediction (belt to the daily-brief lint's braces) ------
    # Nearest miss: "The index itself predicts nothing"
    # (docs/predictions.html:38) -- "itself" breaks adjacency and the
    # lookahead excludes "nothing"/"none"/"no" objects anyway.
    ("index-predicts",
     re.compile(r"\b(?:index|instrument|IGRM|model|we) "
                r"(?:predicts?|forecasts?|anticipates?)\b"
                r"(?!\s+(?:nothing|none|no)\b)", re.IGNORECASE), 60, 0),
    # Nearest misses: "is not an early-warning system for anything
    # priced" (docs/datasheet.md:377) and "a better narrative-tracker
    # than early-warning system" (paper/WORKING_PAPER.md:128) -- the
    # guard's "not" and "than" both hit inside the window.
    ("early-warning",
     re.compile(r"\bearly[- ]warning (?:system|signal|indicator|tool)\b",
                re.IGNORECASE), 80, 0),
    # -- (d) unlicensed study results -------------------------------
    # Nearest miss: "placebo channels that must stay quiet"
    # (docs/validation.html header) -- a design requirement; "that
    # must" breaks adjacency.
    ("placebo-quiet",
     re.compile(r"\bplacebo channels? (?:stay(?:s|ed)?|remain(?:s|ed)?) quiet\b",
                re.IGNORECASE), 0, 0),
    # Nearest miss: "that the placebo test passed -- 45.2% is not a
    # pass" (paper/founder_interview.md:218): the refutation follows
    # the phrase, so this one guards the AFTER window too.
    ("placebo-passed",
     re.compile(r"\bplacebo (?:test|check|diagnostic)s? passed\b",
                re.IGNORECASE), 80, 80),
    # Nearest miss: "that its precision is established -- it's
    # uncalibrated" (paper/founder_interview.md:215) has the reversed
    # word order and never matches the adjectival form required here.
    ("established-precision",
     re.compile(r"\b(?:high|strong|excellent|demonstrated|established|proven|confirmed) "
                r"(?:precision|recall|accuracy)\b", re.IGNORECASE), 60, 0),
]

# The known-violations ledger: (file, exact sentence). See the audit
# for the classification and the one-line fixes. Delete each entry when
# its fix lands; a stale pin is inert, never load-bearing.
KNOWN_VIOLATIONS: list[tuple[str, str]] = []

_TAGS = re.compile(r"<script\b.*?</script>|<style\b.*?</style>|<[^>]+>", re.S | re.I)
# Meta descriptions render in search results and social cards -- they
# are reader-facing prose, and tag-stripping alone would silently drop
# them (the audit's item 1 lives in exactly such an attribute).
_META = re.compile(
    r'<meta\b[^>]*?(?:name|property)="(?:description|og:description|'
    r'og:title|twitter:description)"[^>]*?content="([^"]*)"', re.I)
_META_REV = re.compile(
    r'<meta\b[^>]*?content="([^"]*)"[^>]*?(?:name|property)="(?:description|'
    r'og:description|og:title|twitter:description)"', re.I)


def _html_text(raw: str) -> str:
    metas = _META.findall(raw) + _META_REV.findall(raw)
    return html_mod.unescape(" ".join([_TAGS.sub(" ", raw), *metas]))


def _json_prose(path: Path) -> str:
    """IGRM-authored prose strings, joined. Paths under a key containing
    'forbidden' are deny-lists of quoted claims, not claims."""
    out: list[str] = []

    def walk(obj, key: str, banned: bool) -> None:
        banned = banned or "forbidden" in key.lower()
        if isinstance(obj, dict):
            for k, v in obj.items():
                walk(v, str(k), banned)
        elif isinstance(obj, list):
            for v in obj:
                walk(v, key, banned)
        elif isinstance(obj, str) and not banned and key.lower() in PROSE_KEYS:
            out.append(obj)

    walk(json.loads(path.read_text(encoding="utf-8")), "", False)
    return "\n".join(out)


def _surface() -> dict[str, str]:
    texts: dict[str, str] = {}
    for rel in MD_FILES:
        texts[rel] = (ROOT / rel).read_text(encoding="utf-8")
    for rel in HTML_FILES:
        texts[rel] = _html_text((ROOT / rel).read_text(encoding="utf-8"))
    for rel in JSON_FILES:
        texts[rel] = _json_prose(ROOT / rel)
    return texts


def _pinned_spans(rel: str, text: str) -> list[tuple[int, int]]:
    spans = []
    for file, sentence in KNOWN_VIOLATIONS:
        if file != rel:
            continue
        start = 0
        while (i := text.find(sentence, start)) != -1:
            spans.append((i, i + len(sentence)))
            start = i + 1
    return spans


def test_no_reader_facing_surface_makes_an_unlicensed_claim():
    offenders = []
    for rel, text in sorted(_surface().items()):
        pins = _pinned_spans(rel, text)
        for name, pat, before, after in PATTERNS:
            for m in pat.finditer(text):
                if any(a <= m.start() < b for a, b in pins):
                    continue
                if (before or after) and _guarded(text, m.start(), before, after):
                    continue
                ctx = " ".join(text[max(0, m.start() - 90):m.end() + 90].split())
                offenders.append(f"{rel} [{name}]: ...{ctx}...")
    assert not offenders, (
        "Unlicensed claim language on a reader-facing surface. IGRM "
        "measures press salience; construct-validity, superiority, "
        "prediction, and established-precision claims are not licensed "
        "(analysis/claims_audit_2026-08-08.md has the rubric and the "
        "receipts):\n" + "\n".join(offenders))


def test_the_scan_actually_covers_the_surface():
    """A glob that silently matches nothing would make the test above
    pass vacuously; the file counts are the tripwire."""
    texts = _surface()
    assert len(MD_FILES) >= 12, f"markdown surface shrank to {len(MD_FILES)}"
    assert len(HTML_FILES) >= 20, f"html surface shrank to {len(HTML_FILES)}"
    assert len(JSON_FILES) >= 25, f"payload surface shrank to {len(JSON_FILES)}"
    assert len(texts) >= 25, f"scanned surface shrank to {len(texts)} files"
    nonempty = sum(1 for t in texts.values() if t.strip())
    assert nonempty >= 25, f"only {nonempty} scanned files had any text"


def test_the_pins_still_match_their_files():
    """Each ledger entry names a real file. (The sentence itself may
    vanish -- that is the fix landing, and the pin then tolerates
    nothing.) But a renamed file would leave a pin dangling while its
    replacement went unpinned, so the filenames are asserted."""
    for file, _ in KNOWN_VIOLATIONS:
        assert (ROOT / file).is_file(), (
            f"known-violations ledger names a missing file: {file}; "
            "update analysis/claims_audit_2026-08-08.md and this ledger")
