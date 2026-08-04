"""Regression locks for the 2026-08-04 base-hardening fixes."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_receipts_sort_is_credibility_then_aptness():
    from src.receipts import _tier_sort_key
    apt_t2 = {"tier": 2, "_title_hit": True, "_rel": 5}
    junk_t2 = {"tier": 2, "_title_hit": False, "_rel": 0}
    apt_t3 = {"tier": 3, "_title_hit": True, "_rel": 0}
    order = sorted([junk_t2, apt_t3, apt_t2], key=_tier_sort_key)
    assert order[0] is apt_t2, "apt tier-2 first"
    assert order[1] is junk_t2, "tier beats aptness across tiers"
    assert order[2] is apt_t3


def test_audit_gauge_tolerance_is_rounded_inputs_bound():
    src = (ROOT / "src" / "audit.py").read_text()
    assert "0.101" in src, "gauge check must keep the rounded-inputs bound"


def test_no_typewriter_hyphens_in_reader_copy():
    for name in ("index.html", "data.html", "receipts.html", "analysis.html"):
        text = (ROOT / "docs" / name).read_text()
        assert " -- " not in text, f"double hyphen in {name}"


def test_every_published_payload_is_documented():
    codebook = (ROOT / "docs" / "codebook.md").read_text()
    for payload in ("receipts.json", "expert_shelf.json", "precision.json",
                    "reliability.json", "predictions.json", "nowcast.json",
                    "stress_gauge.json", "comparators.json",
                    "predictability.json", "episode_actors.json",
                    "api_contract.json"):
        assert payload in codebook, f"{payload} missing from codebook"


def test_url_schemes_are_allowlisted_in_receipts_payload():
    p = ROOT / "docs" / "data" / "receipts.json"
    if not p.exists():
        return
    d = json.loads(p.read_text())
    for c in (d.get("channels") or {}).values():
        for a in c.get("articles", []):
            assert a["url"].startswith(("http://", "https://"))
