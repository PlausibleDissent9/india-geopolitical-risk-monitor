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

COVERAGE IS MANIFEST-RECONCILED (external review finding #14,
2026-08-08): the scan set used to be guarded by count floors (md >= 12,
html >= 20, payloads >= 25) -- catastrophic-shrinkage detection only.
Losing one important page was invisible, and a new surface was unscanned
by definition. Each scanned class is now reconciled against a manifest
the publication machinery already maintains for its own reasons: pages
against docs/sitemap.xml (itself derived and enforced by
tests/test_sitemap.py), payloads against docs/data/api_contract.json's
promised endpoints, markdown against the git index filtered to
reader-facing paths. The tests below assert the scanned set EQUALS the
derived manifest, so an unexplained addition or removal fails with the
delta named. Every exception is listed here with its reason; nothing
else is hand-enumerated.
"""
import html as html_mod
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

# -- markdown ---------------------------------------------------------------
# Tracked markdown that is NOT reader-facing, each with its reason.
# Entries ending in "/" exclude the directory; anything tracked and not
# excluded here is reader-facing BY DEFAULT and must be scanned -- a new
# file or directory of markdown fails the manifest test until it is
# either scanned or named here with a reason.
MD_EXCLUDED = {
    ".github/": "issue-form scaffolding for reviewers, not IGRM prose",
    "CONTINUITY.md": "working notes between agent sessions",
    "DESIGN_BRIEF.md": "design working notes",
    "DESIGN_SYSTEM.md": "design working notes",
    "IGRM_MAX_SPEC.md": "the internal build spec, a working document",
    "NOTES_FOR_ISHAN.md": "working notes addressed to the founder",
    "sectors_nse_amendment_DRAFT.md": "an unmerged draft amendment",
    "analysis/": "internal audits and run logs; the site never links a reader here",
    "auditor/": "the versioned machine-coding rubric, a registered instrument",
    "briefs/": "internal template for the practitioner brief",
    "countries/": "the country-fork recipe, an internal working document",
    "design/": "design working notes",
    "notes/": "weekly note SOURCES; their published forms (docs/feed.xml "
              "and the notes payload) are scanned instead",
    "notes-inbox/": "unpublished drafts",
    "prompts/": "LLM prompt sources and their changelog",
    "validation/": "hash-frozen registered study evidence "
                   "(tests/test_blind_audit_500.py pins the bytes); a claims "
                   "lint must never be able to demand edits to frozen evidence",
}

# The scanned markdown, derived from disk. Top-level repo-front documents
# are named (a directory glob cannot express "these five files");
# GOVERNANCE, REPLICATION and SECURITY joined the scan 2026-08-08 -- they
# are read on GitHub by exactly the audience the claims rubric protects.
MD_FILES = sorted(
    {"README.md", "GOVERNANCE.md", "REPLICATION.md", "SECURITY.md",
     "methodology.md", "package/README.md"}
    | {str(p.relative_to(ROOT)) for p in DOCS.rglob("*.md")}
    | {str(p.relative_to(ROOT)) for p in (ROOT / "paper").rglob("*.md")}
    | {str(p.relative_to(ROOT)) for p in (ROOT / "nef").rglob("*.md")}
    | {str(p.relative_to(ROOT)) for p in (ROOT / "listings").rglob("*.md")}
    | {str(p.relative_to(ROOT)) for p in (ROOT / "standard").rglob("*.md")}
)

# -- pages ------------------------------------------------------------------
# Served pages the sitemap deliberately hides from crawlers
# (src/sitemap.py EXCLUDE, reasons there). They are still public bytes on
# the origin, so they are still scanned; the manifest test keeps this
# list synchronized with the sitemap's own exclusion list.
NON_SITEMAP_PAGES = {
    "404.html": "served to every mistyped URL",
    "embed.html": "rendered inside other people's pages",
    "portal.html": "noindex, but public bytes on the origin",
    "write.html": "noindex, but public bytes on the origin",
}
HTML_FILES = sorted(str(p.relative_to(ROOT)) for p in DOCS.rglob("*.html"))

# -- payloads ---------------------------------------------------------------
# JSON on disk under docs/ that is not IGRM-authored prose and not a
# promised endpoint. Anything else on disk must be promised or named.
NON_PAYLOAD_JSON = {
    "docs/geo/india.json": "third-party map geometry, no IGRM-authored prose",
    "docs/geo/world.json": "third-party map geometry, no IGRM-authored prose",
}
# Prose-bearing machine surfaces scanned although they are not contract
# endpoints (the contract cannot promise itself).
EXTRA_PAYLOADS = {
    "docs/data/api_contract.json": "the contract itself; endpoints cannot include it",
    "docs/openapi.json": "generator-mirrored contract prose served to integrators",
    "listings/kaggle_dataset_metadata.json": "third-party listing copy, not an endpoint",
}
# The one prose-bearing non-JSON endpoint; scanned as markup. The five
# CSV endpoints carry no authored prose field (they ARE the numeric
# series) -- the manifest test asserts that stays true of every non-JSON
# endpoint other than this one.
FEED = "docs/feed.xml"

JSON_FILES = sorted(
    ({str(p.relative_to(ROOT)) for p in DOCS.rglob("*.json")}
     - set(NON_PAYLOAD_JSON))
    | {p for p in EXTRA_PAYLOADS if not p.startswith("docs/")}
)

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
    """True when the match sits in a negated or quoted/discussed span.

    KNOWN FALSE-NEGATIVE (accepted, 2026-08-08): the window does not
    stop at sentence boundaries, so a negation in a PRIOR sentence can
    excuse a claim in the next one ("Not investment advice. IGRM
    measures risk." slips through). External review flagged it; a
    sentence-boundary cut was tried and REVERTED the same hour -- it
    fired on honest deny-lists and on decimal points ("99.5" reads as a
    boundary), and this file's own rule is that zero false positives
    beats fewer false negatives. The bias is toward under-flagging,
    which the audit cycle (not this test) exists to catch."""
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
    # The RSS feed is IGRM-authored prose in XML clothing; tag-stripping
    # leaves exactly the item text a feed reader displays.
    texts[FEED] = _html_text((ROOT / FEED).read_text(encoding="utf-8"))
    return texts


def _tracked_md() -> set[str]:
    """Tracked *.md per the git index. Falls back to the disk tree where
    .git is absent: a `git archive` extract IS the committed tree, so the
    fallback is exact there and only there."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "*.md"], cwd=ROOT,
            capture_output=True, text=True, check=True,
        ).stdout
        files = {line.strip() for line in out.splitlines() if line.strip()}
        if files:
            return files
    except (OSError, subprocess.CalledProcessError):
        pass
    junk = {".venv", "node_modules", ".git"}
    return {
        str(p.relative_to(ROOT)) for p in ROOT.rglob("*.md")
        if junk.isdisjoint(p.relative_to(ROOT).parts)
    }


def _md_excluded(rel: str) -> bool:
    return any(
        rel == entry or (entry.endswith("/") and rel.startswith(entry))
        for entry in MD_EXCLUDED
    )


def _sitemap_pages() -> set[str]:
    text = (DOCS / "sitemap.xml").read_text(encoding="utf-8")
    pages = set()
    for loc in re.findall(r"<loc>([^<]+)</loc>", text):
        rel = loc.replace("https://igrm.in/", "").rstrip("/")
        pages.add("docs/" + (rel if rel.endswith(".html") else "index.html"))
    return pages


def _promised_endpoints() -> tuple[set[str], set[str]]:
    contract = json.loads(
        (ROOT / "docs" / "data" / "api_contract.json").read_text(encoding="utf-8")
    )
    json_promises: set[str] = set()
    other_promises: set[str] = set()
    for endpoint in contract["endpoints"]:
        path = "docs/" + endpoint["path"]
        (json_promises if path.endswith(".json") else other_promises).add(path)
    return json_promises, other_promises


def _deltas(scanned: set[str], manifest: set[str], extra_hint: str,
            missing_hint: str) -> list[str]:
    problems = [
        f"scanned but not in the manifest: {rel} -- {extra_hint}"
        for rel in sorted(scanned - manifest)
    ]
    problems += [
        f"in the manifest but not scanned: {rel} -- {missing_hint}"
        for rel in sorted(manifest - scanned)
    ]
    return problems


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


def test_the_scanned_pages_equal_the_sitemap_manifest():
    """Pages come from the publication machinery's own list. A page on
    disk that the sitemap does not know is an unexplained addition (add
    it to the sitemap or to src/sitemap.py EXCLUDE plus the named set
    here); a sitemap entry with no scanned file is a removal the scan
    would otherwise paper over."""
    from src import sitemap as sitemap_mod

    assert set(NON_SITEMAP_PAGES) == set(sitemap_mod.EXCLUDE), (
        "the scanned non-sitemap set has drifted from src/sitemap.py "
        "EXCLUDE; the two lists must name the same pages: "
        f"{sorted(set(NON_SITEMAP_PAGES) ^ set(sitemap_mod.EXCLUDE))}")
    manifest = _sitemap_pages() | {"docs/" + p for p in NON_SITEMAP_PAGES}
    problems = _deltas(
        set(HTML_FILES), manifest,
        "not in docs/sitemap.xml and not a named non-sitemap page",
        "listed in docs/sitemap.xml but absent from disk")
    assert not problems, "\n".join(problems)


def test_the_scanned_payloads_equal_the_contract_manifest():
    """Payloads come from the API contract's promised endpoints. A JSON
    file on disk the contract does not promise is an unexplained
    addition (contract it, or name it in EXTRA_PAYLOADS/NON_PAYLOAD_JSON
    with a reason); a promised endpoint with no file is a removal."""
    json_promises, other_promises = _promised_endpoints()

    assert FEED in other_promises, (
        "the feed endpoint left the contract; its scan entry is stale")
    unscannable = other_promises - {FEED}
    assert all(p.endswith(".csv") for p in sorted(unscannable)), (
        "a promised non-JSON, non-CSV endpoint exists that the prose "
        "scan silently skips; wire it into _surface(): "
        f"{sorted(p for p in unscannable if not p.endswith('.csv'))}")

    for rel, reason in NON_PAYLOAD_JSON.items():
        assert (ROOT / rel).is_file(), (
            f"stale NON_PAYLOAD_JSON entry ({reason}): {rel} is gone")
        assert rel not in json_promises, (
            f"{rel} is excluded as non-prose but the contract now "
            "promises it; it must be scanned instead")
    for rel in EXTRA_PAYLOADS:
        assert rel not in json_promises, (
            f"{rel} is named as a non-endpoint extra but the contract "
            "now promises it; drop the redundant naming")

    manifest = json_promises | set(EXTRA_PAYLOADS)
    problems = _deltas(
        set(JSON_FILES) | {p for p in EXTRA_PAYLOADS if p.startswith("docs/")},
        manifest,
        "not promised by docs/data/api_contract.json and not named",
        "promised by the contract but absent from the scan")
    assert not problems, "\n".join(problems)


def test_the_scanned_markdown_equals_the_tracked_reader_facing_set():
    """Markdown comes from the git index minus named exceptions. A new
    tracked .md anywhere is reader-facing by default: it either enters
    the scan (the disk globs pick up the covered directories on their
    own) or gets a named exclusion with a reason. A scan list that
    quietly narrowed would leave tracked reader-facing files here and
    fail with their names."""
    tracked = _tracked_md()
    for entry, reason in MD_EXCLUDED.items():
        assert any(
            rel == entry or (entry.endswith("/") and rel.startswith(entry))
            for rel in tracked
        ), f"stale MD_EXCLUDED entry ({reason}): nothing tracked matches {entry}"
    manifest = {rel for rel in tracked if not _md_excluded(rel)}
    problems = _deltas(
        set(MD_FILES), manifest,
        "on disk but not tracked reader-facing markdown (untracked file, "
        "or it belongs in MD_EXCLUDED with a reason)",
        "tracked reader-facing markdown the scan misses (extend the scan "
        "or add a named exclusion with a reason)")
    assert not problems, "\n".join(problems)


def test_the_prose_extraction_is_not_vacuous():
    """Manifest equality checks file SETS; this checks the extractors
    still yield text. A misspelled PROSE_KEYS entry or a broken tag
    stripper would zero the scanned prose while every set test stayed
    green."""
    texts = _surface()
    for rel in ("README.md", "docs/index.html", "docs/data/latest.json", FEED):
        assert texts[rel].strip(), f"prose extraction went empty for {rel}"
    payloads = [rel for rel in JSON_FILES]
    nonempty = [rel for rel in payloads if texts[rel].strip()]
    assert len(nonempty) * 2 > len(payloads), (
        f"only {len(nonempty)} of {len(payloads)} payloads yielded prose; "
        "the JSON prose extractor is scanning air")


def test_the_pins_still_match_their_files():
    """Each ledger entry names a real file. (The sentence itself may
    vanish -- that is the fix landing, and the pin then tolerates
    nothing.) But a renamed file would leave a pin dangling while its
    replacement went unpinned, so the filenames are asserted."""
    for file, _ in KNOWN_VIOLATIONS:
        assert (ROOT / file).is_file(), (
            f"known-violations ledger names a missing file: {file}; "
            "update analysis/claims_audit_2026-08-08.md and this ledger")
