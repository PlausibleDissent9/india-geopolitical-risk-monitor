"""Hostile tests for the independent GDELT receipt-identity lane."""
from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from src import receipt_identity
from src import receipt_identity_rights as rights

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc)
TARGET = date(2026, 8, 11)


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_root(tmp_path: Path, *, active: bool) -> tuple[Path, Ed25519PrivateKey, str]:
    root = tmp_path / "root"
    for relative in (
        "dictionaries.json",
        "governance/gdelt_receipt_identity_profile.json",
        "governance/schemas/gdelt-receipt-identity-profile.schema.json",
        "docs/schemas/receipt-identity.schema.json",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)

    private = Ed25519PrivateKey.generate()
    public_raw = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    public_text = base64.b64encode(public_raw).decode("ascii")
    signer_id = "receipt_rights_reviewer"
    signers = {
        "schema_version": "1.0.0",
        "effective": "2026-08-01",
        "default_policy": "deny",
        "signers": [
            {
                "signer_id": signer_id,
                "name": "Synthetic reviewer",
                "role": "rights_reviewer",
                "public_key_ed25519_base64": public_text,
                "effective": "2026-08-01",
                "revoked_on": None,
            }
        ],
    }
    _write(root / "governance/rights_signers.json", signers)

    source = json.loads(
        (ROOT / "governance/source_rights_registry.json").read_text(encoding="utf-8")
    )["sources"][1]
    assert source["source_id"] == rights.SOURCE_ID
    source = dict(source)
    if not active:
        # The live row is approved since the founder's 2026-08-15 signing;
        # the pending scenario needs the pre-decision shape back.
        source.update(
            decision_state="review_required",
            decision_id=f"pending:{rights.SOURCE_ID}",
            decision_owner="unassigned",
            signer_id=None,
            decision_artifact_path=None,
            decision_artifact_sha256=None,
            decision_signature_path=None,
            reviewed_on=None,
            review_due=None,
            max_current_age_days=None,
            permitted_uses=[],
        )
    if active:
        source.update(
            {
                "decision_state": "approved",
                "decision_id": "receipt_identity_approved_fixture",
                "decision_owner": "synthetic_test_only",
                "signer_id": signer_id,
                "decision_artifact_path": (
                    "governance/rights_decisions/gdelt_doc_api.json"
                ),
                "decision_signature_path": (
                    "governance/rights_decisions/gdelt_doc_api.sig"
                ),
                "reviewed_on": "2026-08-01",
                "review_due": "2026-08-31",
                "terms_url": "https://www.gdeltproject.org/about.html",
                "access_basis": "signed_fixture_only",
                "max_current_age_days": 1,
                "permitted_uses": list(rights.CANONICAL_REQUIRED_USES),
            }
        )
        artifact_fields = {
            "source_id",
            "name",
            "provider",
            "role",
            "authority_class",
            "independence_group",
            "decision_id",
            "decision_owner",
            "signer_id",
            "reviewed_on",
            "review_due",
            "access_url",
            "terms_url",
            "access_basis",
            "lineage_policy",
            "max_current_age_days",
            "permitted_uses",
        }
        artifact = {"schema_version": "1.0.0"}
        artifact.update({field: source[field] for field in artifact_fields})
        artifact["statement"] = "Synthetic fixture; no production force."
        artifact_path = root / source["decision_artifact_path"]
        _write(artifact_path, artifact)
        signature_path = root / source["decision_signature_path"]
        signature_path.parent.mkdir(parents=True, exist_ok=True)
        signature_path.write_bytes(private.sign(artifact_path.read_bytes()))
        source["decision_artifact_sha256"] = _sha(artifact_path)

    registry = {
        "schema_version": "1.0.0",
        "effective": "2026-08-01",
        "default_policy": "deny",
        "sources": [source],
    }
    _write(root / "governance/source_rights_registry.json", registry)

    profile_path = root / "governance/gdelt_receipt_identity_profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if active:
        profile["activation"] = {
            "state": "active",
            "signer_id": signer_id,
            "reviewed_on": "2026-08-01",
            "review_due": "2026-08-31",
            "signature_path": "governance/rights_decisions/gdelt_receipt_identity_profile.sig",
        }
        _write(profile_path, profile)
        profile_signature = root / profile["activation"]["signature_path"]
        profile_signature.parent.mkdir(parents=True, exist_ok=True)
        profile_signature.write_bytes(private.sign(profile_path.read_bytes()))
    else:
        # The live profile is active since the founder's 2026-08-15
        # activation; the pending scenario needs the pre-signature shape.
        profile["activation"] = {
            "state": "inactive_pending_human_signature",
            "signer_id": None,
            "reviewed_on": None,
            "review_due": None,
            "signature_path": None,
        }
        _write(profile_path, profile)
    return root, private, public_text


class ExplodingClient:
    def fetch(self, query: str, target: date) -> object:
        raise AssertionError("network must not be reached")


class FakeClient:
    def __init__(self, *, fail_on_call: int | None = None, invalid_on_call: int | None = None):
        self.calls: list[tuple[str, date]] = []
        self.fail_on_call = fail_on_call
        self.invalid_on_call = invalid_on_call

    def fetch(self, query: str, target: date) -> object:
        self.calls.append((query, target))
        call = len(self.calls)
        if call == self.fail_on_call:
            raise RuntimeError("source unavailable")
        if call == self.invalid_on_call:
            return {"articles": [], "smuggled": 7}
        rows = [
            {
                "title": f"Headline {call}-{index}",
                "url": f"https://www.example{call}.com/story/{index}#tracking",
                "domain": "ignored.example",
                "seendate": "20260811T010000Z",
                "socialimage": "https://images.invalid/image.jpg",
            }
            for index in range(8)
        ]
        # Duplicate URL and duplicate title across a different URL must both collapse.
        rows.append(dict(rows[0]))
        rows.append({**rows[1], "url": f"https://mirror{call}.example/copy"})
        return {"articles": rows}


@pytest.fixture()
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rights, "_utc_now", lambda: NOW)


def _test_authority(root: Path) -> rights.NonGitTestRightsAuthority:
    return rights.non_git_test_authority(root)


def test_pending_profile_is_value_free_and_pre_network(
    tmp_path: Path, fixed_clock: None
) -> None:
    root, _, _ = _fixture_root(tmp_path, active=False)
    output = tmp_path / "out.json"
    payload = receipt_identity.execute(
        today=NOW.date(),
        generated_at=NOW,
        root=root,
        path=output,
        client=ExplodingClient(),
        test_authority=_test_authority(root),
    )
    assert payload["state"] == "unavailable"
    assert payload["target_date"] == TARGET.isoformat()
    assert "authority" not in payload
    assert payload["refusal"]["blockers"] == [
        "receipt_identity_profile_inactive",
        "receipt_identity_source_decision_review_required",
    ]
    encoded = json.dumps(payload).lower()
    for forbidden in (
        "article_body",
        '"articles"',
        "snippet",
        "story_id",
        "socialimage",
        "seendate",
    ):
        assert forbidden not in encoded


def test_authorized_lane_is_exact_d_minus_1_bounded_and_content_minimal(
    tmp_path: Path, fixed_clock: None
) -> None:
    root, _, _ = _fixture_root(tmp_path, active=True)
    client = FakeClient()
    payload = receipt_identity.execute(
        today=NOW.date(),
        generated_at=NOW,
        root=root,
        path=tmp_path / "out.json",
        client=client,
        test_authority=_test_authority(root),
    )
    assert payload["state"] == "available"
    assert len(client.calls) == receipt_identity.MAX_REQUESTS_PER_RUN == 7
    assert all(target == TARGET for _, target in client.calls)
    assert tuple(payload["channels"]) == receipt_identity.CHANNELS
    for block in payload["channels"].values():
        assert block["state"] == "available"
        assert len(block["articles"]) == 5
        assert all(set(article) == {"title", "url", "domain"} for article in block["articles"])
        assert all("#" not in article["url"] for article in block["articles"])
        assert len({article["title"] for article in block["articles"]}) == 5
    encoded = json.dumps(payload).lower()
    for forbidden in (
        "article_body",
        "snippet",
        "socialimage",
        "seendate",
        "document_id",
        "raw_response",
    ):
        assert forbidden not in encoded


def test_zero_is_available_while_failure_is_missing(
    tmp_path: Path, fixed_clock: None
) -> None:
    root, _, _ = _fixture_root(tmp_path, active=True)

    class ZeroAndMissing(FakeClient):
        def fetch(self, query: str, target: date) -> object:
            self.calls.append((query, target))
            if len(self.calls) == 4:
                raise RuntimeError("outage")
            if len(self.calls) == 3:
                return {"articles": []}
            call = len(self.calls)
            return {
                "articles": [
                    {
                        "title": f"Headline {call}",
                        "url": f"https://example{call}.com/story",
                    }
                ]
            }

    client = ZeroAndMissing()
    payload = receipt_identity.execute(
        today=NOW.date(),
        generated_at=NOW,
        root=root,
        path=tmp_path / "out.json",
        client=client,
        test_authority=_test_authority(root),
    )
    assert payload["state"] == "partial"
    assert payload["channels"]["china_east"] == {
        "state": "available",
        "articles": [],
    }
    assert payload["channels"]["gulf_energy"] == {
        "state": "unavailable",
        "reason_code": "source_unavailable",
    }


def test_source_response_invalid_is_not_reported_as_zero(
    tmp_path: Path, fixed_clock: None
) -> None:
    root, _, _ = _fixture_root(tmp_path, active=True)
    payload = receipt_identity.execute(
        today=NOW.date(),
        generated_at=NOW,
        root=root,
        path=tmp_path / "out.json",
        client=FakeClient(invalid_on_call=3),
        test_authority=_test_authority(root),
    )
    assert payload["channels"]["china_east"] == {
        "state": "unavailable",
        "reason_code": "source_response_invalid",
    }


def test_same_target_available_to_partial_retains_exact_prior_rows(
    tmp_path: Path, fixed_clock: None
) -> None:
    root, _, _ = _fixture_root(tmp_path, active=True)
    authority = _test_authority(root)
    prior = receipt_identity.execute(
        today=NOW.date(), generated_at=NOW, root=root, path=tmp_path / "prior.json",
        client=FakeClient(), test_authority=authority
    )
    predecessor = receipt_identity.non_git_test_predecessor(prior, root=root)
    retried = receipt_identity.execute(
        today=NOW.date(), generated_at=NOW, root=root, path=tmp_path / "retry.json",
        client=FakeClient(fail_on_call=1), test_authority=authority,
        test_predecessor=predecessor,
    )
    assert retried["state"] == "available"
    assert retried["channels"] == prior["channels"]
    assert retried["predecessor"]["state"] == "same_target"


def test_same_target_partial_to_unavailable_cannot_remove_available_rows(
    tmp_path: Path, fixed_clock: None
) -> None:
    root, _, _ = _fixture_root(tmp_path, active=True)
    authority = _test_authority(root)
    prior = receipt_identity.execute(
        today=NOW.date(), generated_at=NOW, root=root, path=tmp_path / "prior.json",
        client=FakeClient(fail_on_call=1), test_authority=authority
    )

    class AllUnavailable:
        def fetch(self, query: str, target: date) -> object:
            raise RuntimeError("outage")

    retried = receipt_identity.execute(
        today=NOW.date(), generated_at=NOW, root=root, path=tmp_path / "retry.json",
        client=AllUnavailable(), test_authority=authority,
        test_predecessor=receipt_identity.non_git_test_predecessor(prior, root=root),
    )
    assert retried["state"] == "partial"
    assert retried["channels"]["pakistan_west"]["state"] == "unavailable"
    for channel in receipt_identity.CHANNELS[1:]:
        assert retried["channels"][channel] == prior["channels"][channel]


def test_same_target_partial_to_more_available_succeeds_monotonically(
    tmp_path: Path, fixed_clock: None
) -> None:
    root, _, _ = _fixture_root(tmp_path, active=True)
    authority = _test_authority(root)
    prior = receipt_identity.execute(
        today=NOW.date(), generated_at=NOW, root=root, path=tmp_path / "prior.json",
        client=FakeClient(fail_on_call=1), test_authority=authority
    )
    retried = receipt_identity.execute(
        today=NOW.date(), generated_at=NOW, root=root, path=tmp_path / "retry.json",
        client=FakeClient(), test_authority=authority,
        test_predecessor=receipt_identity.non_git_test_predecessor(prior, root=root),
    )
    assert retried["state"] == "available"
    assert retried["channels"]["pakistan_west"]["state"] == "available"
    for channel in receipt_identity.CHANNELS[1:]:
        assert retried["channels"][channel] == prior["channels"][channel]


def test_same_target_different_fetch_rows_are_replaced_by_exact_predecessor(
    tmp_path: Path, fixed_clock: None
) -> None:
    root, _, _ = _fixture_root(tmp_path, active=True)
    authority = _test_authority(root)
    prior = receipt_identity.execute(
        today=NOW.date(), generated_at=NOW, root=root, path=tmp_path / "prior.json",
        client=FakeClient(), test_authority=authority
    )

    class DifferentRows(FakeClient):
        def fetch(self, query: str, target: date) -> object:
            response = super().fetch(query, target)
            assert isinstance(response, dict)
            for article in response["articles"]:
                article["title"] = "Changed " + article["title"]
            return response

    retried = receipt_identity.execute(
        today=NOW.date(), generated_at=NOW, root=root, path=tmp_path / "retry.json",
        client=DifferentRows(), test_authority=authority,
        test_predecessor=receipt_identity.non_git_test_predecessor(prior, root=root),
    )
    assert retried["channels"] == prior["channels"]


def test_non_git_predecessor_digest_cannot_be_spliced(
    tmp_path: Path, fixed_clock: None
) -> None:
    root, _, _ = _fixture_root(tmp_path, active=True)
    authority = _test_authority(root)
    prior = receipt_identity.execute(
        today=NOW.date(), generated_at=NOW, root=root, path=tmp_path / "prior.json",
        client=FakeClient(), test_authority=authority
    )
    predecessor = receipt_identity.non_git_test_predecessor(prior, root=root)
    spliced = receipt_identity.PredecessorSnapshot(
        predecessor.commit_sha,
        predecessor.state,
        predecessor.blob_git_sha1,
        "0" * 64,
        predecessor.target_date,
        predecessor.payload,
    )
    with pytest.raises(receipt_identity.ReceiptIdentityRefusal) as exc:
        receipt_identity.execute(
            today=NOW.date(), generated_at=NOW, root=root,
            path=tmp_path / "retry.json", client=FakeClient(),
            test_authority=authority, test_predecessor=spliced,
        )
    assert exc.value.code == "receipt_identity_test_predecessor_invalid"


def test_provider_duplicate_json_is_typed_invalid_without_network_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        status_code = 200
        content = b'{"articles":[],"articles":[]}'

    monkeypatch.setattr(receipt_identity.requests, "get", lambda *args, **kwargs: Response())
    client = receipt_identity.GdeltDocArticleListClient()
    with pytest.raises(receipt_identity.ArticleListResponseInvalid):
        client.fetch("registered query", TARGET)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/story",
        "http://[::1]/story",
        "https://localhost/story",
        "https://publisher.local/story",
        "https://user:secret" + "@" + "publisher.invalid/story",
    ],
)
def test_nonpublic_or_credentialed_article_urls_are_discarded(url: str) -> None:
    assert receipt_identity._normalize_url(url) is None


@pytest.mark.parametrize(
    "uses",
    [
        ["cite_metadata", "model_processing"],
        ["cite_metadata", "model_processing", "publish_extract", "publish_derived_value"],
        ["cite_metadata", "model_processing", "publish_extract", "publish_extract"],
        ["model_processing", "cite_metadata", "publish_extract"],
        ["cite_metadata", "model_processing", 7],
    ],
)
def test_source_use_vector_must_be_exact(
    tmp_path: Path, fixed_clock: None, uses: list[object]
) -> None:
    root, _, _ = _fixture_root(tmp_path, active=True)
    registry_path = root / "governance/source_rights_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["sources"][0]["permitted_uses"] = uses
    _write(registry_path, registry)
    snapshot, proof = rights.evaluate_authority(
        target=TARGET, root=root, test_authority=_test_authority(root)
    )
    assert proof is None
    assert snapshot["authorization_status"] == "receipt_identity_source_use_not_permitted"


def test_profile_signature_is_separate_and_exact(
    tmp_path: Path, fixed_clock: None
) -> None:
    root, _, _ = _fixture_root(tmp_path, active=True)
    authority = _test_authority(root)
    snapshot, proof = rights.evaluate_authority(target=TARGET, root=root, test_authority=authority)
    assert snapshot["authorization_status"] == "authorized"
    assert proof is not None
    profile = root / "governance/gdelt_receipt_identity_profile.json"
    profile.write_bytes(profile.read_bytes() + b"\n")
    changed_snapshot, changed_proof = rights.evaluate_authority(
        target=TARGET, root=root, test_authority=authority
    )
    assert changed_proof is None
    assert (
        changed_snapshot["authorization_status"]
        == "receipt_identity_profile_signature_invalid"
    )


def test_revocation_and_future_target_refuse(
    tmp_path: Path, fixed_clock: None
) -> None:
    root, _, _ = _fixture_root(tmp_path, active=True)
    signers_path = root / "governance/rights_signers.json"
    signers = json.loads(signers_path.read_text(encoding="utf-8"))
    signers["signers"][0]["revoked_on"] = "2026-08-12"
    _write(signers_path, signers)
    authority = _test_authority(root)
    snapshot, proof = rights.evaluate_authority(target=TARGET, root=root, test_authority=authority)
    assert proof is None
    assert snapshot["authorization_status"] == "receipt_identity_source_signer_revoked"
    root2, _, _ = _fixture_root(tmp_path / "future", active=True)
    snapshot2, proof2 = rights.evaluate_authority(
        target=NOW.date(), root=root2, test_authority=_test_authority(root2)
    )
    assert proof2 is None
    assert snapshot2["authorization_status"] == "receipt_identity_target_not_completed_d_minus_1"


def test_source_signer_must_have_been_effective_on_review_day(
    tmp_path: Path, fixed_clock: None
) -> None:
    root, _, _ = _fixture_root(tmp_path, active=True)
    signers_path = root / "governance/rights_signers.json"
    signers = json.loads(signers_path.read_text(encoding="utf-8"))
    signers["signers"][0]["effective"] = "2026-08-02"
    _write(signers_path, signers)
    snapshot, proof = rights.evaluate_authority(
        target=TARGET, root=root, test_authority=_test_authority(root)
    )
    assert proof is None
    assert snapshot["authorization_status"] == "receipt_identity_source_signer_untrusted"


def test_authority_mutation_after_first_fetch_prevents_write(
    tmp_path: Path, fixed_clock: None
) -> None:
    root, _, _ = _fixture_root(tmp_path, active=True)
    output = tmp_path / "out.json"
    registry_path = root / "governance/source_rights_registry.json"

    class MutatingClient(FakeClient):
        def fetch(self, query: str, target: date) -> object:
            result = super().fetch(query, target)
            if len(self.calls) == 1:
                registry = json.loads(registry_path.read_text(encoding="utf-8"))
                registry["sources"][0]["review_due"] = "2026-08-30"
                _write(registry_path, registry)
            return result

    with pytest.raises(receipt_identity.ReceiptIdentityRefusal):
        receipt_identity.execute(
            today=NOW.date(),
            generated_at=NOW,
            root=root,
            path=output,
            client=MutatingClient(),
            test_authority=_test_authority(root),
        )
    assert not output.exists()


def test_closed_payload_rejects_extra_values_even_when_resealed(
    tmp_path: Path, fixed_clock: None
) -> None:
    root, _, _ = _fixture_root(tmp_path, active=False)
    payload = receipt_identity.execute(
        today=NOW.date(), generated_at=NOW, root=root, path=tmp_path / "out.json",
        client=ExplodingClient(), test_authority=_test_authority(root)
    )
    payload["refusal"]["invented_count"] = 7
    payload["payload_seal_sha256"] = receipt_identity._payload_seal(payload)
    with pytest.raises(receipt_identity.ReceiptIdentityRefusal):
        receipt_identity.validate_payload(payload, root=root)

    payload["refusal"].pop("invented_count")
    payload["_meta"]["what"] = "A source-derived story smuggled into status prose"
    payload["payload_seal_sha256"] = receipt_identity._payload_seal(payload)
    with pytest.raises(receipt_identity.ReceiptIdentityRefusal):
        receipt_identity.validate_payload(payload, root=root)


def test_active_payload_rejects_extra_proof_fields_after_reseal(
    tmp_path: Path, fixed_clock: None
) -> None:
    root, _, _ = _fixture_root(tmp_path, active=True)
    payload = receipt_identity.execute(
        today=NOW.date(),
        generated_at=NOW,
        root=root,
        path=tmp_path / "out.json",
        client=FakeClient(),
        test_authority=_test_authority(root),
    )
    payload["authority"]["evaluations"][0]["proof"]["invented_grant"] = True
    payload["payload_seal_sha256"] = receipt_identity._payload_seal(payload)
    with pytest.raises(receipt_identity.ReceiptIdentityRefusal):
        receipt_identity.validate_payload(payload, root=root)


def test_lane_writes_no_legacy_or_score_path(
    tmp_path: Path, fixed_clock: None
) -> None:
    root, _, _ = _fixture_root(tmp_path, active=False)
    protected = [
        "docs/data/latest.json",
        "docs/data/receipts.json",
        "docs/data/receipts_archive.json",
        "data/raw/gdelt_volume.csv",
        "data/raw/ngram_days",
        "data/raw/receipt_days",
    ]
    receipt_identity.execute(
        today=NOW.date(), generated_at=NOW, root=root, path=root / receipt_identity.OUTPUT_RELATIVE,
        client=ExplodingClient(), test_authority=_test_authority(root)
    )
    assert all(not (root / relative).exists() for relative in protected)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _init_git_predecessor(root: Path) -> str:
    _git(root, "init")
    _git(root, "config", "user.name", "test")
    _git(root, "config", "user.email", "test.invalid")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "predecessor")
    predecessor = _git(root, "rev-parse", "HEAD")
    _git(root, "update-ref", "refs/remotes/origin/main", predecessor)
    return predecessor


def test_release_reads_exact_regular_candidate_blob_and_refuses_overlay(
    tmp_path: Path, fixed_clock: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _, public_text = _fixture_root(tmp_path, active=True)
    role = "rights_reviewer"
    monkeypatch.setattr(
        rights,
        "PRODUCTION_TRUSTED_SIGNERS",
        {"receipt_rights_reviewer": (public_text, role)},
    )
    predecessor = _init_git_predecessor(root)
    receipt_identity.execute(
        today=NOW.date(), generated_at=NOW, root=root,
        path=root / receipt_identity.OUTPUT_RELATIVE, client=FakeClient()
    )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "candidate")
    candidate = _git(root, "rev-parse", "HEAD")
    result = receipt_identity.check_release_rights(
        expected_candidate_sha=candidate, root=root
    )
    assert result["status"] == "receipt_identity_release_verified"
    assert result["predecessor_commit_sha"] == predecessor
    assert result["predecessor_blob_sha256"] is None
    output = root / receipt_identity.OUTPUT_RELATIVE
    output.write_text(output.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(receipt_identity.ReceiptIdentityRefusal) as exc:
        receipt_identity.check_release_rights(
            expected_candidate_sha=candidate, root=root
        )
    assert exc.value.code == "receipt_identity_release_tree_dirty"
    _git(root, "add", "--", receipt_identity.OUTPUT_RELATIVE.as_posix())
    with pytest.raises(receipt_identity.ReceiptIdentityRefusal) as staged_exc:
        receipt_identity.check_release_rights(
            expected_candidate_sha=candidate, root=root
        )
    assert staged_exc.value.code == "receipt_identity_release_tree_dirty"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("remove_channel", "receipt_identity_predecessor_channel_regression"),
        ("change_articles", "receipt_identity_predecessor_articles_changed"),
    ],
)
def test_release_refuses_same_target_available_regression(
    tmp_path: Path,
    fixed_clock: None,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected_code: str,
) -> None:
    root, _, public_text = _fixture_root(tmp_path, active=True)
    monkeypatch.setattr(
        rights,
        "PRODUCTION_TRUSTED_SIGNERS",
        {"receipt_rights_reviewer": (public_text, "rights_reviewer")},
    )
    _init_git_predecessor(root)
    receipt_identity.execute(
        today=NOW.date(), generated_at=NOW, root=root,
        path=root / receipt_identity.OUTPUT_RELATIVE, client=FakeClient()
    )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "published predecessor")
    predecessor = _git(root, "rev-parse", "HEAD")
    _git(root, "update-ref", "refs/remotes/origin/main", predecessor)
    output = root / receipt_identity.OUTPUT_RELATIVE
    payload = json.loads(output.read_text(encoding="utf-8"))
    snapshot = receipt_identity._load_predecessor(
        root=root, ref=predecessor, require_remote=True,
        exit_code=receipt_identity.EXIT_RELEASE_REFUSED,
    )
    payload["predecessor"] = receipt_identity._predecessor_binding(snapshot, TARGET)
    if mutation == "remove_channel":
        payload["channels"]["pakistan_west"] = {
            "state": "unavailable",
            "reason_code": "source_unavailable",
        }
        payload["state"] = "partial"
    else:
        payload["channels"]["pakistan_west"]["articles"][0]["title"] = (
            "Different signed-looking title"
        )
    payload["payload_seal_sha256"] = receipt_identity._payload_seal(payload)
    _write(output, payload)
    _git(root, "add", receipt_identity.OUTPUT_RELATIVE.as_posix())
    _git(root, "commit", "-m", "regressive retry")
    candidate = _git(root, "rev-parse", "HEAD")
    with pytest.raises(receipt_identity.ReceiptIdentityRefusal) as exc:
        receipt_identity.check_release_rights(
            expected_candidate_sha=candidate, root=root
        )
    assert exc.value.code == expected_code


def test_current_rights_revocation_allows_value_free_withdrawal(
    tmp_path: Path, fixed_clock: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _, public_text = _fixture_root(tmp_path, active=True)
    monkeypatch.setattr(
        rights,
        "PRODUCTION_TRUSTED_SIGNERS",
        {"receipt_rights_reviewer": (public_text, "rights_reviewer")},
    )
    _init_git_predecessor(root)
    receipt_identity.execute(
        today=NOW.date(), generated_at=NOW, root=root,
        path=root / receipt_identity.OUTPUT_RELATIVE, client=FakeClient()
    )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "published values")
    published = _git(root, "rev-parse", "HEAD")
    _git(root, "update-ref", "refs/remotes/origin/main", published)

    signers_path = root / "governance/rights_signers.json"
    signers = json.loads(signers_path.read_text(encoding="utf-8"))
    signers["signers"][0]["revoked_on"] = NOW.date().isoformat()
    _write(signers_path, signers)
    _git(root, "add", signers_path.relative_to(root).as_posix())
    _git(root, "commit", "-m", "revoke source signer")
    revoked_parent = _git(root, "rev-parse", "HEAD")
    _git(root, "update-ref", "refs/remotes/origin/main", revoked_parent)

    payload = receipt_identity.execute(
        today=NOW.date(), generated_at=NOW, root=root,
        path=root / receipt_identity.OUTPUT_RELATIVE, client=ExplodingClient()
    )
    assert payload["state"] == "unavailable"
    assert "authority" not in payload
    assert '"articles"' not in json.dumps(payload)
    assert payload["predecessor"]["state"] == "same_target"
    _git(root, "add", receipt_identity.OUTPUT_RELATIVE.as_posix())
    _git(root, "commit", "-m", "withdraw values")
    candidate = _git(root, "rev-parse", "HEAD")
    result = receipt_identity.check_release_rights(
        expected_candidate_sha=candidate, root=root
    )
    assert result["status"] == "unavailable_status_release_verified"
    assert result["predecessor_commit_sha"] == revoked_parent
    assert result["predecessor_blob_sha256"] is not None


def test_post_rebase_changed_predecessor_blob_is_refused(
    tmp_path: Path, fixed_clock: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _, public_text = _fixture_root(tmp_path, active=True)
    monkeypatch.setattr(
        rights,
        "PRODUCTION_TRUSTED_SIGNERS",
        {"receipt_rights_reviewer": (public_text, "rights_reviewer")},
    )
    _init_git_predecessor(root)
    output = root / receipt_identity.OUTPUT_RELATIVE
    receipt_identity.execute(
        today=NOW.date(), generated_at=NOW, root=root, path=output,
        client=FakeClient(fail_on_call=1)
    )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "partial predecessor")
    predecessor_a = _git(root, "rev-parse", "HEAD")
    _git(root, "update-ref", "refs/remotes/origin/main", predecessor_a)
    predecessor_a_bytes = output.read_bytes()

    receipt_identity.execute(
        today=NOW.date(), generated_at=NOW, root=root, path=output,
        client=FakeClient()
    )
    stale_candidate_bytes = output.read_bytes()
    output.write_bytes(predecessor_a_bytes)

    class DifferentRecovery(FakeClient):
        def fetch(self, query: str, target: date) -> object:
            response = super().fetch(query, target)
            assert isinstance(response, dict)
            for article in response["articles"]:
                article["title"] = "Concurrent " + article["title"]
            return response

    receipt_identity.execute(
        today=NOW.date(), generated_at=NOW, root=root, path=output,
        client=DifferentRecovery()
    )
    _git(root, "add", receipt_identity.OUTPUT_RELATIVE.as_posix())
    _git(root, "commit", "-m", "concurrent stronger retry")
    predecessor_b = _git(root, "rev-parse", "HEAD")
    _git(root, "update-ref", "refs/remotes/origin/main", predecessor_b)

    output.write_bytes(stale_candidate_bytes)
    _git(root, "add", receipt_identity.OUTPUT_RELATIVE.as_posix())
    _git(root, "commit", "-m", "rebased stale retry")
    rebased_candidate = _git(root, "rev-parse", "HEAD")
    with pytest.raises(receipt_identity.ReceiptIdentityRefusal) as exc:
        receipt_identity.check_release_rights(
            expected_candidate_sha=rebased_candidate, root=root
        )
    assert exc.value.code == "receipt_identity_release_predecessor_binding_invalid"


def test_inactive_candidate_release_is_value_free_and_verified(
    tmp_path: Path, fixed_clock: None
) -> None:
    root, _, _ = _fixture_root(tmp_path, active=False)
    predecessor = _init_git_predecessor(root)
    receipt_identity.execute(
        today=NOW.date(),
        generated_at=NOW,
        root=root,
        path=root / receipt_identity.OUTPUT_RELATIVE,
        client=ExplodingClient(),
    )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "inactive candidate")
    candidate = _git(root, "rev-parse", "HEAD")
    result = receipt_identity.check_release_rights(
        expected_candidate_sha=candidate, root=root
    )
    assert result["status"] == "unavailable_status_release_verified"
    assert result["predecessor_commit_sha"] == predecessor

    _git(root, "update-ref", "refs/remotes/origin/main", candidate)
    output = root / receipt_identity.OUTPUT_RELATIVE
    raw = output.read_text(encoding="utf-8")
    raw = raw.replace(
        ' "state": "unavailable",',
        ' "state": "unavailable",\n "state": "unavailable",',
        1,
    )
    output.write_text(raw, encoding="utf-8")
    _git(root, "add", receipt_identity.OUTPUT_RELATIVE.as_posix())
    _git(root, "commit", "-m", "duplicate payload key")
    duplicate_candidate = _git(root, "rev-parse", "HEAD")
    with pytest.raises(receipt_identity.ReceiptIdentityRefusal) as duplicate_exc:
        receipt_identity.check_release_rights(
            expected_candidate_sha=duplicate_candidate, root=root
        )
    assert duplicate_exc.value.code == "receipt_identity_release_payload_invalid"


def test_release_refuses_candidate_splice_and_future_generation(
    tmp_path: Path, fixed_clock: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _, public_text = _fixture_root(tmp_path, active=True)
    monkeypatch.setattr(
        rights,
        "PRODUCTION_TRUSTED_SIGNERS",
        {"receipt_rights_reviewer": (public_text, "rights_reviewer")},
    )
    _init_git_predecessor(root)
    future = NOW.replace(hour=23, minute=59)
    receipt_identity.execute(
        today=NOW.date(),
        generated_at=future,
        root=root,
        path=root / receipt_identity.OUTPUT_RELATIVE,
        client=FakeClient(),
    )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "future candidate")
    candidate = _git(root, "rev-parse", "HEAD")
    with pytest.raises(receipt_identity.ReceiptIdentityRefusal) as future_exc:
        receipt_identity.check_release_rights(
            expected_candidate_sha=candidate, root=root
        )
    assert future_exc.value.code == "receipt_identity_release_temporal_invalid"
    marker = root / "marker"
    marker.write_text("new candidate\n", encoding="utf-8")
    _git(root, "add", "marker")
    _git(root, "commit", "-m", "splice")
    with pytest.raises(receipt_identity.ReceiptIdentityRefusal) as splice_exc:
        receipt_identity.check_release_rights(
            expected_candidate_sha=candidate, root=root
        )
    assert splice_exc.value.code == "receipt_identity_release_candidate_changed"


def test_candidate_reader_rejects_symlink_and_submodule_modes(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.name", "test")
    _git(root, "config", "user.email", "test.invalid")
    target = root / receipt_identity.OUTPUT_RELATIVE
    target.parent.mkdir(parents=True)
    target.symlink_to("/tmp/external-receipt.json")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "symlink")
    candidate = _git(root, "rev-parse", "HEAD")
    with pytest.raises(rights.ReceiptIdentityRightsError) as exc:
        rights.CandidateAuthorityReader(root, candidate).read(
            receipt_identity.OUTPUT_RELATIVE.as_posix(), "tree_invalid"
        )
    assert exc.value.code == "tree_invalid"

    target.unlink()
    _git(root, "rm", "--cached", receipt_identity.OUTPUT_RELATIVE.as_posix())
    _git(
        root,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{candidate},{receipt_identity.OUTPUT_RELATIVE.as_posix()}",
    )
    _git(root, "commit", "-m", "gitlink")
    gitlink_candidate = _git(root, "rev-parse", "HEAD")
    with pytest.raises(rights.ReceiptIdentityRightsError) as gitlink_exc:
        rights.CandidateAuthorityReader(root, gitlink_candidate).read(
            receipt_identity.OUTPUT_RELATIVE.as_posix(), "tree_invalid"
        )
    assert gitlink_exc.value.code == "tree_invalid"


def test_profile_active_and_signature_verifies_against_pinned_key() -> None:
    """Tripwire on the lane's two-gate state, updated 2026-08-15 (late).

    The founder-run dual ceremony signed the gdelt_doc_api source decision,
    the reviewed commit pinned the enrolled signer, and the founder-run
    activation ceremony then signed the profile itself. Both gates are now
    closed by the same enrolled human; the activation signature must verify
    over the EXACT committed profile bytes against the code-pinned key. Any
    change to either gate must change this test in the same commit.
    """
    profile_path = ROOT / "governance/gdelt_receipt_identity_profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    assert profile["activation"] == {
        "state": "active",
        "signer_id": "human:igrm-ngram-rights-reviewer",
        "reviewed_on": "2026-08-15",
        "review_due": "2026-11-13",
        "signature_path": (
            "governance/rights_decisions/"
            "gdelt_doc_receipt_identity_v1-activation-1.0.sig"
        ),
    }
    assert rights.PRODUCTION_TRUSTED_SIGNERS == {
        "human:igrm-ngram-rights-reviewer": (
            "qcS/4lMEpmUO0RhFRkVILagrVBIhMsSfVYksZmRvgFQ=",
            "rights_reviewer",
        ),
    }
    decision_signature = (
        ROOT / "governance/rights_decisions/gdelt_doc_api-receipt-identity-1.0.sig"
    )
    assert len(decision_signature.read_bytes()) == 64
    activation_signature = (ROOT / profile["activation"]["signature_path"]).read_bytes()
    assert len(activation_signature) == 64
    pinned = Ed25519PublicKey.from_public_bytes(
        base64.b64decode(
            rights.PRODUCTION_TRUSTED_SIGNERS["human:igrm-ngram-rights-reviewer"][0]
        )
    )
    pinned.verify(activation_signature, profile_path.read_bytes())


def test_predecessor_written_under_prior_profile_survives_activation(
    tmp_path: Path, fixed_clock: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A profile transition must not deadlock the lane.

    The committed payload binds the profile it was WRITTEN under; the next
    run validates it at its writing commit, not against the tip's profile.
    Before the 2026-08-15 activation this exact shape refused with
    receipt_identity_payload_profile_invalid and no new payload could ever
    be written (run 31900072504).
    """
    root, private, public_text = _fixture_root(tmp_path, active=True)
    monkeypatch.setattr(
        rights,
        "PRODUCTION_TRUSTED_SIGNERS",
        {"receipt_rights_reviewer": (public_text, "rights_reviewer")},
    )
    _init_git_predecessor(root)
    receipt_identity.execute(
        today=NOW.date(),
        generated_at=NOW,
        root=root,
        path=root / receipt_identity.OUTPUT_RELATIVE,
        client=FakeClient(),
    )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "payload under profile A")

    profile_path = root / "governance/gdelt_receipt_identity_profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["activation"]["review_due"] = "2026-09-30"
    _write(profile_path, profile)
    signature = root / profile["activation"]["signature_path"]
    signature.write_bytes(private.sign(profile_path.read_bytes()))
    _git(root, "add", ".")
    _git(root, "commit", "-m", "profile B activation")
    tip = _git(root, "rev-parse", "HEAD")
    _git(root, "update-ref", "refs/remotes/origin/main", tip)

    snapshot = receipt_identity._load_predecessor(
        root=root,
        ref="HEAD",
        require_remote=True,
        exit_code=receipt_identity.EXIT_RIGHTS_BLOCKED,
    )
    assert snapshot.state == "present"
    assert snapshot.commit_sha == tip
    assert snapshot.payload is not None
    assert (
        snapshot.payload["profile_sha256"]
        != rights.load_profile_identity(root).profile_sha256
    )


def _superseded_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, date]:
    root, _, public_text = _fixture_root(tmp_path, active=True)
    monkeypatch.setattr(
        rights,
        "PRODUCTION_TRUSTED_SIGNERS",
        {"receipt_rights_reviewer": (public_text, "rights_reviewer")},
    )
    _init_git_predecessor(root)
    target = date.fromordinal(NOW.date().toordinal() - 1)
    return root, target


def test_superseded_verdict_passes_when_main_retains_everything_closed(
    tmp_path: Path, fixed_clock: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, target = _superseded_fixture(tmp_path, monkeypatch)
    output = root / receipt_identity.OUTPUT_RELATIVE
    payload = receipt_identity.execute(
        today=NOW.date(), generated_at=NOW, root=root, path=output,
        client=FakeClient()
    )
    assert payload["target_date"] == target.isoformat()
    _git(root, "add", receipt_identity.OUTPUT_RELATIVE.as_posix())
    _git(root, "commit", "-m", "partner release")
    _git(root, "update-ref", "refs/remotes/origin/main", _git(root, "rev-parse", "HEAD"))
    receipt_identity.verify_superseded(expected_target=target, root=root)


def test_superseded_verdict_refuses_when_main_is_missing_local_evidence(
    tmp_path: Path, fixed_clock: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, target = _superseded_fixture(tmp_path, monkeypatch)
    output = root / receipt_identity.OUTPUT_RELATIVE
    receipt_identity.execute(
        today=NOW.date(), generated_at=NOW, root=root, path=output,
        client=FakeClient(fail_on_call=1)
    )
    _git(root, "add", receipt_identity.OUTPUT_RELATIVE.as_posix())
    _git(root, "commit", "-m", "weaker partner release")
    _git(root, "update-ref", "refs/remotes/origin/main", _git(root, "rev-parse", "HEAD"))
    receipt_identity.execute(
        today=NOW.date(), generated_at=NOW, root=root, path=output,
        client=FakeClient()
    )
    with pytest.raises(receipt_identity.ReceiptIdentityRefusal) as exc:
        receipt_identity.verify_superseded(expected_target=target, root=root)
    assert exc.value.code == "receipt_identity_predecessor_channel_regression"


def test_superseded_verdict_refuses_when_main_never_released_the_target(
    tmp_path: Path, fixed_clock: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, target = _superseded_fixture(tmp_path, monkeypatch)
    output = root / receipt_identity.OUTPUT_RELATIVE
    receipt_identity.execute(
        today=NOW.date(), generated_at=NOW, root=root, path=output,
        client=FakeClient()
    )
    with pytest.raises(receipt_identity.ReceiptIdentityRefusal) as exc:
        receipt_identity.verify_superseded(expected_target=target, root=root)
    assert exc.value.code == "receipt_identity_superseded_remote_absent"
