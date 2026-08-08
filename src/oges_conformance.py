"""Offline reference conformance runner for OGES public draft 0.1.0.

Conformance is deliberately narrower than truth.  The runner verifies the exact
registered profile, schema and semantic-validator bytes, then delegates complete
release validation to :mod:`src.canonical_objects`.  Reports contain identifiers,
hashes, counts and refusal codes only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, Union, cast

from src import canonical_objects as canonical
from src.oges_fixture import OgesFixtureError, apply_operation, build_fixture

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "standard" / "oges" / "0.1.0" / "profile.json"
PROFILE_SHA256 = "73d4347bf7b3a42f509b37e3ad7518423a57c2e645c91bd35b8b6859acf009c2"

JsonValue = Union[dict[str, Any], list[Any], str, int, float, bool, None]

EXPECTED_CASES = {
    "valid_signed_release": ("none", "conformant", None),
    "tampered_release_signature": (
        "tamper_release_signature",
        "refused",
        "release_signature_invalid",
    ),
    "spoofed_official_confirmation": (
        "spoof_official_confirmation",
        "refused",
        "event_official_confirmation_ineligible",
    ),
    "omitted_universe_member": (
        "omit_universe_member",
        "refused",
        "universe_frame_membership_mismatch",
    ),
    "invented_exposure_method": (
        "invent_exposure_method",
        "refused",
        "method_unregistered",
    ),
    "qualitative_edge_with_number": (
        "qualitative_edge_with_number",
        "refused",
        "object_schema_invalid",
    ),
    "future_measurement_period": (
        "future_measurement_period",
        "refused",
        "edge_magnitude_after_observation",
    ),
    "tampered_rights_registry": (
        "tamper_rights_registry",
        "refused",
        "release_rights_registry_digest_mismatch",
    ),
    "duplicate_json_key": ("duplicate_json_key", "refused", "json_duplicate_key"),
    "false_release_count": (
        "false_release_count",
        "refused",
        "release_counts_mismatch",
    ),
    "restricted_evidence_bytes_exposed": (
        "expose_restricted_evidence",
        "refused",
        "restricted_evidence_bytes_forbidden",
    ),
}


class OgesConformanceError(ValueError):
    """Stable profile, bundle or suite refusal."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise OgesConformanceError(code, detail)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("conformance_json_duplicate_key", key)
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    _fail("conformance_json_non_finite", value)


def _read_json(path: Path, code: str) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OgesConformanceError(code) from exc
    if not isinstance(value, dict):
        _fail(code)
    return raw, cast(dict[str, Any], value)


def _sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise OgesConformanceError("conformance_file_unreadable", str(path)) from exc


def _relative(value: object, code: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        _fail(code)
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) != value:
        _fail(code)
    return value


def _repo_file(relative: object, code: str) -> Path:
    value = _relative(relative, code)
    candidate = ROOT.resolve()
    for part in PurePosixPath(value).parts:
        candidate = candidate / part
        if candidate.is_symlink():
            _fail(code)
    if not candidate.is_file():
        _fail(code)
    return candidate


def _load_profile() -> tuple[dict[str, Any], dict[str, Any], str]:
    raw, profile = _read_json(PROFILE_PATH, "profile_unreadable")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != PROFILE_SHA256:
        _fail("profile_digest_mismatch")
    if (
        profile.get("schema_version") != "1.0.0"
        or profile.get("standard_id") != "oges"
        or profile.get("standard_version") != "0.1.0"
        or profile.get("status") != "public_draft_reference_implementation"
        or profile.get("effective") != "2026-08-08"
    ):
        _fail("profile_identity_invalid")
    implementation = profile.get("implementation")
    if not isinstance(implementation, dict):
        _fail("profile_implementation_invalid")
    for path_field, hash_field in (
        ("validator_path", "validator_sha256"),
        ("schema_registry_path", "schema_registry_sha256"),
        ("spec_path", "spec_sha256"),
        ("adversarial_cases_path", "adversarial_cases_sha256"),
    ):
        path = _repo_file(implementation.get(path_field), "profile_path_invalid")
        if _sha(path) != implementation.get(hash_field):
            _fail("profile_artifact_digest_mismatch", path_field)
    if implementation.get("network_access") != "forbidden":
        _fail("profile_network_boundary_invalid")
    required_types = profile.get("required_object_types")
    if required_types != [
        "evidence_item",
        "entity",
        "event",
        "universe_release",
        "exposure_edge",
    ]:
        _fail("profile_object_types_invalid")

    cases_path = _repo_file(
        implementation.get("adversarial_cases_path"), "profile_cases_path_invalid"
    )
    _, cases_document = _read_json(cases_path, "profile_cases_unreadable")
    if (
        cases_document.get("standard_id") != "oges"
        or cases_document.get("standard_version") != "0.1.0"
        or cases_document.get("fixture_class") != "synthetic_nonproduction"
    ):
        _fail("profile_cases_identity_invalid")
    rows = cases_document.get("cases")
    if not isinstance(rows, list) or len(rows) != len(EXPECTED_CASES):
        _fail("profile_case_count_invalid")
    observed: dict[str, tuple[object, object, object]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            _fail("profile_case_invalid")
        case_id = row["id"]
        if case_id in observed:
            _fail("profile_case_duplicate", case_id)
        observed[case_id] = (
            row.get("operation"),
            row.get("expected_status"),
            row.get("expected_reason"),
        )
    if observed != EXPECTED_CASES:
        _fail("profile_case_registration_mismatch")
    conformance = profile.get("conformance")
    if not isinstance(conformance, dict) or conformance.get(
        "required_case_count"
    ) != len(EXPECTED_CASES):
        _fail("profile_conformance_rule_invalid")

    schema_registry = _repo_file(
        implementation["schema_registry_path"], "profile_schema_registry_missing"
    )
    try:
        _, _, registry_digest = canonical._load_schema_registry(ROOT, schema_registry)
    except canonical.CanonicalObjectError as exc:
        _fail("profile_schema_registry_invalid", exc.code)
    if registry_digest != implementation["schema_registry_sha256"]:
        _fail("profile_schema_registry_digest_mismatch")
    return profile, cases_document, digest


def profile_summary() -> dict[str, object]:
    profile, cases, digest = _load_profile()
    implementation = cast(Mapping[str, object], profile["implementation"])
    return {
        "status": "registered_public_draft",
        "standard_id": profile["standard_id"],
        "standard_version": profile["standard_version"],
        "profile_sha256": digest,
        "validator_sha256": implementation["validator_sha256"],
        "schema_registry_sha256": implementation["schema_registry_sha256"],
        "required_object_types": profile["required_object_types"],
        "adversarial_case_count": len(cases["cases"]),
        "production_adoption_claim": False,
    }


def _bundle_root(path: Path) -> Path:
    if path.is_symlink() or not path.is_dir():
        _fail("bundle_root_invalid")
    return path.resolve()


def validate_bundle(
    bundle: Path, *, manifest_relative: str = "canonical/release.json"
) -> dict[str, object]:
    """Validate one complete bundle against the exact OGES 0.1 profile."""

    profile, _, profile_digest = _load_profile()
    implementation = cast(Mapping[str, object], profile["implementation"])
    root = _bundle_root(bundle)
    manifest_path = root / _relative(manifest_relative, "bundle_manifest_path_invalid")
    bundle_registry = root / "governance" / "canonical_schema_registry.json"
    if bundle_registry.is_symlink() or not bundle_registry.is_file():
        _fail("bundle_schema_registry_missing")
    if _sha(bundle_registry) != implementation["schema_registry_sha256"]:
        _fail("bundle_schema_registry_profile_mismatch")
    try:
        summary = canonical.validate_release(
            manifest_path,
            root=root,
            schema_registry_path=bundle_registry,
            rights_registry_path=root / "governance" / "source_rights_registry.json",
            rights_signers_path=root / "governance" / "rights_signers.json",
            method_registry_path=root / "governance" / "canonical_method_registry.json",
            release_signers_path=root / "governance" / "release_signers.json",
        )
    except canonical.CanonicalObjectError:
        raise
    counts = summary.get("counts")
    if not isinstance(counts, dict):
        _fail("bundle_counts_invalid")
    for object_type in cast(list[str], profile["required_object_types"]):
        value = counts.get(object_type)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            _fail("required_object_type_missing", object_type)
    return {
        "status": "conformant",
        "standard_id": "oges",
        "standard_version": "0.1.0",
        "profile_sha256": profile_digest,
        "validator_sha256": implementation["validator_sha256"],
        "schema_registry_sha256": implementation["schema_registry_sha256"],
        "release_id": summary["release_id"],
        "release_record_sha256": summary["record_sha256"],
        "object_count": summary["object_count"],
        "object_counts": counts,
    }


def _prepare_materialization(path: Path) -> Path:
    if path.is_symlink():
        _fail("materialize_path_invalid")
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            _fail("materialize_path_not_empty")
    else:
        path.mkdir(parents=True)
    return path.resolve()


def _run_cases(directory: Path) -> dict[str, object]:
    _, cases_document, profile_digest = _load_profile()
    results: list[dict[str, object]] = []
    passed = 0
    for row in cases_document["cases"]:
        case_id = cast(str, row["id"])
        case_root = directory / case_id
        fixture = build_fixture(case_root)
        apply_operation(fixture, cast(str, row["operation"]))
        observed_status: str
        observed_reason: str | None
        try:
            validate_bundle(case_root)
            observed_status = "conformant"
            observed_reason = None
        except canonical.CanonicalObjectError as exc:
            observed_status = "refused"
            observed_reason = exc.code
        except OgesConformanceError as exc:
            observed_status = "refused"
            observed_reason = exc.code
        case_passed = (
            observed_status == row["expected_status"]
            and observed_reason == row["expected_reason"]
        )
        if case_passed:
            passed += 1
        results.append(
            {
                "id": case_id,
                "expected_status": row["expected_status"],
                "expected_reason": row["expected_reason"],
                "observed_status": observed_status,
                "observed_reason": observed_reason,
                "passed": case_passed,
            }
        )
    total = len(results)
    return {
        "status": "pass" if passed == total else "fail",
        "standard_id": "oges",
        "standard_version": "0.1.0",
        "profile_sha256": profile_digest,
        "cases_passed": passed,
        "cases_total": total,
        "cases": results,
    }


def self_test(materialize: Path | None = None) -> dict[str, object]:
    """Run every registered case, optionally retaining generated bundles."""

    if materialize is not None:
        return _run_cases(_prepare_materialization(materialize))
    with tempfile.TemporaryDirectory(prefix="oges-0.1-conformance-") as temporary:
        return _run_cases(Path(temporary))


def _emit(value: Mapping[str, object], *, stream: Any = sys.stdout) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")), file=stream)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Validate OGES 0.1 profiles, bundles and adversarial vectors offline"
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("profile", help="print the registered public-draft profile")
    validate = subcommands.add_parser("validate", help="validate one complete bundle")
    validate.add_argument("--bundle", required=True, type=Path)
    validate.add_argument("--manifest", default="canonical/release.json")
    suite = subcommands.add_parser("self-test", help="run every registered test vector")
    suite.add_argument("--materialize", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "profile":
            result = profile_summary()
        elif args.command == "validate":
            result = validate_bundle(args.bundle, manifest_relative=args.manifest)
        else:
            result = self_test(args.materialize)
    except canonical.CanonicalObjectError as exc:
        _emit(
            {
                "status": "refused",
                "standard_id": "oges",
                "standard_version": "0.1.0",
                "reason": exc.code,
                "detail": exc.detail,
            },
            stream=sys.stderr,
        )
        raise SystemExit(2) from None
    except (OgesConformanceError, OgesFixtureError) as exc:
        _emit(
            {
                "status": "refused",
                "standard_id": "oges",
                "standard_version": "0.1.0",
                "reason": getattr(exc, "code", str(exc)),
                "detail": getattr(exc, "detail", ""),
            },
            stream=sys.stderr,
        )
        raise SystemExit(2) from None
    _emit(result)
    if result.get("status") == "fail":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
