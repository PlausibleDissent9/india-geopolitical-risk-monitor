"""Adversarial checks for the repository security-integrity baseline."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
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
    assert report["status"] == "repository_self_consistency_only"
    assert report["default_policy"] == "deny"
    assert report["controls"]["exact_post_rebase_publication_gate"] == {
        "status": "self_consistent_unattested_transition",
        "policy": "refuse_publish_on_red_candidate",
        # --publish since 2026-08-11. The control is unchanged in strength:
        # it still requires a full gate on the committed candidate by exact
        # command string, and still refuses a red one. --publish differs only
        # by excluding assertions about the already-served site, which
        # deadlocked every publisher (see scripts/gate.sh).
        "command": "bash scripts/gate.sh --publish",
        "final_cas_command": "bash scripts/gate.sh --publish",
        "push_paths_verified": 3,
        "transition_authority": "unavailable_no_external_signature",
    }
    assert report["scope"]["successor_transition_external_authority"] is False
    assert report["controls"]["public_api_byte_manifest_barrier"] == {
        "status": "repository_self_consistency_only",
        "generic_post_rebase_refresh_paths": 2,
        "final_candidate_classes": ["final", "refusal"],
        "source": "captured_git_index_or_tree",
        "self_excluded_endpoint": "data/public_api_byte_manifest.json",
        "signed": False,
        "authenticated_deployment": False,
        "atomic_hosted_snapshot": False,
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
    path = security_tree / "scripts" / "publish_final_cas.sh"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "remote_commit=$(git rev-parse origin/main)",
            'remote_commit="unguarded"',
            1,
        ),
        encoding="utf-8",
    )
    _rehash_registered_script(security_tree, "final_cas_script")
    _refusal(security_tree, "publisher_final_cas_function_digest_invalid")


def test_registered_final_publisher_refuses_a_second_or_earlier_push(
    security_tree: Path,
) -> None:
    path = security_tree / "scripts" / "publish_final_cas.sh"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "  /usr/bin/time -v bash scripts/gate.sh --publish",
            "  git push origin HEAD:main\n"
            "  /usr/bin/time -v bash scripts/gate.sh --publish",
            1,
        ),
        encoding="utf-8",
    )
    _rehash_registered_script(security_tree, "final_cas_script")
    _refusal(security_tree, "publisher_final_cas_push_count_invalid")


def test_registered_final_publisher_refuses_dead_code_gate_fragments(
    security_tree: Path,
) -> None:
    path = security_tree / "scripts" / "publish_final_cas.sh"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "  /usr/bin/time -v bash scripts/gate.sh --publish",
            "  if false; then\n"
            "    /usr/bin/time -v bash scripts/gate.sh --publish\n"
            "  fi",
            1,
        ),
        encoding="utf-8",
    )
    _rehash_registered_script(security_tree, "final_cas_script")
    _refusal(security_tree, "publisher_final_cas_function_digest_invalid")


@pytest.mark.parametrize(
    ("needle", "replacement"),
    (
        (
            "  git fetch --quiet origin main",
            "  if false; then\n    git fetch --quiet origin main\n  fi",
        ),
        (
            "  git fetch --quiet origin main",
            "  true || git fetch --quiet origin main",
        ),
        (
            "  git fetch --quiet origin main",
            "  return 0\n  git fetch --quiet origin main",
        ),
        (
            '  if [ "$candidate_parent" != "$BASE_COMMIT" ]; then',
            '  if false; then\n    if [ "$candidate_parent" != "$BASE_COMMIT" ]; then',
        ),
        (
            '    git push origin "$FROZEN_CANDIDATE_SHA:main"',
            '    true || git push origin "$FROZEN_CANDIDATE_SHA:main"',
        ),
        (
            '  if ! release_proof=$(python -m src.final_publication \\',
            '  if ! release_proof=$(true || python -m src.final_publication \\',
        ),
        (
            '  if [ "$release_candidate" != "$FROZEN_CANDIDATE_SHA" ]; then',
            '  if false && [ "$release_candidate" != "$FROZEN_CANDIDATE_SHA" ]; then',
        ),
    ),
)
def test_final_cas_push_function_rejects_dead_or_bypassed_dominators(
    security_tree: Path, needle: str, replacement: str
) -> None:
    path = security_tree / "scripts" / "publish_final_cas.sh"
    text = path.read_text(encoding="utf-8")
    assert needle in text
    path.write_text(text.replace(needle, replacement, 1), encoding="utf-8")
    _rehash_registered_script(security_tree, "final_cas_script")
    _refusal(security_tree, "publisher_final_cas_function_digest_invalid")


@pytest.mark.parametrize(
    ("replacement", "code"),
    (
        ("true || require_frozen_base", "publisher_final_cas_dispatch_invalid"),
        (
            "if false; then require_frozen_base; fi",
            "publisher_final_cas_dispatch_invalid",
        ),
        (
            "return 0\nrequire_frozen_base",
            "publisher_final_cas_dispatch_digest_invalid",
        ),
    ),
)
def test_final_cas_dispatch_rejects_dead_or_skipped_base_guard(
    security_tree: Path, replacement: str, code: str
) -> None:
    path = security_tree / "scripts" / "publish_final_cas.sh"
    text = path.read_text(encoding="utf-8")
    marker = "\nrequire_frozen_base\nif ["
    assert marker in text
    path.write_text(
        text.replace(marker, f"\n{replacement}\nif [", 1), encoding="utf-8"
    )
    _rehash_registered_script(security_tree, "final_cas_script")
    _refusal(security_tree, code)


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


def test_registered_generic_publisher_cannot_skip_manifest_refresh(
    security_tree: Path,
) -> None:
    path = security_tree / "scripts" / "publish_push.sh"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "    if ! refresh_public_api_byte_manifest; then exit 1; fi",
            "    true # manifest refresh removed",
            1,
        ),
        encoding="utf-8",
    )
    _rehash_registered_script(security_tree, "push_script")
    _refusal(security_tree, "publisher_manifest_refresh_count_invalid")


def test_registered_final_publisher_stages_manifest_for_both_classes(
    security_tree: Path,
) -> None:
    path = security_tree / "scripts" / "publish_final_cas.sh"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "  stage_public_api_byte_manifest\n",
            "  true # manifest stage removed\n",
            1,
        ),
        encoding="utf-8",
    )
    _rehash_registered_script(security_tree, "final_cas_script")
    _refusal(security_tree, "publisher_final_manifest_call_count_invalid")


def test_registered_security_implementation_cannot_drift(security_tree: Path) -> None:
    path = security_tree / "src" / "security_integrity.py"
    path.write_text(path.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
    _refusal(security_tree, "security_registered_hash_mismatch")


def test_prior_commit_anchor_rejects_coordinated_cas_and_validator_reseal(
    tmp_path: Path,
) -> None:
    if not (ROOT / ".git").exists():
        pytest.skip("requires committed Git history for the predecessor anchor")
    root = tmp_path / "coordinated-reseal"
    subprocess.run(
        ["git", "clone", "-q", "--shared", str(ROOT), str(root)], check=True
    )
    shutil.copy2(
        ROOT / "src/security_integrity.py", root / "src/security_integrity.py"
    )
    shutil.copy2(
        ROOT / "governance/security_integrity_registry.json",
        root / "governance/security_integrity_registry.json",
    )
    shutil.copy2(
        ROOT / "scripts/publish_final_cas.sh",
        root / "scripts/publish_final_cas.sh",
    )
    shutil.copy2(
        ROOT / "scripts/publish_push.sh",
        root / "scripts/publish_push.sh",
    )
    script_path = root / "scripts/publish_final_cas.sh"
    script = script_path.read_text(encoding="utf-8").replace(
        "  git fetch --quiet origin main",
        "  true || git fetch --quiet origin main",
        1,
    )
    script_path.write_text(script, encoding="utf-8")
    body = re.search(
        r"(?ms)^push_frozen_parent\(\) \{\n(?P<body>.*?)^\}\s*$", script
    )
    assert body is not None
    resealed_function = hashlib.sha256(
        body.group("body").encode("utf-8")
    ).hexdigest()
    implementation_path = root / "src/security_integrity.py"
    implementation = implementation_path.read_text(encoding="utf-8")
    implementation = implementation.replace(
        security_integrity.FINAL_CAS_FUNCTION_SHA256["push_frozen_parent"],
        resealed_function,
        1,
    )
    implementation_path.write_text(implementation, encoding="utf-8")
    registry = _registry(root)
    registry["publisher"]["final_cas_script"]["sha256"] = hashlib.sha256(
        script_path.read_bytes()
    ).hexdigest()
    registry["implementation"]["sha256"] = hashlib.sha256(
        implementation_path.read_bytes()
    ).hexdigest()
    _write_registry(root, registry)

    result = subprocess.run(
        [sys.executable, "-m", "src.security_integrity", "--check"],
        cwd=root,
        env={**os.environ, "PYTHONPATH": str(root)},
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "security_prior_cas_transition_rejected" in result.stderr


def test_coordinated_successor_reseal_cannot_claim_independent_trust(
    tmp_path: Path,
) -> None:
    if not (ROOT / ".git").exists():
        pytest.skip("requires committed Git history for the predecessor anchor")
    root = tmp_path / "coordinated-successor-reseal"
    subprocess.run(
        ["git", "clone", "-q", "--shared", str(ROOT), str(root)], check=True
    )
    for relative in (
        "src/security_integrity.py",
        "scripts/publish_final_cas.sh",
        "scripts/publish_push.sh",
        "governance/security_integrity_registry.json",
    ):
        shutil.copy2(ROOT / relative, root / relative)

    malicious_transition = (
        "  true # release-rights bypass\n"
        '  # --check-release-candidate "$CANDIDATE_CLASS"\n'
        '  # --expected-candidate-sha "$FROZEN_CANDIDATE_SHA"\n'
        '  # --base-commit "$BASE_COMMIT"\n'
        '  # --expected-target "$TARGET"\n'
        '  release_proof="{\\"candidate_sha\\": '
        '\\"$FROZEN_CANDIDATE_SHA\\", '
        '\\"candidate_class\\": \\"$CANDIDATE_CLASS\\"}"\n'
        '  release_candidate="$FROZEN_CANDIDATE_SHA"\n'
        '  release_class="$CANDIDATE_CLASS"\n'
        '  if [ "$release_candidate" != "$FROZEN_CANDIDATE_SHA" ]; then\n'
        '    echo "::error::unreachable candidate mismatch"\n'
        "    return 1\n"
        "  fi\n"
        '  if [ "$release_class" != "$CANDIDATE_CLASS" ]; then\n'
        '    echo "::error::unreachable class mismatch"\n'
        "    return 1\n"
        "  fi\n"
        "  printf '%s\\n' \"$release_proof\"\n"
    )
    script_path = root / "scripts/publish_final_cas.sh"
    script = script_path.read_text(encoding="utf-8")
    start = script.index("  # Rights are time-varying authority.")
    end = script.index("  GIT_CONFIG_COUNT=1", start)
    script = script[:start] + malicious_transition + script[end:]
    script_path.write_text(script, encoding="utf-8")
    body = re.search(
        r"(?ms)^push_frozen_parent\(\) \{\n(?P<body>.*?)^\}\s*$", script
    )
    assert body is not None
    resealed_function = hashlib.sha256(
        body.group("body").encode("utf-8")
    ).hexdigest()

    implementation_path = root / "src/security_integrity.py"
    implementation = implementation_path.read_text(encoding="utf-8")
    implementation = re.sub(
        r'(?s)_RIGHTS_RELEASE_TRANSITION = """.*?"""\n\n',
        lambda _match: (
            f"_RIGHTS_RELEASE_TRANSITION = {malicious_transition!r}\n\n"
        ),
        implementation,
        count=1,
    )
    implementation = implementation.replace(
        security_integrity.FINAL_CAS_FUNCTION_SHA256["push_frozen_parent"],
        resealed_function,
        1,
    )
    implementation = implementation.replace(
        '"release_candidate=$(printf",',
        "'release_candidate=\"$FROZEN_CANDIDATE_SHA\"',",
        1,
    ).replace(
        '"release_class=$(printf",',
        "'release_class=\"$CANDIDATE_CLASS\"',",
        1,
    )
    implementation_path.write_text(implementation, encoding="utf-8")
    registry = _registry(root)
    registry["publisher"]["final_cas_script"]["sha256"] = hashlib.sha256(
        script_path.read_bytes()
    ).hexdigest()
    registry["implementation"]["sha256"] = hashlib.sha256(
        implementation_path.read_bytes()
    ).hexdigest()
    _write_registry(root, registry)

    result = subprocess.run(
        [sys.executable, "-m", "src.security_integrity", "--write"],
        cwd=root,
        env={**os.environ, "PYTHONPATH": str(root)},
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(
        (root / "docs/data/security_integrity.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "repository_self_consistency_only"
    assert report["controls"]["exact_post_rebase_publication_gate"]["status"] == (
        "self_consistent_unattested_transition"
    )
    assert (
        report["controls"]["exact_post_rebase_publication_gate"][
            "transition_authority"
        ]
        == "unavailable_no_external_signature"
    )
