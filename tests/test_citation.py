"""CITATION.cff is the file a stranger cites from. It must not drift.

It had drifted. On 2026-08-07 it said:

    version: 1.0.0
    date-released: "2026-07-24"
    url: "https://plausibledissent9.github.io/india-geopolitical-risk-monitor"

while the methodology was at v1.9.0 and every published payload's
`_meta.citation` read "https://igrm.in/". Eight minor versions stale, and
pointing at the GitHub Pages mirror rather than the canonical site — so
anyone who did the right thing and cited the machine-readable file would
have cited the wrong URL and an eight-version-old release.

This is the same defect as two copies of the palette, except the copy
that goes stale is the one that ends up in somebody else's bibliography,
where neither of us can fix it. So the three fields that exist elsewhere
in the repo are checked against their source rather than maintained by
hand.
"""
from __future__ import annotations

import re
from pathlib import Path

from src import stamp_meta

ROOT = Path(__file__).resolve().parents[1]
CFF = ROOT / "CITATION.cff"
METHODOLOGY = ROOT / "docs" / "methodology.html"


def _field(name: str) -> str:
    m = re.search(rf'^{name}:\s*"?([^"\n]+)"?\s*$', CFF.read_text(encoding="utf-8"),
                  re.M)
    assert m, f"CITATION.cff has no {name} field"
    return m.group(1).strip()


def test_the_cited_url_is_the_canonical_site():
    """Every payload tells its downloader to cite https://igrm.in/. The
    citation file must say the same thing or the two disagree in the one
    place a reader is most likely to trust."""
    canonical = stamp_meta.universal_fields("x.json")["citation"]
    host = re.search(r"(https://[\w.]+/)", canonical).group(1)
    assert _field("url") == host, (
        f"CITATION.cff url is {_field('url')} but every payload cites "
        f"{host}. The mirror is not the canonical site.")


def test_the_cited_version_matches_the_methodology():
    """A dataset citation carries a version. If it lags the methodology,
    somebody cites v1.0.0 while reading v1.9.0's numbers."""
    page = METHODOLOGY.read_text(encoding="utf-8")
    m = re.search(r"<p>Version (\d+\.\d+\.\d+)", page)
    assert m, "methodology.html no longer states its version in the lead"
    assert _field("version") == m.group(1), (
        f"CITATION.cff says version {_field('version')}, methodology.html "
        f"says {m.group(1)}")


def test_the_licence_matches_what_every_payload_promises():
    promised = stamp_meta.universal_fields("x.json")["license"]     # "CC BY 4.0"
    declared = _field("license")                                     # "CC-BY-4.0"
    assert declared.replace("-", " ").upper() == promised.replace("-", " ").upper(), (
        f"CITATION.cff licence {declared} vs payload licence {promised}")


def test_a_doi_is_absent_rather_than_invented():
    """The DOI is founder-gated: minting it requires a Zenodo deposit that
    only Ishan can make. An identifier written here before that happens
    would be a citation pointing at nothing, which is worse than no
    identifier at all. When the deposit exists, add it here and this test
    becomes the check that it is well-formed."""
    text = CFF.read_text(encoding="utf-8")
    m = re.search(r"doi:\s*(\S+)", text, re.I)
    if m:
        assert re.fullmatch(r"10\.\d{4,9}/\S+", m.group(1)), (
            f"malformed DOI in CITATION.cff: {m.group(1)}")
