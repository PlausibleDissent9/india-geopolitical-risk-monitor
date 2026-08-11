"""Exact candidate-byte and publication-boundary tests for API manifest 0.1."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
from collections.abc import Callable, Generator
from datetime import date
from pathlib import Path

import jsonschema
import pytest
from src import final_publication
from src import public_api_byte_manifest as manifest

ROOT = Path(__file__).resolve().parents[1]


def _git(root: Path, *args: str, env: dict[str, str] | None = None) -> str:
    effective_env = env
    if effective_env is None and root.resolve() != ROOT.resolve():
        effective_env = {key: value for key, value in os.environ.items() if key != "GIT_INDEX_FILE"}
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        env=effective_env,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


@pytest.fixture(scope="module")
def candidate_tree() -> str:
    # Under the committed gate this is HEAD's tree. During pre-commit review,
    # a caller may provide a temporary candidate index; write-tree captures
    # that same staged candidate without moving any ref or the shared index.
    return _git(ROOT, "write-tree")


@pytest.fixture()
def candidate_repo(tmp_path: Path, candidate_tree: str) -> Generator[Path, None, None]:
    archive = tmp_path / "candidate.tar"
    subprocess.run(
        ["git", "archive", candidate_tree, "-o", str(archive)],
        cwd=ROOT,
        check=True,
    )
    root = tmp_path / "repo"
    root.mkdir()
    with tarfile.open(archive) as handle:
        try:
            handle.extractall(root, filter="data")
        except TypeError:  # pragma: no cover - Python <3.12 compatibility
            handle.extractall(root)
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Manifest test")
    _git(root, "config", "user.email", "actions@github.com")
    _git(root, "add", "--all")
    _git(root, "commit", "-q", "-m", "candidate")
    outer_index = os.environ.pop("GIT_INDEX_FILE", None)
    try:
        yield root
    finally:
        if outer_index is not None:
            os.environ["GIT_INDEX_FILE"] = outer_index


def _refusal(code: str, call: Callable[[], object]) -> None:
    with pytest.raises(manifest.PublicAPIByteManifestError) as exc:
        call()
    assert exc.value.code == code


def test_candidate_manifest_is_exact_complete_and_schema_valid(candidate_tree: str) -> None:
    payload = manifest.verify_tree(candidate_tree)
    assert payload["api_contract"]["endpoint_denominator"] == 117
    assert payload["universe"] == {
        "basis": "api_contract.endpoints",
        "endpoint_denominator": 117,
        "endpoint_set_sha256": payload["universe"]["endpoint_set_sha256"],
        "excluded_endpoint_denominator": 1,
        "hashed_endpoint_denominator": 116,
        "order": "public_path_utf8_byte_ascending",
    }
    assert payload["totals"]["hashed_entries"] == 116
    assert payload["excluded_entries"] == [
        {
            "path": manifest.MANIFEST_API_PATH,
            "repository_path": manifest.MANIFEST_REPOSITORY_PATH,
            "reason": "self_exclusion_avoids_recursive_digest",
        }
    ]
    assert [row["path"] for row in payload["entries"]] == sorted(
        (row["path"] for row in payload["entries"]), key=lambda value: value.encode()
    )
    schema = json.loads((ROOT / manifest.SCHEMA_PATH).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(payload)


def test_index_capture_ignores_dirty_worktree_overlay(candidate_repo: Path) -> None:
    before = manifest.expected_manifest_bytes(manifest.capture_index(candidate_repo))
    endpoint = candidate_repo / "docs/data/latest.json"
    endpoint.write_bytes(endpoint.read_bytes() + b"\n")
    after = manifest.expected_manifest_bytes(manifest.capture_index(candidate_repo))
    assert before == after


def test_staged_endpoint_change_requires_a_refreshed_manifest(candidate_repo: Path) -> None:
    endpoint = candidate_repo / "docs/data/latest.json"
    payload = json.loads(endpoint.read_text(encoding="utf-8"))
    payload["_manifest_test_additive"] = True
    endpoint.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    _git(candidate_repo, "add", "--", "docs/data/latest.json")
    _refusal(
        "manifest_snapshot_mismatch",
        lambda: manifest.verify_index(candidate_repo),
    )
    manifest.write_from_index(candidate_repo)
    _git(candidate_repo, "add", "--", manifest.MANIFEST_REPOSITORY_PATH)
    verified = manifest.verify_index(candidate_repo)
    latest = next(row for row in verified["entries"] if row["path"] == "data/latest.json")
    assert latest["bytes"] == len(endpoint.read_bytes())


def test_casefold_endpoint_alias_is_refused(candidate_repo: Path) -> None:
    contract_path = candidate_repo / manifest.API_CONTRACT_PATH
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    row = dict(next(item for item in contract["endpoints"] if item["path"] == "data/latest.json"))
    row["path"] = "data/LATEST.json"
    contract["endpoints"].append(row)
    contract_path.write_text(json.dumps(contract, indent=1) + "\n", encoding="utf-8")
    _git(candidate_repo, "add", "--", manifest.API_CONTRACT_PATH)
    _refusal(
        "candidate_path_collision",
        lambda: manifest.build_manifest(manifest.capture_index(candidate_repo)),
    )


@pytest.mark.parametrize(
    "unsafe_path",
    (
        "../data/latest.json",
        "data\\latest.json",
        "data/latest.json:alternate-stream",
        "data/e\u0301.json",
    ),
)
def test_ambiguous_endpoint_paths_are_refused(
    candidate_repo: Path, unsafe_path: str
) -> None:
    contract_path = candidate_repo / manifest.API_CONTRACT_PATH
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["endpoints"][0]["path"] = unsafe_path
    contract_path.write_text(json.dumps(contract, indent=1) + "\n", encoding="utf-8")
    _git(candidate_repo, "add", "--", manifest.API_CONTRACT_PATH)
    _refusal(
        "candidate_path_invalid",
        lambda: manifest.build_manifest(manifest.capture_index(candidate_repo)),
    )


def test_duplicate_api_contract_key_uses_contract_refusal(candidate_repo: Path) -> None:
    contract_path = candidate_repo / manifest.API_CONTRACT_PATH
    raw = contract_path.read_text(encoding="utf-8")
    assert raw.startswith("{\n \"_meta\":")
    contract_path.write_text(
        raw.replace("{\n \"_meta\":", "{\n \"_meta\": {},\n \"_meta\":", 1),
        encoding="utf-8",
    )
    _git(candidate_repo, "add", "--", manifest.API_CONTRACT_PATH)
    _refusal(
        "api_contract_invalid",
        lambda: manifest.build_manifest(manifest.capture_index(candidate_repo)),
    )


def test_endpoint_symlink_mode_is_refused(candidate_repo: Path) -> None:
    endpoint = candidate_repo / "docs/data/latest.json"
    endpoint.unlink()
    endpoint.symlink_to("history.json")
    _git(candidate_repo, "add", "--", "docs/data/latest.json")
    _refusal(
        "candidate_mode_invalid",
        lambda: manifest.build_manifest(manifest.capture_index(candidate_repo)),
    )


def test_oversized_endpoint_is_refused(candidate_repo: Path) -> None:
    endpoint = candidate_repo / "docs/data/latest.json"
    endpoint.write_bytes(b"x" * (manifest.MAX_ENTRY_BYTES + 1))
    _git(candidate_repo, "add", "--", "docs/data/latest.json")
    _refusal(
        "candidate_size_limit_exceeded",
        lambda: manifest.build_manifest(manifest.capture_index(candidate_repo)),
    )


def test_profile_dependency_reseal_is_not_silently_accepted(candidate_repo: Path) -> None:
    runtime = candidate_repo / manifest.RUNTIME_PATH
    runtime.write_bytes(runtime.read_bytes() + b"\n# drift\n")
    _git(candidate_repo, "add", "--", manifest.RUNTIME_PATH)
    _refusal(
        "candidate_dependency_drift",
        lambda: manifest.build_manifest(manifest.capture_index(candidate_repo)),
    )


def test_manifest_has_no_clock_commit_or_authentication_claim(candidate_tree: str) -> None:
    payload = manifest.verify_tree(candidate_tree)
    text = json.dumps(payload).lower()
    assert "generated_at" not in text
    assert "candidate_sha" not in text
    assert payload["integrity"] == {
        "algorithm": "SHA-256",
        "entries_sha256": payload["integrity"]["entries_sha256"],
        "external_manifest_digest_required": True,
        "signed": False,
        "authenticated_deployment": False,
        "atomic_hosted_snapshot": False,
    }
    assert "does not authenticate" in payload["claim_boundary"].lower()


def test_real_index_and_tree_modes_are_distinct(candidate_repo: Path) -> None:
    baseline_tree = _git(candidate_repo, "rev-parse", "HEAD^{tree}")
    endpoint = candidate_repo / "docs/data/latest.json"
    endpoint.write_bytes(endpoint.read_bytes() + b"\n")
    _git(candidate_repo, "add", "--", "docs/data/latest.json")
    indexed = manifest.expected_manifest_bytes(manifest.capture_index(candidate_repo))
    committed = manifest.expected_manifest_bytes(
        manifest.capture_tree(baseline_tree, candidate_repo)
    )
    assert indexed != committed


def test_candidate_index_environment_does_not_modify_shared_index(
    tmp_path: Path, candidate_tree: str
) -> None:
    before = _git(ROOT, "write-tree")
    temporary = tmp_path / "index"
    env = {**os.environ, "GIT_INDEX_FILE": str(temporary)}
    _git(ROOT, "read-tree", candidate_tree, env=env)
    assert _git(ROOT, "write-tree") == before


def _publisher_env() -> dict[str, str]:
    clean = {key: value for key, value in os.environ.items() if key != "GIT_INDEX_FILE"}
    return {
        **clean,
        "PATH": f"{Path(sys.executable).parent}:{os.environ.get('PATH', '')}",
    }


def test_generic_publisher_noop_never_amends_upstream(candidate_repo: Path, tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    _git(candidate_repo, "remote", "add", "origin", str(remote))
    _git(candidate_repo, "branch", "-M", "main")
    _git(candidate_repo, "push", "-q", "-u", "origin", "main")
    before = _git(candidate_repo, "rev-parse", "HEAD")
    manifest_before = (candidate_repo / manifest.MANIFEST_REPOSITORY_PATH).read_bytes()
    result = subprocess.run(
        ["bash", "scripts/publish_push.sh", "--refresh-public-api-byte-manifest"],
        cwd=candidate_repo,
        env=_publisher_env(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "upstream no-op" in result.stdout
    assert _git(candidate_repo, "rev-parse", "HEAD") == before
    assert (candidate_repo / manifest.MANIFEST_REPOSITORY_PATH).read_bytes() == manifest_before


def test_post_rebase_refresh_amends_exact_lane_candidate(candidate_repo: Path, tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    _git(candidate_repo, "remote", "add", "origin", str(remote))
    _git(candidate_repo, "branch", "-M", "main")
    _git(candidate_repo, "push", "-q", "-u", "origin", "main")
    upstream = tmp_path / "upstream"
    _git(tmp_path, "clone", "-q", str(remote), str(upstream))
    _git(upstream, "config", "user.name", "Upstream test")
    _git(upstream, "config", "user.email", "actions@github.com")
    readme = upstream / "README.md"
    readme.write_bytes(readme.read_bytes() + b"\n")
    _git(upstream, "add", "--", "README.md")
    _git(upstream, "commit", "-q", "-m", "move remote")
    _git(upstream, "push", "-q", "origin", "main")

    endpoint = candidate_repo / "docs/data/latest.json"
    payload = json.loads(endpoint.read_text(encoding="utf-8"))
    payload["_manifest_rebase_test"] = True
    endpoint.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    _git(candidate_repo, "add", "--", "docs/data/latest.json")
    _git(candidate_repo, "commit", "-q", "-m", "lane candidate")
    _git(candidate_repo, "pull", "-q", "--rebase", "origin", "main")
    stale = _git(candidate_repo, "rev-parse", "HEAD")
    result = subprocess.run(
        ["bash", "scripts/publish_push.sh", "--refresh-public-api-byte-manifest"],
        cwd=candidate_repo,
        env=_publisher_env(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    refreshed = _git(candidate_repo, "rev-parse", "HEAD")
    assert refreshed != stale
    assert _git(candidate_repo, "rev-parse", "HEAD^") == _git(
        candidate_repo, "rev-parse", "origin/main"
    )
    assert not _git(candidate_repo, "status", "--short")
    manifest.verify_tree("HEAD", candidate_repo)


def test_publication_scripts_cover_generic_and_both_final_classes() -> None:
    generic = (ROOT / "scripts/publish_push.sh").read_text(encoding="utf-8")
    final = (ROOT / "scripts/publish_final_cas.sh").read_text(encoding="utf-8")
    assert generic.count("if ! refresh_public_api_byte_manifest; then exit 1; fi") == 2
    assert generic.count("if ! gate_candidate; then exit 1; fi") == 2
    for refresh in [
        index for index in range(len(generic)) if generic.startswith(
            "if ! refresh_public_api_byte_manifest", index
        )
    ]:
        gate = generic.index("if ! gate_candidate", refresh)
        push = generic.index("if git_push", gate)
        assert refresh < gate < push
    assert final.count("stage_public_api_byte_manifest") == 3  # definition + 2 calls
    refusal_add = final.index("git add data/raw/final_publication_status.json")
    refusal_manifest = final.index("stage_public_api_byte_manifest", refusal_add)
    refusal_publish = final.index("publish_gated_candidate", refusal_manifest)
    assert refusal_add < refusal_manifest < refusal_publish


def _committed_refusal_with_manifest(root: Path) -> tuple[str, str, date]:
    base = _git(root, "rev-parse", "HEAD")
    target = date(2026, 8, 10)
    final_publication.record_pipeline_failed(
        target,
        root=root,
        base_commit=base,
        failure_stage="source",
        contract_today=date(2026, 8, 11),
    )
    state = final_publication.write_public_status(root=root, today=date(2026, 8, 11))
    parent_status = json.loads(
        subprocess.run(
            ["git", "show", f"{base}:docs/data/status.json"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
    )
    parent_status["final_publication"] = state
    assert (root / "docs/data/status.json").read_bytes() == (
        json.dumps(parent_status, indent=1) + "\n"
    ).encode("utf-8")
    _git(root, "add", "--", *sorted(final_publication._VALUE_FREE_REFUSAL_PATHS))
    manifest.write_from_index(root)
    _git(root, "add", "--", manifest.MANIFEST_REPOSITORY_PATH)
    _git(root, "commit", "-q", "-m", "value-free refusal with derived manifest")
    return base, _git(root, "rev-parse", "HEAD"), target


def test_refusal_candidate_is_exact_four_outputs_plus_manifest(candidate_repo: Path) -> None:
    base, candidate, target = _committed_refusal_with_manifest(candidate_repo)
    proof = final_publication.require_release_candidate(
        "refusal",
        expected_candidate_sha=candidate,
        base_commit=base,
        expected_target=target,
        root=candidate_repo,
    )
    assert set(proof["changed_paths"]) == {
        *final_publication._VALUE_FREE_REFUSAL_PATHS,
        manifest.MANIFEST_REPOSITORY_PATH,
    }
    assert proof["value_fields_published"] is False


def test_refusal_candidate_cannot_reseal_a_false_manifest(candidate_repo: Path) -> None:
    base, _candidate, target = _committed_refusal_with_manifest(candidate_repo)
    path = candidate_repo / manifest.MANIFEST_REPOSITORY_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["entries"][0]["sha256"] = "0" * 64
    path.write_text(manifest.canonical_json(payload).decode("utf-8"), encoding="utf-8")
    _git(candidate_repo, "add", "--", manifest.MANIFEST_REPOSITORY_PATH)
    _git(candidate_repo, "commit", "-q", "--amend", "--no-edit")
    candidate = _git(candidate_repo, "rev-parse", "HEAD")
    with pytest.raises(final_publication.FinalPublicationError) as exc:
        final_publication.require_release_candidate(
            "refusal",
            expected_candidate_sha=candidate,
            base_commit=base,
            expected_target=target,
            root=candidate_repo,
        )
    assert exc.value.classification == "release_candidate_unproven"
    assert exc.value.detail.startswith("api_manifest_invalid:")
