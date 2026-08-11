"""Fail-closed repository security controls and a bounded public report.

This is deliberately narrower than a security certification. It verifies the
controls that are visible in this repository: immutable workflow actions,
least-privilege workflow permissions, full Git history for frozen evidence,
publisher environment parity, and the exact post-rebase gate before a bot
push. It cannot verify GitHub account settings, branch protection, MFA,
secrets, the hosted platform, or an external penetration test.

Standalone::

    python -m src.security_integrity --check
    python -m src.security_integrity --write
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "governance" / "security_integrity_registry.json"
PUBLIC_REPORT_PATH = ROOT / "docs" / "data" / "security_integrity.json"

ACTION_RE = re.compile(r"uses:\s*(?P<action>[^@\s]+)@(?P<ref>[^\s#]+)")
PERMISSIONS_RE = re.compile(r"^permissions:\n(?P<body>(?:  [^\n]+\n)+)", re.M)
PERMISSION_ROW_RE = re.compile(r"^  (?P<scope>[a-z-]+): (?P<level>read|write|none)$", re.M)
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
FINAL_CAS_GATE_COMMAND = "bash scripts/gate.sh --publish"

# These bodies are deliberately tiny, reviewable shell grammars. The full
# script is registry-pinned; these independent implementation pins prevent an
# attacker from wrapping a required fragment in dead code and merely resealing
# the script's registry hash.
FINAL_CAS_FUNCTION_SHA256 = {
    "require_frozen_base": (
        "5b1b35c93e04107f700430b24afc197dc68b91b46c3d1b5e0f2c765687b77f25"
    ),
    "publish_gated_candidate": (
        "d5ac0aa01f94393637d100157f5db32a81e5e75781004dbfb21aeef26eb1134a"
    ),
    "push_frozen_parent": (
        "2370b61bca5ed688272960332f69045cfbb18908bb72793a56c05d615797508b"
    ),
}
FINAL_CAS_DISPATCH_SHA256 = (
    "792dff3ece39d417edc12565c3dd97f8d3e0d7d05ed10273f239ea97c5e2d3f5"
)
TRUSTED_SECURITY_BASELINE_COMMIT = "1ba3618b832a5ee64ea86b3f97e26145ee72c178"
TRUSTED_SECURITY_IMPLEMENTATION_SHA256 = (
    "47630c10edd582e19e23a733de9ba5e632e8a587f42551a90363628b40978718"
)
TRUSTED_FINAL_CAS_SCRIPT_SHA256 = (
    "64435b77b8ff876160f7bb62cda478c687e5980f22b8da2da867fbae2e8b5234"
)
_RIGHTS_RELEASE_TRANSITION = """  # Rights are time-varying authority. Recheck after every potentially slow
  # gate/remote operation for value-bearing finals. A disjoint refusal uses
  # separate authority: its exact candidate diff must contain only value-free
  # status/UI paths. Both proofs bind the frozen candidate SHA and class.
  if ! release_proof=$(python -m src.final_publication \\
    --check-release-candidate "$CANDIDATE_CLASS" \\
    --expected-candidate-sha "$FROZEN_CANDIDATE_SHA" \\
    --base-commit "$BASE_COMMIT" \\
    --expected-target "$TARGET"); then
    echo "::error::CAS refusal: candidate-class release proof is not valid"
    return 1
  fi
  release_candidate=$(printf '%s\\n' "$release_proof" | \\
    sed -n 's/.*"candidate_sha": "\\([0-9a-f]*\\)".*/\\1/p')
  release_class=$(printf '%s\\n' "$release_proof" | \\
    sed -n 's/.*"candidate_class": "\\([a-z]*\\)".*/\\1/p')
  if [ "$release_candidate" != "$FROZEN_CANDIDATE_SHA" ]; then
    echo "::error::CAS refusal: release proof candidate $release_candidate is not frozen candidate $FROZEN_CANDIDATE_SHA"
    return 1
  fi
  if [ "$release_class" != "$CANDIDATE_CLASS" ]; then
    echo "::error::CAS refusal: release proof class $release_class is not candidate class $CANDIDATE_CLASS"
    return 1
  fi
  printf '%s\\n' "$release_proof"
"""


class SecurityIntegrityError(ValueError):
    """Stable refusal code for a repository security-control violation."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise SecurityIntegrityError(code, detail)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("security_registry_duplicate_key", key)
        result[key] = value
    return result


def _read_object(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SecurityIntegrityError(code, str(path)) from exc
    if not isinstance(value, dict):
        _fail(code, str(path))
    return cast(dict[str, Any], value)


def _safe_path(root: Path, value: object, code: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        _fail(code)
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or ".." in parsed.parts or str(parsed) != value:
        _fail(code, value)
    path = root.joinpath(*parsed.parts)
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        raise SecurityIntegrityError(code, value) from exc
    return path


def _sha256(path: Path, code: str) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise SecurityIntegrityError(code, str(path)) from exc


def _string(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(code)
    return value


def _string_list(value: object, code: str) -> list[str]:
    if not isinstance(value, list) or not value:
        _fail(code)
    rows = [_string(item, code) for item in value]
    if len(rows) != len(set(rows)):
        _fail(code)
    return rows


def _registry(root: Path, registry: dict[str, Any] | None) -> dict[str, Any]:
    value = registry or _read_object(
        root / "governance" / "security_integrity_registry.json",
        "security_registry_unreadable",
    )
    if (
        value.get("schema_version") != "1.0.0"
        or value.get("effective") != "2026-08-08"
        or value.get("default_policy") != "deny"
        or value.get("status") != "repository_control_baseline"
    ):
        _fail("security_registry_identity_invalid")
    return value


def _verify_registered_file(
    root: Path, record: object, identity: str
) -> tuple[str, str]:
    if not isinstance(record, dict):
        _fail("security_registered_file_invalid", identity)
    path_value = record.get("path")
    expected = record.get("sha256")
    path = _safe_path(root, path_value, "security_registered_path_invalid")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        _fail("security_registered_hash_invalid", identity)
    actual = _sha256(path, "security_registered_file_unreadable")
    if actual != expected:
        _fail("security_registered_hash_mismatch", f"{identity}:{path_value}")
    return cast(str, path_value), actual


def _permissions(name: str, text: str) -> dict[str, str]:
    permission_blocks = re.findall(r"(?m)^\s*permissions:\s*$", text)
    if len(permission_blocks) != 1:
        _fail("workflow_permission_block_count_invalid", name)
    match = PERMISSIONS_RE.search(text)
    if not match:
        _fail("workflow_permissions_missing", name)
    rows = {
        row.group("scope"): row.group("level")
        for row in PERMISSION_ROW_RE.finditer(match.group("body"))
    }
    if not rows:
        _fail("workflow_permissions_invalid", name)
    if set(rows) - {"contents", "actions"}:
        _fail("workflow_permission_scope_unregistered", name)
    if rows.get("contents") not in {"read", "write"}:
        _fail("workflow_contents_permission_invalid", name)
    return rows


def _checkout_has_full_history(name: str, text: str, action_sha: str) -> None:
    matches = list(
        re.finditer(
            rf"(?ms)^\s*- uses: actions/checkout@{re.escape(action_sha)}[^\n]*\n"
            rf"(?P<body>.*?)(?=^\s*- (?:uses:|run:|name:)|^\s{{0,6}}[A-Za-z_-]+:|\Z)",
            text,
        )
    )
    if not matches:
        _fail("workflow_checkout_missing", name)
    for match in matches:
        if not re.search(r"(?m)^\s+fetch-depth:\s*0\s*$", match.group("body")):
            _fail("workflow_checkout_history_shallow", name)
        if not re.search(
            r"(?m)^\s+persist-credentials:\s*false\s*$", match.group("body")
        ):
            _fail("workflow_checkout_credentials_persist", name)


def _shell_function(text: str, name: str) -> str:
    matches = list(
        re.finditer(
            rf"(?ms)^{re.escape(name)}\(\) \{{\n(?P<body>.*?)^\}}\s*$", text
        )
    )
    if len(matches) != 1:
        _fail("publisher_final_cas_function_count_invalid", name)
    return matches[0].group("body")


def _shell_function_end(text: str, name: str) -> int:
    matches = list(
        re.finditer(
            rf"(?ms)^{re.escape(name)}\(\) \{{\n(?P<body>.*?)^\}}\s*$", text
        )
    )
    if len(matches) != 1:
        _fail("publisher_final_cas_function_count_invalid", name)
    return matches[0].end()


def _validate_against_predecessor_projection(
    root: Path, registry: dict[str, Any]
) -> None:
    """Prove the unchanged predecessor, not authority for its successor.

    The cbb verifier authenticates the controls that predate the additive
    release-rights block. The successor block and this projection live in the
    same mutable commit, so their agreement is repository self-consistency,
    not independent transition authorization. The public result is explicitly
    downgraded until a signature rooted outside this commit is available.
    """

    result = subprocess.run(
        [
            "git",
            "show",
            f"{TRUSTED_SECURITY_BASELINE_COMMIT}:src/security_integrity.py",
        ],
        cwd=ROOT,
        capture_output=True,
    )
    if result.returncode != 0:
        _fail("security_prior_trust_anchor_unavailable")
    trusted_bytes = result.stdout
    if hashlib.sha256(trusted_bytes).hexdigest() != (
        TRUSTED_SECURITY_IMPLEMENTATION_SHA256
    ):
        _fail("security_prior_trust_anchor_digest_invalid")
    script_result = subprocess.run(
        [
            "git",
            "show",
            f"{TRUSTED_SECURITY_BASELINE_COMMIT}:scripts/publish_final_cas.sh",
        ],
        cwd=ROOT,
        capture_output=True,
    )
    if script_result.returncode != 0 or hashlib.sha256(
        script_result.stdout
    ).hexdigest() != TRUSTED_FINAL_CAS_SCRIPT_SHA256:
        _fail("security_prior_cas_anchor_invalid")
    registry_result = subprocess.run(
        [
            "git",
            "show",
            f"{TRUSTED_SECURITY_BASELINE_COMMIT}:"
            "governance/security_integrity_registry.json",
        ],
        cwd=ROOT,
        capture_output=True,
    )
    if registry_result.returncode != 0:
        _fail("security_prior_registry_anchor_unavailable")
    try:
        predecessor_registry = json.loads(registry_result.stdout)
    except json.JSONDecodeError:
        _fail("security_prior_registry_anchor_invalid")
    predecessor_publisher = predecessor_registry.get("publisher")
    if not isinstance(predecessor_publisher, dict):
        _fail("security_prior_registry_anchor_invalid")
    predecessor_script = script_result.stdout.decode("utf-8")
    current_script = (root / "scripts/publish_final_cas.sh").read_text(
        encoding="utf-8"
    )
    predecessor_push = _shell_function(predecessor_script, "push_frozen_parent")
    prior_locals = "  local candidate_head parent_count candidate_parent remote_commit\n"
    successor_locals = (
        "  local candidate_head parent_count candidate_parent remote_commit "
        "release_proof release_candidate release_class\n"
    )
    marker = "  GIT_CONFIG_COUNT=1 \\\n"
    if predecessor_push.count(marker) != 1 or predecessor_push.count(prior_locals) != 1:
        _fail("security_prior_cas_transition_marker_invalid")
    expected_push = predecessor_push.replace(
        prior_locals, successor_locals, 1
    ).replace(
        marker, _RIGHTS_RELEASE_TRANSITION + marker, 1
    )
    if _shell_function(current_script, "push_frozen_parent") != expected_push:
        _fail("security_prior_cas_transition_rejected")

    namespace: dict[str, Any] = {
        "__name__": "_igrm_trusted_security_baseline",
        "__file__": (
            f"git:{TRUSTED_SECURITY_BASELINE_COMMIT}:src/security_integrity.py"
        ),
    }
    try:
        exec(compile(trusted_bytes, namespace["__file__"], "exec"), namespace)
        trusted_validate = namespace["validate_repository"]
        projected_registry = json.loads(json.dumps(registry))
        projected_registry["implementation"]["sha256"] = (
            TRUSTED_SECURITY_IMPLEMENTATION_SHA256
        )
        projected_registry["publisher"]["final_cas_script"]["sha256"] = (
            TRUSTED_FINAL_CAS_SCRIPT_SHA256
        )
        projected_registry["publisher"]["required_gate_command"] = (
            predecessor_publisher["required_gate_command"]
        )
        with tempfile.TemporaryDirectory(prefix="igrm-security-parent-") as temp:
            projected = Path(temp)
            shutil.copytree(
                root / ".github/workflows", projected / ".github/workflows"
            )
            for key in ("push_script", "gate_script"):
                record = predecessor_publisher.get(key)
                if not isinstance(record, dict):
                    _fail("security_prior_registry_anchor_invalid")
                projected_registry["publisher"][key] = record
                relative = Path(record["path"])
                destination = projected / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                anchored = subprocess.run(
                    [
                        "git",
                        "show",
                        f"{TRUSTED_SECURITY_BASELINE_COMMIT}:{relative.as_posix()}",
                    ],
                    cwd=ROOT,
                    capture_output=True,
                )
                if anchored.returncode != 0:
                    _fail("security_prior_registered_file_unavailable", key)
                destination.write_bytes(anchored.stdout)
            final_relative = Path(
                projected_registry["publisher"]["final_cas_script"]["path"]
            )
            final_destination = projected / final_relative
            final_destination.parent.mkdir(parents=True, exist_ok=True)
            final_destination.write_bytes(script_result.stdout)
            implementation_relative = Path(
                projected_registry["implementation"]["path"]
            )
            implementation_destination = projected / implementation_relative
            implementation_destination.parent.mkdir(parents=True, exist_ok=True)
            implementation_destination.write_bytes(trusted_bytes)
            trusted_validate(root=projected, registry=projected_registry)
    except Exception as exc:  # noqa: BLE001 - translate prior verifier refusal
        detail = str(getattr(exc, "code", type(exc).__name__))
        _fail("security_prior_trust_anchor_rejected", detail)


def validate_repository(
    *, root: Path = ROOT, registry: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Verify the registered repository controls and return a public report."""

    value = _registry(root, registry)
    implementation = value.get("implementation")
    publisher = value.get("publisher")
    if not isinstance(publisher, dict):
        _fail("security_publisher_registry_invalid")
    _verify_registered_file(root, implementation, "implementation")
    push_path, _ = _verify_registered_file(
        root, publisher.get("push_script"), "push_script"
    )
    gate_path, _ = _verify_registered_file(
        root, publisher.get("gate_script"), "gate_script"
    )
    final_cas_path, _ = _verify_registered_file(
        root, publisher.get("final_cas_script"), "final_cas_script"
    )

    action_records = value.get("actions")
    if not isinstance(action_records, dict) or not action_records:
        _fail("security_action_registry_invalid")
    allowed_actions: dict[str, str] = {}
    for action, record in action_records.items():
        if not isinstance(action, str) or not isinstance(record, dict):
            _fail("security_action_registry_invalid")
        sha = record.get("sha256")
        version = record.get("version")
        if not isinstance(sha, str) or not HEX40_RE.fullmatch(sha):
            _fail("security_action_hash_invalid", action)
        if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
            _fail("security_action_version_invalid", action)
        allowed_actions[action] = sha

    workflow_dir = _safe_path(
        root, value.get("workflow_directory"), "security_workflow_directory_invalid"
    )
    workflow_paths = sorted(workflow_dir.glob("*.yml"))
    if not workflow_paths:
        _fail("security_workflows_missing")
    allowed_actions_write = set(
        _string_list(
            value.get("actions_write_workflows"),
            "security_actions_write_registry_invalid",
        )
    )
    publisher_marker = _string(
        publisher.get("workflow_marker"), "security_publisher_marker_invalid"
    )
    install_fragment = _string(
        publisher.get("required_install_fragment"),
        "security_publisher_install_invalid",
    )
    token_fragment = _string(
        publisher.get("required_token_fragment"),
        "security_publisher_token_fragment_invalid",
    )
    gate_command = _string(
        publisher.get("required_gate_command"), "security_gate_command_invalid"
    )

    action_references = 0
    publishing_lanes: list[str] = []
    observed_actions_write: set[str] = set()
    checkout_sha = allowed_actions.get("actions/checkout")
    if checkout_sha is None:
        _fail("security_checkout_action_unregistered")

    for path in workflow_paths:
        name = path.name
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise SecurityIntegrityError("security_workflow_unreadable", name) from exc
        permissions = _permissions(name, text)
        if permissions.get("actions") == "write":
            observed_actions_write.add(name)
        elif "actions" in permissions and permissions["actions"] != "none":
            _fail("workflow_actions_permission_invalid", name)

        actions = list(ACTION_RE.finditer(text))
        for match in actions:
            action = match.group("action")
            ref = match.group("ref")
            if action.startswith("./"):
                _fail("workflow_local_action_unregistered", f"{name}:{action}")
            if not HEX40_RE.fullmatch(ref):
                _fail("workflow_action_not_immutable", f"{name}:{action}@{ref}")
            if allowed_actions.get(action) != ref:
                _fail("workflow_action_unregistered", f"{name}:{action}@{ref}")
            action_references += 1
        if "actions/checkout@" in text:
            _checkout_has_full_history(name, text, checkout_sha)

        final_cas_marker = f"bash {final_cas_path}"
        direct_frozen_cas = "git push origin HEAD:main" in text
        if direct_frozen_cas:
            _fail("publisher_direct_push_outside_registered_script", name)
        if publisher_marker in text or final_cas_marker in text:
            publishing_lanes.append(name)
            if permissions.get("contents") != "write":
                _fail("publisher_contents_write_missing", name)
            if install_fragment not in text:
                _fail("publisher_environment_incomplete", name)
            if text.count(token_fragment) != 1:
                _fail("publisher_ephemeral_token_missing", name)
            _checkout_has_full_history(name, text, checkout_sha)
            if final_cas_marker in text and text.count(final_cas_marker) != 1:
                _fail("publisher_final_cas_workflow_invocation_invalid", name)

    if observed_actions_write != allowed_actions_write:
        _fail(
            "workflow_actions_write_set_mismatch",
            f"observed={sorted(observed_actions_write)}; registered={sorted(allowed_actions_write)}",
        )
    if not publishing_lanes:
        _fail("security_publishing_lanes_missing")

    push_text = _safe_path(root, push_path, "security_push_script_path_invalid").read_text(
        encoding="utf-8"
    )
    if gate_command not in push_text:
        _fail("publisher_committed_gate_missing")
    if "SECURITY REFUSAL" not in push_text:
        _fail("publisher_fail_closed_refusal_missing")
    if "unset IGRM_PUBLISH_TOKEN" not in push_text:
        _fail("publisher_token_not_cleared_before_gate")
    if re.search(r"^\s*if git push", push_text, re.M):
        _fail("publisher_plain_git_push_present")
    pushes = list(re.finditer(r"^\s*if git_push", push_text, re.M))
    guards = list(
        re.finditer(r"^\s*if ! gate_candidate; then exit 1; fi\s*$", push_text, re.M)
    )
    if len(pushes) != 2 or len(guards) != len(pushes):
        _fail("publisher_push_guard_count_invalid")
    for push in pushes:
        prior_guards = [guard for guard in guards if guard.end() < push.start()]
        if not prior_guards or push.start() - prior_guards[-1].end() > 80:
            _fail("publisher_push_not_immediately_gated")

    final_cas_text = _safe_path(
        root, final_cas_path, "security_final_cas_script_path_invalid"
    ).read_text(encoding="utf-8")
    direct_push = 'git push origin "$FROZEN_CANDIDATE_SHA:main"'
    if final_cas_text.count(direct_push) != 1 or "git push origin HEAD:main" in final_cas_text:
        _fail("publisher_final_cas_push_count_invalid")
    if "git pull --rebase" in final_cas_text or "checkout --theirs" in final_cas_text:
        _fail("publisher_frozen_cas_conflict_resolution_present")
    if "unset IGRM_PUBLISH_TOKEN PUBLISH_TOKEN GH_TOKEN GITHUB_TOKEN" not in final_cas_text:
        _fail("publisher_token_not_cleared_before_gate")
    bodies = {
        name: _shell_function(final_cas_text, name)
        for name in FINAL_CAS_FUNCTION_SHA256
    }
    for name, expected_sha in FINAL_CAS_FUNCTION_SHA256.items():
        if hashlib.sha256(bodies[name].encode("utf-8")).hexdigest() != expected_sha:
            _fail("publisher_final_cas_function_digest_invalid", name)

    base_markers = (
        "current_head=$(git rev-parse HEAD)",
        '[ "$current_head" != "$BASE_COMMIT" ]',
    )
    push_markers = (
        "candidate_head=$(git rev-parse HEAD)",
        '[ -z "$FROZEN_CANDIDATE_SHA" ]',
        'parent_count=$(git rev-list --parents -n 1 "$FROZEN_CANDIDATE_SHA"',
        '[ "$parent_count" != "1" ]',
        'candidate_parent=$(git rev-parse "$FROZEN_CANDIDATE_SHA^")',
        '[ "$candidate_parent" != "$BASE_COMMIT" ]',
        "git fetch --quiet origin main",
        "remote_commit=$(git rev-parse origin/main)",
        '[ "$remote_commit" != "$BASE_COMMIT" ]',
        '--check-release-candidate "$CANDIDATE_CLASS"',
        '--expected-candidate-sha "$FROZEN_CANDIDATE_SHA"',
        '--base-commit "$BASE_COMMIT"',
        '--expected-target "$TARGET"',
        "release_candidate=$(printf",
        "release_class=$(printf",
        '[ "$release_candidate" != "$FROZEN_CANDIDATE_SHA" ]',
        '[ "$release_class" != "$CANDIDATE_CLASS" ]',
        direct_push,
    )
    gated_markers = (
        'CANDIDATE_CLASS="$candidate_class"',
        'git commit -m "$message"',
        "FROZEN_CANDIDATE_SHA=$(git rev-parse HEAD)",
        'parent_count=$(git rev-list --parents -n 1 "$FROZEN_CANDIDATE_SHA"',
        '[ "$parent_count" != "1" ]',
        'candidate_parent=$(git rev-parse "$FROZEN_CANDIDATE_SHA^")',
        '[ "$candidate_parent" != "$BASE_COMMIT" ]',
        FINAL_CAS_GATE_COMMAND,
        "push_frozen_parent",
    )
    for body, markers, code in (
        (bodies["require_frozen_base"], base_markers, "publisher_final_cas_base_guard_order_invalid"),
        (bodies["push_frozen_parent"], push_markers, "publisher_final_cas_remote_guard_order_invalid"),
        (bodies["publish_gated_candidate"], gated_markers, "publisher_final_cas_gate_order_invalid"),
    ):
        offsets = [body.find(marker) for marker in markers]
        if any(offset < 0 for offset in offsets) or offsets != sorted(offsets):
            _fail(code)

    dispatch_marker = "\nrequire_frozen_base\n"
    if final_cas_text.count(dispatch_marker) != 1:
        _fail("publisher_final_cas_dispatch_invalid")
    dispatch = final_cas_text[
        _shell_function_end(final_cas_text, "publish_refusal") :
    ]
    if hashlib.sha256(dispatch.encode("utf-8")).hexdigest() != FINAL_CAS_DISPATCH_SHA256:
        _fail("publisher_final_cas_dispatch_digest_invalid")

    # Preserve granular refusals for ordinary drift and verify that the
    # unchanged predecessor still satisfies cbb. This does not independently
    # authorize the successor transition; the returned status says so.
    _validate_against_predecessor_projection(root, value)
    limitations = _string_list(
        value.get("limitations"), "security_limitations_missing"
    )
    return {
        "_meta": {
            "schema_version": "1.0.0",
            "date": "2026-08-08",
            "generated": "2026-08-08T00:00:00Z",
            "license": "CC BY 4.0",
            "citation": (
                "Krishna, Ishan (2026). India Geopolitical Risk Monitor. "
                "https://igrm.in/"
            ),
            "codebook": "https://igrm.in/codebook.html",
            "source": "https://igrm.in/data/security_integrity.json",
            "what": (
                "Static, machine-verified repository-control baseline for workflow "
                "actions, permissions, history, publisher environments and the exact "
                "post-rebase publication gate; not a penetration test or security certification."
            ),
        },
        "status": "repository_self_consistency_only",
        "default_policy": "deny",
        "scope": {
            "repository_controls_only": True,
            "workflow_directory": value["workflow_directory"],
            "publisher_push_script": push_path,
            "final_cas_push_script": final_cas_path,
            "canonical_gate_script": gate_path,
            "successor_transition_external_authority": False,
        },
        "controls": {
            "immutable_workflow_actions": {
                "status": "pass",
                "reviewed_action_identities": len(allowed_actions),
                "action_references": action_references,
            },
            "full_history_for_frozen_evidence": {
                "status": "pass",
                "fetch_depth": 0,
                "workflow_count": sum(
                    "actions/checkout@" in path.read_text(encoding="utf-8")
                    for path in workflow_paths
                ),
            },
            "least_privilege_workflow_permissions": {
                "status": "pass",
                "workflow_count": len(workflow_paths),
                "actions_write_workflows": sorted(observed_actions_write),
            },
            "publisher_environment_parity": {
                "status": "pass",
                "publishing_lane_count": len(publishing_lanes),
                "requirement_sets": ["requirements.txt", "requirements-dev.txt"],
            },
            "publisher_credential_isolation": {
                "status": "pass",
                "checkout_persist_credentials": False,
                "token_scope": "final_publication_step_only",
                "token_cleared_before_candidate_gate": True,
            },
            "exact_post_rebase_publication_gate": {
                "status": "self_consistent_unattested_transition",
                "policy": "refuse_publish_on_red_candidate",
                "command": gate_command,
                "final_cas_command": FINAL_CAS_GATE_COMMAND,
                "push_paths_verified": len(pushes) + 1,
                "transition_authority": "unavailable_no_external_signature",
            },
        },
        "publishing_lanes": sorted(publishing_lanes),
        "limitations": limitations,
    }


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def render_report(report: dict[str, Any]) -> bytes:
    return (json.dumps(report, indent=1, sort_keys=True) + "\n").encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--write", action="store_true")
    args = parser.parse_args()
    content = render_report(validate_repository())
    if args.write:
        _write_atomic(PUBLIC_REPORT_PATH, content)
        print(f"[security-integrity] wrote {PUBLIC_REPORT_PATH}")
        return
    try:
        current = PUBLIC_REPORT_PATH.read_bytes()
    except OSError as exc:
        raise SystemExit("[security-integrity] public report missing") from exc
    if current != content:
        raise SystemExit("[security-integrity] public report differs from verified controls")
    print("[security-integrity] repository controls and public report match")


if __name__ == "__main__":
    main()
