"""A drafted rights decision must be inert until the founder signs it.

The mission's standing rule is: agents PREPARE source-rights packets and
never sign them. governance/decisions/ now holds drafts. The dangerous
failure is not a missing draft -- it is a draft that quietly acquires
force: a registry entry pointing at unsigned bytes, a draft edited to look
signed, or `permitted_uses` filling up while `decision_state` still says
review_required.

Every rule here is checkable from the tree alone, which is the point:
the deny-by-default posture must be auditable without asking anyone what
they meant.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ROOT / "governance" / "decisions"
REGISTRY = ROOT / "governance" / "source_rights_registry.json"

BANNER = "UNSIGNED — NO FORCE"


def _registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def _drafts() -> list[Path]:
    if not DECISIONS.exists():
        return []
    return sorted(DECISIONS.glob("DRAFT_*.md"))


def test_every_draft_declares_itself_unsigned() -> None:
    for path in _drafts():
        text = path.read_text(encoding="utf-8")
        assert BANNER in text, (
            f"{path.name} lost its '{BANNER}' banner. A decision packet "
            "without it reads as an authorization; restore the banner or "
            "complete the signing lifecycle in decisions/README.md, which "
            "only the founder may do.")
        assert "signed_on (UTC):     ____" in text, (
            f"{path.name}'s signature block is no longer empty. If the "
            "founder signed, the file must be renamed off the DRAFT_ prefix "
            "and the registry updated in the same commit; a filled-in DRAFT "
            "is neither draft nor decision.")


def test_the_registry_never_points_at_a_draft() -> None:
    registry_text = REGISTRY.read_text(encoding="utf-8")
    for path in _drafts():
        assert path.name not in registry_text, (
            f"source_rights_registry.json references {path.name}, which is "
            "an unsigned draft. The registry may only bind to signed "
            "artifacts, updated in the signing commit itself.")


def test_drafted_sources_remain_deny_by_default() -> None:
    """Each draft names its source_id; that source must still be
    review_required with zero permitted uses. This is the invariant that
    makes drafting safe at all."""
    registry = _registry()
    assert registry["default_policy"] == "deny"
    by_id = {s["source_id"]: s for s in registry["sources"]}
    for path in _drafts():
        m = re.search(r"source_id \| `([a-z0-9_]+)`", path.read_text(encoding="utf-8"))
        assert m, f"{path.name} does not state its source_id in the identity table"
        source_id = m.group(1)
        assert source_id in by_id, (
            f"{path.name} names {source_id}, which is not in the registry; "
            "a packet for an unregistered source authorizes confusion")
        entry = by_id[source_id]
        assert entry["decision_state"] == "review_required", (
            f"{source_id} is {entry['decision_state']!r} but its packet is "
            "still a DRAFT; the two must change together in one commit")
        assert entry["permitted_uses"] == [], (
            f"{source_id} has permitted_uses {entry['permitted_uses']} while "
            "its decision packet is unsigned; deny-by-default has been "
            "breached")
        assert entry["signer_id"] is None and entry["decision_artifact_sha256"] is None


def test_the_vocabulary_file_is_present_when_drafts_exist() -> None:
    if _drafts():
        readme = DECISIONS / "README.md"
        assert readme.exists() and "permitted_uses" in readme.read_text(encoding="utf-8"), (
            "drafts exist but the lifecycle/vocabulary README is gone; the "
            "drafts' use lists would float free of any shared meaning")
