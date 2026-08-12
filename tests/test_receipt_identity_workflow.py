"""Isolation and public-display locks for the receipt-identity lane."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from src import receipt_identity

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/receipt-identity.yml"


def test_workflow_is_independent_exactly_staged_and_bounded() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert len(re.findall(r'^    - cron: "[^"]+"', text, re.M)) == 3
    assert "python -m src.receipt_identity" in text
    assert "--verify-payload --expected-target \"$TARGET\"" in text
    assert "IGRM_PUBLISH_CLASS: receipt_identity" in text
    assert "persist-credentials: false" in text
    assert "continue-on-error: true" in text
    assert "git add -- docs/data/receipt_identity.json" in text
    assert "git add -- docs/data/receipt_identity.json\n" in text
    for forbidden in (
        "src.aggregate",
        "src.daily",
        "src.fetch_gdelt",
        "docs/data/latest.json",
        "docs/data/receipts.json",
        "docs/data/receipts_archive.json",
        "data/raw/ngram_days",
        "data/raw/receipt_days",
        "weekly",
        "notes.json",
        "feed.xml",
    ):
        assert forbidden not in text


def test_current_public_payload_is_truthful_value_free_pending_status() -> None:
    payload = json.loads(
        (ROOT / receipt_identity.OUTPUT_RELATIVE).read_text(encoding="utf-8")
    )
    profile = json.loads(
        (ROOT / "governance/gdelt_receipt_identity_profile.json").read_text(
            encoding="utf-8"
        )
    )
    assert profile["activation"]["state"] == "inactive_pending_human_signature"
    assert payload["state"] == "unavailable"
    assert "authority" not in payload
    assert all(
        block == {"state": "unavailable", "reason_code": "rights_blocked"}
        for block in payload["channels"].values()
    )
    predecessor = payload["predecessor"]
    assert re.fullmatch(r"[0-9a-f]{40}", predecessor["commit_sha"])
    if predecessor["state"] == "path_absent":
        introduction = subprocess.run(
            [
                "git",
                "log",
                "--diff-filter=A",
                "--format=%H",
                "--",
                receipt_identity.OUTPUT_RELATIVE.as_posix(),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        parent = subprocess.run(
            ["git", "rev-parse", f"{introduction}^"], cwd=ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert predecessor == {
            "state": "path_absent",
            "commit_sha": parent,
            "blob_git_sha1": None,
            "blob_sha256": None,
            "target_date": None,
        }
    else:
        assert predecessor["state"] in {"different_target", "same_target"}
        assert re.fullmatch(r"[0-9a-f]{40}", predecessor["blob_git_sha1"])
        assert re.fullmatch(r"[0-9a-f]{64}", predecessor["blob_sha256"])
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", predecessor["target_date"])
    encoded = json.dumps(payload).lower()
    assert '"articles"' not in encoded
    assert "snippet" not in encoded


def test_receipts_page_only_renders_safe_same_day_identity_links() -> None:
    page = (ROOT / "docs/receipts.html").read_text(encoding="utf-8")
    assert 'j("data/receipt_identity.json")' in page
    assert "identity.target_date === latest.date" in page
    assert "stale or future links are not shown" in page
    assert "!u.username && !u.password" in page
    assert ".articles.slice(0, 5).map" in page
    assert 'typeof a !== "object"' in page
    assert 'rel="noopener noreferrer"' in page
    assert "not a score input" in page


def test_publisher_guard_is_immediately_inside_the_shared_push_function() -> None:
    text = (ROOT / "scripts/publish_push.sh").read_text(encoding="utf-8")
    start = text.index("git_push() {")
    end = text.index("\n}", start)
    body = text[start:end]
    guard = body.index('IGRM_PUBLISH_CLASS:-}" = "receipt_identity"')
    credential = body.index("GIT_CONFIG_COUNT=1")
    assert guard < credential
    assert body.count("src.receipt_identity --check-release-rights") == 1


def test_lane_binds_prewrite_and_release_to_exact_remote_predecessor() -> None:
    module = (ROOT / "src/receipt_identity.py").read_text(encoding="utf-8")
    assert 'ref="HEAD"' in module
    assert '"origin/main"' in module
    assert 'mode != "100644" or object_type != "blob"' in module
    assert "receipt_identity_release_predecessor_remote_drift" in module
    assert "receipt_identity_predecessor_channel_regression" in module
    assert "receipt_identity_predecessor_articles_changed" in module


def test_new_lane_does_not_modify_weekly_note_surfaces() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    module = (ROOT / "src/receipt_identity.py").read_text(encoding="utf-8")
    for forbidden in ("notes.json", "feed.xml", "weekly-note", "weekly_note"):
        assert forbidden not in workflow
        assert forbidden not in module
