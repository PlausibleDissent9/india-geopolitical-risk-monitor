"""The maritime publisher must never turn a registry label into permission."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from src import chokepoints

ROOT = Path(__file__).resolve().parents[1]


def _registry(tmp_path: Path, mutate) -> Path:  # type: ignore[no-untyped-def]
    document = json.loads(
        (ROOT / "governance/source_rights_registry.json").read_text(
            encoding="utf-8"
        )
    )
    mutate(document)
    path = tmp_path / "source_rights_registry.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_current_maritime_sources_reflect_signed_registry_state() -> None:
    """Tripwire on the exact states the manifest reports, updated at the
    founder's 2026-08-15 dual signing: gdelt_doc_api is approved (for the
    receipt-identity lane; this module only reports the state and never
    acquires), imf_portwatch stays pending. Any further state change must
    change this test in the same commit."""
    pending = chokepoints._rights_decision("imf_portwatch")
    assert pending["decision_state"] == "review_required"
    assert pending["decision_id"] == "pending:imf_portwatch"
    assert pending["signer_id"] is None
    signed = chokepoints._rights_decision("gdelt_doc_api")
    assert signed["decision_state"] == "approved"
    assert (
        signed["decision_id"] == "rights:gdelt_doc_api:receipt-identity-1.0:2026-08-15"
    )
    assert signed["signer_id"] == "human:igrm-ngram-rights-reviewer"
    assert signed["reviewed_on"] == "2026-08-15"


def test_rights_state_denied_blocks_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def deny(document: dict[str, object]) -> None:
        for row in document["sources"]:  # type: ignore[index,union-attr]
            if row["source_id"] == "gdelt_doc_api":
                # A denied row must also shed its approval-only fields, or
                # the registry validator refuses before the state check.
                row.update(  # type: ignore[union-attr]
                    decision_state="denied",
                    signer_id=None,
                    decision_artifact_path=None,
                    decision_artifact_sha256=None,
                    decision_signature_path=None,
                    reviewed_on=None,
                    review_due=None,
                    max_current_age_days=None,
                    permitted_uses=[],
                )

    monkeypatch.setattr(chokepoints, "RIGHTS_REGISTRY", _registry(tmp_path, deny))
    with pytest.raises(SystemExit, match="state blocks publication"):
        chokepoints._rights_decision("gdelt_doc_api")


def test_missing_rights_source_blocks_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def remove(document: dict[str, object]) -> None:
        document["sources"] = [  # type: ignore[index]
            row for row in document["sources"]  # type: ignore[index,union-attr]
            if row["source_id"] != "gdelt_doc_api"
        ]

    monkeypatch.setattr(chokepoints, "RIGHTS_REGISTRY", _registry(tmp_path, remove))
    with pytest.raises(SystemExit, match="missing unique rights row"):
        chokepoints._rights_decision("gdelt_doc_api")


def test_unsigned_approved_label_cannot_launder_rights(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_approval(document: dict[str, object]) -> None:
        for row in document["sources"]:  # type: ignore[index,union-attr]
            if row["source_id"] == "gdelt_doc_api":
                row["decision_state"] = "approved"
                row["permitted_uses"] = ["publish_derived_value"]
                row["reviewed_on"] = "2026-08-09"
                row["review_due"] = "2027-08-09"
                row["max_current_age_days"] = 7

    monkeypatch.setattr(
        chokepoints, "RIGHTS_REGISTRY", _registry(tmp_path, fake_approval)
    )
    with pytest.raises(SystemExit, match="invalid rights registry"):
        chokepoints._rights_decision("gdelt_doc_api")
