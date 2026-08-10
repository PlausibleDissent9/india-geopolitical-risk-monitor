"""Adversarial checks for the repository security-integrity baseline."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from src import security_integrity

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def security_tree(tmp_path: Path) -> Path:
    for directory in (".github", "governance", "scripts", "src"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    return tmp_path


def _registry(root: Path) -> dict:
    return json.loads(
        (root / "governance" / "security_integrity_registry.json").read_text(
            encoding="utf-8"
        )
    )


def _write_registry(root: Path, registry: dict) -> None:
    (root / "governance" / "security_integrity_registry.json").write_text(
        json.dumps(registry, indent=1) + "\n", encoding="utf-8"
    )


def _rehash_registered_script(root: Path, key: str) -> None:
    registry = _registry(root)
    record = registry["publisher"][key]
    record["sha256"] = hashlib.sha256((root / record["path"]).read_bytes()).hexdigest()
    _write_registry(root, registry)


def _refusal(root: Path, code: str) -> None:
    with pytest.raises(security_integrity.SecurityIntegrityError) as exc:
        security_integrity.validate_repository(root=root)
    assert exc.value.code == code


def test_current_repository_controls_generate_the_bounded_report() -> None:
    report = security_integrity.validate_repository()
    assert report["status"] == "static_repository_control_foundation"
    assert report["default_policy"] == "deny"
    assert report["controls"]["exact_post_rebase_publication_gate"] == {
        "status": "pass",
        "policy": "refuse_publish_on_red_candidate",
        "command": "bash scripts/gate.sh --committed",
        "push_paths_verified": 2,
    }
    # 13 since 2026-08-09: historical-intelligence.yml. This count is an
    # inventory lock -- a lane that appears without a deliberate edit here
    # is a lane nobody reviewed, so the number is meant to be updated in
    # the same commit that adds one, never loosened to an inequality.
    assert len(report["publishing_lanes"]) == 13
    assert report["controls"]["publisher_credential_isolation"] == {
        "status": "pass",
        "checkout_persist_credentials": False,
        "token_scope": "final_publication_step_only",
        "token_cleared_before_candidate_gate": True,
    }
    text = json.dumps(report).lower()
    assert "not a penetration test or security certification" in text
    assert "zero trust" not in text


def test_moving_action_tag_is_refused(security_tree: Path) -> None:
    path = security_tree / ".github" / "workflows" / "ci.yml"
    text = path.read_text(encoding="utf-8").replace(
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "actions/checkout@v7",
        1,
    )
    path.write_text(text, encoding="utf-8")
    _refusal(security_tree, "workflow_action_not_immutable")


def test_unregistered_action_commit_is_refused(security_tree: Path) -> None:
    path = security_tree / ".github" / "workflows" / "ci.yml"
    text = path.read_text(encoding="utf-8").replace(
        "3d3c42e5aac5ba805825da76410c181273ba90b1", "a" * 40, 1
    )
    path.write_text(text, encoding="utf-8")
    _refusal(security_tree, "workflow_action_unregistered")


def test_shallow_checkout_is_refused(security_tree: Path) -> None:
    path = security_tree / ".github" / "workflows" / "ci.yml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("fetch-depth: 0", "fetch-depth: 1", 1),
        encoding="utf-8",
    )
    _refusal(security_tree, "workflow_checkout_history_shallow")


def test_persisted_checkout_credential_is_refused(security_tree: Path) -> None:
    path = security_tree / ".github" / "workflows" / "ci.yml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "persist-credentials: false", "persist-credentials: true", 1
        ),
        encoding="utf-8",
    )
    _refusal(security_tree, "workflow_checkout_credentials_persist")


def test_publisher_without_dev_environment_is_refused(security_tree: Path) -> None:
    path = security_tree / ".github" / "workflows" / "daily.yml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "pip install -r requirements.txt -r requirements-dev.txt",
            "pip install -r requirements.txt",
            1,
        ),
        encoding="utf-8",
    )
    _refusal(security_tree, "publisher_environment_incomplete")


def test_new_actions_write_permission_is_refused(security_tree: Path) -> None:
    path = security_tree / ".github" / "workflows" / "ci.yml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "  contents: read\n", "  contents: read\n  actions: write\n", 1
        ),
        encoding="utf-8",
    )
    _refusal(security_tree, "workflow_actions_write_set_mismatch")


def test_direct_final_recovery_cas_must_keep_frozen_parent_guard(
    security_tree: Path,
) -> None:
    path = security_tree / ".github" / "workflows" / "morning.yml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'REMOTE_COMMIT=$(git rev-parse origin/main)',
            'REMOTE_COMMIT="unguarded"',
            1,
        ),
        encoding="utf-8",
    )
    _refusal(security_tree, "publisher_frozen_cas_incomplete")


def test_job_level_permission_override_is_refused(security_tree: Path) -> None:
    path = security_tree / ".github" / "workflows" / "ci.yml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "  checks:\n", "  checks:\n    permissions:\n      contents: write\n", 1
        ),
        encoding="utf-8",
    )
    _refusal(security_tree, "workflow_permission_block_count_invalid")


def test_publisher_without_final_step_token_is_refused(security_tree: Path) -> None:
    path = security_tree / ".github" / "workflows" / "daily.yml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "          IGRM_PUBLISH_TOKEN: ${{ secrets.GITHUB_TOKEN }}\n", "", 1
        ),
        encoding="utf-8",
    )
    _refusal(security_tree, "publisher_ephemeral_token_missing")


def test_registered_but_unguarded_push_script_is_still_refused(
    security_tree: Path,
) -> None:
    path = security_tree / "scripts" / "publish_push.sh"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "if ! gate_candidate; then exit 1; fi", "true # gate removed", 1
        ),
        encoding="utf-8",
    )
    _rehash_registered_script(security_tree, "push_script")
    _refusal(security_tree, "publisher_push_guard_count_invalid")


def test_registered_security_implementation_cannot_drift(security_tree: Path) -> None:
    path = security_tree / "src" / "security_integrity.py"
    path.write_text(path.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
    _refusal(security_tree, "security_registered_hash_mismatch")
