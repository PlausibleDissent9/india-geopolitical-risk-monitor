"""Operational founder work must not be served as research output."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def test_no_public_page_links_to_the_operational_queue():
    offenders = []
    for path in DOCS.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        if "decisions.html" in text or "Open decisions" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"operational queue leaked into public pages: {offenders}"


def test_operational_queue_has_no_public_artifact():
    assert not (DOCS / "decisions.html").exists()
    assert not (DOCS / "data" / "decisions.json").exists()


def test_published_weekly_note_contains_no_editorial_workflow():
    note = (ROOT / "notes" / "2026-W32.md").read_text(encoding="utf-8")
    forbidden = ("Status:", "Founder check", "final editorial draft")
    assert not any(term in note for term in forbidden)
    assert note.startswith("# IGRM Weekly Assessment: Week ending 6 August 2026")
    for section in (
        "## Executive assessment",
        "## Channel positioning",
        "## External comparator: Strait of Hormuz",
        "## Calibration sensitivity",
        "## Monitoring statement",
    ):
        assert section in note
