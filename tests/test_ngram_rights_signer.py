"""The production rights signer remains human-only and review-only."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ngram_rights_sign.py"


def test_signer_has_no_yes_mode_and_binds_official_terms() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    contract = (ROOT / "src/ngram_rights_contract.py").read_text(encoding="utf-8")
    assert 'add_argument("--yes"' not in source
    assert "from src import ngram_rights_contract" in source
    assert "https://www.gdeltproject.org/about.html" in contract
    assert 'USES = ["model_processing", "publish_derived_value"]' in source
    assert "PRODUCTION_TRUSTED_SIGNERS" in source
    assert "git commit" not in source
    assert "git push" not in source


def test_repository_signed_state_is_exactly_the_founder_reviewed_decision() -> None:
    """The 2026-08-12 transition: registry, signer, artifact and pin must agree.

    Before the founder-run aggregate-2.0 review this test asserted the unsigned
    state. It now pins the signed state with the same hostility: any drift in
    the approved row, the enrolled signer, the artifact digest, or the
    production trust pin fails here before it can reach the acquisition gate.
    """
    import base64

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from src import ngram_rights

    registry = json.loads(
        (ROOT / "governance/source_rights_registry.json").read_text(encoding="utf-8")
    )
    source = next(
        row for row in registry["sources"] if row["source_id"] == ngram_rights.SOURCE_ID
    )
    assert source["decision_state"] == "approved"
    assert source["signer_id"] == "human:igrm-ngram-rights-reviewer"
    assert source["permitted_uses"] == ["model_processing", "publish_derived_value"]
    assert source["terms_url"] == "https://www.gdeltproject.org/about.html"
    assert source["reviewed_on"] == "2026-08-12"
    assert source["review_due"] == "2026-11-10"
    assert source["max_current_age_days"] == 3

    signers = json.loads(
        (ROOT / "governance/rights_signers.json").read_text(encoding="utf-8")
    )
    signer = next(
        row for row in signers["signers"]
        if row["signer_id"] == source["signer_id"]
    )
    assert signer["role"] == "rights_reviewer"
    assert signer["revoked_on"] is None

    # The production code pin is exactly the enrolled signer -- no more entries.
    assert ngram_rights.PRODUCTION_TRUSTED_SIGNERS == {
        signer["signer_id"]: (
            signer["public_key_ed25519_base64"],
            signer["role"],
        )
    }

    # The committed artifact bytes still verify under the pinned public key.
    artifact = (ROOT / source["decision_artifact_path"]).read_bytes()
    signature = (ROOT / source["decision_signature_path"]).read_bytes()
    assert len(signature) == 64
    assert hashlib.sha256(artifact).hexdigest() == source["decision_artifact_sha256"]
    Ed25519PublicKey.from_public_bytes(
        base64.b64decode(signer["public_key_ed25519_base64"], validate=True)
    ).verify(signature, artifact)


def test_signer_refuses_noninteractive_execution_before_key_or_bundle_write(
    tmp_path: Path,
) -> None:
    key = tmp_path / "key.pem"
    bundle = tmp_path / "bundle"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--private-key",
            str(key),
            "--output",
            str(bundle),
            "--reviewed-on",
            "2026-08-12",
            "--review-due",
            "2027-08-12",
        ],
        cwd=ROOT,
        input="",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "interactive_human_terminal_required" in result.stdout
    assert not key.exists()
    assert not bundle.exists()


class _TTY:
    def isatty(self) -> bool:
        return True


def _generated_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    reviewed_on: str = "2026-08-12",
    review_due: str = "2027-08-12",
) -> tuple[Path, Ed25519PrivateKey]:
    from scripts import ngram_rights_sign

    # The live repository now carries the applied 2026-08-12 review, and the
    # tool's rotation guard rightly refuses to re-sign an enrolled signer_id.
    # These attacks target the tool itself, so they run against a snapshot
    # root frozen in the pre-transition state: current registry rows, but no
    # enrolled signer. Only these two files are read by build_bundle.
    pristine = tmp_path / "pre-transition-root"
    (pristine / "governance").mkdir(parents=True)
    shutil.copy2(
        ROOT / "governance/source_rights_registry.json",
        pristine / "governance/source_rights_registry.json",
    )
    (pristine / "governance/rights_signers.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "effective": "2026-08-08",
                "default_policy": "deny",
                "signers": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(ngram_rights_sign, "ROOT", pristine)

    private_key = Ed25519PrivateKey.generate()
    proposed = ngram_rights_sign._source_row(
        next(
            row
            for row in json.loads(
                (ROOT / "governance/source_rights_registry.json").read_text(
                    encoding="utf-8"
                )
            )["sources"]
            if row["source_id"] == ngram_rights_sign.SOURCE_ID
        ),
        reviewed_on=reviewed_on,
        review_due=review_due,
    )
    decision = ngram_rights_sign._decision(proposed)
    digest = ngram_rights_sign.hashlib.sha256(
        ngram_rights_sign._canonical(decision)
    ).hexdigest()
    monkeypatch.setattr(ngram_rights_sign.sys, "stdin", _TTY())
    monkeypatch.setattr(ngram_rights_sign.sys, "stderr", _TTY())
    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt: f"SIGN {ngram_rights_sign.SOURCE_ID} AGGREGATE-2.0 {digest[:16]}",
    )
    monkeypatch.setattr(
        ngram_rights_sign.founder_authorize,
        "_load_or_create_private_key",
        lambda _path: private_key,
    )
    bundle = tmp_path / "review-bundle"
    ngram_rights_sign.build_bundle(
        private_key_path=tmp_path / "human-key.pem",
        output=bundle,
        reviewed_on=reviewed_on,
        review_due=review_due,
    )
    return bundle, private_key


def _applied_root(tmp_path: Path, bundle: Path) -> Path:
    root = tmp_path / "canonical-root"
    decisions = root / "governance/rights_decisions"
    decisions.mkdir(parents=True)
    shutil.copy2(
        bundle / "proposed-source-rights-registry.json",
        root / "governance/source_rights_registry.json",
    )
    shutil.copy2(
        bundle / "proposed-rights-signers.json",
        root / "governance/rights_signers.json",
    )
    shutil.copy2(
        bundle / "decision.json",
        decisions / "gdelt_web_ngrams_v5-aggregate-2.0.json",
    )
    shutil.copy2(
        bundle / "decision.sig",
        decisions / "gdelt_web_ngrams_v5-aggregate-2.0.sig",
    )
    return root


def _pin_generated_signer(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src import ngram_rights

    signer = json.loads(
        (root / "governance/rights_signers.json").read_text(encoding="utf-8")
    )["signers"][0]
    monkeypatch.setattr(
        ngram_rights,
        "PRODUCTION_TRUSTED_SIGNERS",
        {
            signer["signer_id"]: (
                signer["public_key_ed25519_base64"],
                signer["role"],
            )
        },
    )
    monkeypatch.setattr(
        ngram_rights,
        "_utc_now",
        lambda: datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc),
    )


def test_generated_bundle_applies_to_production_aggregate_guard_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src import final_publication

    bundle, _key = _generated_bundle(tmp_path, monkeypatch)
    root = _applied_root(tmp_path, bundle)
    _pin_generated_signer(root, monkeypatch)

    proof = final_publication.require_ngram_daily_aggregate_rights(
        target=date(2026, 8, 11), root=root
    )
    assert proof["permitted_uses"] == ["model_processing", "publish_derived_value"]
    with pytest.raises(final_publication.FinalPublicationError) as exc:
        final_publication.require_ngram_public_identity_rights(
            target=date(2026, 8, 11), root=root
        )
    assert exc.value.detail == "ngram_public_identity_use_not_permitted"


def test_signed_historical_recovery_targets_are_exact_and_aggregate_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src import final_publication, ngram_rights

    bundle, _key = _generated_bundle(tmp_path, monkeypatch)
    root = _applied_root(tmp_path, bundle)
    _pin_generated_signer(root, monkeypatch)
    monkeypatch.setattr(
        ngram_rights,
        "_utc_now",
        lambda: datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc),
    )
    proof = final_publication.require_ngram_daily_aggregate_rights(
        target=date(2026, 8, 9), root=root
    )
    assert proof["target_date"] == "2026-08-09"
    assert proof["recovery_exception_used"] is True
    assert ngram_rights.validate_daily_aggregate_rights_proof(
        proof, target=date(2026, 8, 9)
    ) == proof
    with pytest.raises(final_publication.FinalPublicationError) as exc:
        final_publication.require_ngram_daily_aggregate_rights(
            target=date(2026, 8, 8), root=root
        )
    assert exc.value.detail == "ngram_rights_target_too_old"
    with pytest.raises(final_publication.FinalPublicationError):
        final_publication.require_ngram_public_identity_rights(
            target=date(2026, 8, 9), root=root
        )


def test_recovery_reviewed_on_actual_as_of_requires_and_validates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src import final_publication, ngram_rights

    bundle, _key = _generated_bundle(
        tmp_path,
        monkeypatch,
        reviewed_on="2026-08-13",
        review_due="2027-08-13",
    )
    root = _applied_root(tmp_path, bundle)
    _pin_generated_signer(root, monkeypatch)
    monkeypatch.setattr(
        ngram_rights,
        "_utc_now",
        lambda: datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc),
    )
    proof = final_publication.require_ngram_daily_aggregate_rights(
        target=date(2026, 8, 9), root=root
    )
    assert proof["reviewed_on"] == "2026-08-13"
    assert proof["rights_as_of"] == "2026-08-14"
    assert proof["evaluated_age_days"] == 5
    assert proof["release_deadline_utc"] == "2027-08-13T23:59:59Z"
    assert proof["recovery_exception_used"] is True
    assert ngram_rights.validate_daily_aggregate_rights_proof(
        proof, target=date(2026, 8, 9)
    ) == proof
    with pytest.raises(final_publication.FinalPublicationError) as exc:
        final_publication.require_ngram_daily_aggregate_rights(
            target=date(2026, 8, 8), root=root
        )
    assert exc.value.detail == "ngram_rights_target_too_old"


def test_later_review_signs_exact_bounded_completed_outage_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src import final_publication, ngram_rights, ngram_rights_contract

    bundle, _key = _generated_bundle(
        tmp_path,
        monkeypatch,
        reviewed_on="2026-08-20",
        review_due="2027-08-20",
    )
    decision = json.loads((bundle / "decision.json").read_text(encoding="utf-8"))
    expected = [f"2026-08-{day:02d}" for day in range(9, 20)]
    assert decision["historical_recovery_targets"] == expected
    assert decision["historical_recovery_targets_sha256"] == (
        ngram_rights_contract.historical_recovery_targets_sha256(expected)
    )
    assert "2026-08-08" not in expected
    assert "2026-08-20" not in expected
    assert "2026-08-21" not in expected

    root = _applied_root(tmp_path, bundle)
    _pin_generated_signer(root, monkeypatch)
    monkeypatch.setattr(
        ngram_rights,
        "_utc_now",
        lambda: datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc),
    )
    replayed: dict[str, object] | None = None
    for target_text in expected:
        target = date.fromisoformat(target_text)
        proof = final_publication.require_ngram_daily_aggregate_rights(
            target=target, root=root
        )
        assert proof["historical_recovery_targets"] == expected
        assert ngram_rights.validate_daily_aggregate_rights_proof(
            proof, target=target
        ) == proof
        if target_text == "2026-08-09":
            replayed = proof
    assert replayed is not None
    hostile_vectors = {
        "prepend_pre_outage": ["2026-08-08", *expected],
        "append_review_day": [*expected, "2026-08-20"],
        "future_unbounded": [
            *expected,
            *[f"2026-08-{day:02d}" for day in range(20, 32)],
            "2026-09-01",
        ],
        "omit_interior": [item for item in expected if item != "2026-08-14"],
        "reorder": [expected[1], expected[0], *expected[2:]],
        "move_interior": [
            *expected[:5],
            "2026-08-20",
            *expected[6:],
        ],
        "duplicate": [*expected, expected[-1]],
    }
    for attacked_targets in hostile_vectors.values():
        attacked = dict(replayed)
        attacked["historical_recovery_targets"] = attacked_targets
        attacked["historical_recovery_targets_sha256"] = (
            ngram_rights_contract.historical_recovery_targets_sha256(
                attacked_targets
            )
        )
        with pytest.raises(ngram_rights.NgramRightsError) as exc:
            ngram_rights.validate_daily_aggregate_rights_proof(
                attacked, target=date(2026, 8, 9)
            )
        assert exc.value.code == "ngram_rights_recovery_binding_invalid"
    with pytest.raises(final_publication.FinalPublicationError) as exc:
        final_publication.require_ngram_daily_aggregate_rights(
            target=date(2026, 8, 8), root=root
        )
    assert exc.value.detail == "ngram_rights_target_too_old"
    prospective = final_publication.require_ngram_daily_aggregate_rights(
        target=date(2026, 8, 20), root=root
    )
    assert prospective["recovery_exception_used"] is False


def test_signer_refuses_unbounded_recovery_review_after_cutoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import ngram_rights_sign

    monkeypatch.setattr(ngram_rights_sign.sys, "stdin", _TTY())
    monkeypatch.setattr(ngram_rights_sign.sys, "stderr", _TTY())
    with pytest.raises(ngram_rights_sign.RightsSigningError) as exc:
        ngram_rights_sign.build_bundle(
            private_key_path=tmp_path / "human-key.pem",
            output=tmp_path / "late-review-bundle",
            reviewed_on="2026-09-02",
            review_due="2027-09-02",
        )
    assert str(exc.value) == "historical_recovery_review_outside_bounded_window"
    assert not (tmp_path / "late-review-bundle").exists()


def test_resealed_aggregate_proof_malformed_fields_refuse_stably(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src import final_publication, ngram_rights

    bundle, _key = _generated_bundle(tmp_path, monkeypatch)
    root = _applied_root(tmp_path, bundle)
    _pin_generated_signer(root, monkeypatch)
    monkeypatch.setattr(
        ngram_rights,
        "_utc_now",
        lambda: datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc),
    )
    proof = final_publication.require_ngram_daily_aggregate_rights(
        target=date(2026, 8, 9), root=root
    )
    attacks: tuple[tuple[str, object, str], ...] = (
        ("signer_revoked_on", True, "ngram_rights_proof_date_invalid"),
        ("signer_revoked_on", 20260815, "ngram_rights_proof_date_invalid"),
        ("signer_revoked_on", {}, "ngram_rights_proof_date_invalid"),
        ("signer_revoked_on", "2026-8-15", "ngram_rights_proof_date_invalid"),
        (
            "historical_recovery_targets",
            ["not-a-date"],
            "ngram_rights_recovery_binding_invalid",
        ),
        (
            "historical_recovery_targets",
            ["2026-08-09", {}],
            "ngram_rights_recovery_binding_invalid",
        ),
        ("evaluated_age_days", None, "ngram_rights_proof_temporal_invalid"),
        ("max_current_age_days", {}, "ngram_rights_proof_temporal_invalid"),
    )
    for field, malformed, expected_code in attacks:
        attacked = dict(proof)
        attacked[field] = malformed
        if field == "historical_recovery_targets":
            attacked["historical_recovery_targets_sha256"] = hashlib.sha256(
                json.dumps(malformed, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        with pytest.raises(ngram_rights.NgramRightsError) as exc:
            ngram_rights.validate_daily_aggregate_rights_proof(
                attacked, target=date(2026, 8, 9)
            )
        assert exc.value.code == expected_code

    revoked_before_as_of = dict(proof)
    revoked_before_as_of["signer_revoked_on"] = "2026-08-13"
    revoked_before_as_of["release_deadline_utc"] = "2026-08-12T23:59:59Z"
    with pytest.raises(ngram_rights.NgramRightsError) as exc:
        ngram_rights.validate_daily_aggregate_rights_proof(
            revoked_before_as_of, target=date(2026, 8, 9)
        )
    assert exc.value.code == "ngram_rights_proof_temporal_invalid"


def test_artifact_mutation_after_validation_cannot_escalate_captured_rights(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import ngram_rights_sign
    from src import final_publication, publication_guard

    bundle, key = _generated_bundle(tmp_path, monkeypatch)
    root = _applied_root(tmp_path, bundle)
    _pin_generated_signer(root, monkeypatch)
    artifact_path = (
        root / "governance/rights_decisions/gdelt_web_ngrams_v5-aggregate-2.0.json"
    )
    signature_path = artifact_path.with_suffix(".sig")
    original_validate = publication_guard._validate_rights_registry

    def validate_then_attack(
        document: dict[str, object],
        validation_root: Path,
        signers: dict[str, dict[str, object]],
    ) -> dict[str, dict[str, object]]:
        validated = original_validate(document, validation_root, signers)
        attacked = json.loads(artifact_path.read_text(encoding="utf-8"))
        attacked["permitted_uses"] = [
            "model_processing",
            "publish_derived_value",
            "publish_extract",
            "redistribute_full_record",
        ]
        attacked_bytes = ngram_rights_sign._canonical(attacked)
        artifact_path.write_bytes(attacked_bytes)
        signature_path.write_bytes(key.sign(attacked_bytes))
        return validated

    monkeypatch.setattr(
        publication_guard,
        "_validate_rights_registry",
        validate_then_attack,
    )
    proof = final_publication.require_ngram_daily_aggregate_rights(
        target=date(2026, 8, 11), root=root
    )
    assert proof["permitted_uses"] == ["model_processing", "publish_derived_value"]
    assert proof["decision_artifact_sha256"] != ngram_rights_sign.hashlib.sha256(
        artifact_path.read_bytes()
    ).hexdigest()

    with pytest.raises(final_publication.FinalPublicationError) as exc:
        final_publication.require_ngram_public_identity_rights(
            target=date(2026, 8, 11), root=root
        )
    assert exc.value.detail in {
        "rights_source_decision_artifact_digest_mismatch",
        "ngram_public_identity_use_not_permitted",
    }


@pytest.mark.parametrize(
    ("attack", "expected"),
    [
        ("missing", "rights_source_decision_artifact_fields_invalid"),
        ("extra", "rights_source_decision_artifact_fields_invalid"),
        ("profile", "rights_source_decision_artifact_mismatch"),
        ("citation", "rights_source_decision_artifact_mismatch"),
    ],
)
def test_generated_bundle_closed_schema_refuses_resigned_mutations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    attack: str,
    expected: str,
) -> None:
    from scripts import ngram_rights_sign
    from src import final_publication

    bundle, key = _generated_bundle(tmp_path, monkeypatch)
    root = _applied_root(tmp_path, bundle)
    decision_path = (
        root / "governance/rights_decisions/gdelt_web_ngrams_v5-aggregate-2.0.json"
    )
    signature_path = decision_path.with_suffix(".sig")
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    if attack == "missing":
        decision.pop("official_terms_citation")
    elif attack == "extra":
        decision["unreviewed_scope"] = "identity_retention"
    elif attack == "profile":
        decision["profile_id"] = "igrm:gdelt-ngram-identity:1.0.0"
    else:
        decision["official_terms_citation"]["url"] = "https://example.test/terms"
    artifact = ngram_rights_sign._canonical(decision)
    decision_path.write_bytes(artifact)
    signature_path.write_bytes(key.sign(artifact))
    registry_path = root / "governance/source_rights_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    source = next(
        row for row in registry["sources"] if row["source_id"] == "gdelt_web_ngrams_v5"
    )
    source["decision_artifact_sha256"] = ngram_rights_sign.hashlib.sha256(
        artifact
    ).hexdigest()
    registry_path.write_bytes(ngram_rights_sign._canonical(registry))
    _pin_generated_signer(root, monkeypatch)

    with pytest.raises(final_publication.FinalPublicationError) as exc:
        final_publication.require_ngram_daily_aggregate_rights(
            target=date(2026, 8, 11), root=root
        )
    assert exc.value.detail == expected
