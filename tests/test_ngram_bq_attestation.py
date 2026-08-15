"""Hostile tests for the BigQuery backfill attestation validator (3.0).

The 3.0 plane is admissible only for ledger-disclosed lost days, only with a
sealed exact-match equivalence proof, and only under the permanent
``bigquery_backfill`` regime label. Every test that relaxes one of those
constraints must see a typed refusal.
"""
from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from src import ngram_bq_attestation as bq

ROOT = Path(__file__).resolve().parents[1]
TARGET = date(2026, 8, 11)
PROOF_DAY = date(2026, 8, 9)


def _specs() -> dict[str, dict[str, Any]]:
    return {
        "g_alpha": {"channel": "pakistan_west", "phrases": ["alpha"]},
        "g_beta": {"channel": "shipping", "phrases": ["beta"]},
    }


def _provenance() -> dict[str, Any]:
    return {
        "table": "gdelt-bq.gdeltv2.webngrams",
        "query_text_sha256": "ab" * 32,
        "job_id": "igrm_backfill_20260811_0001",
        "job_created_utc": "2026-08-15T21:00:00Z",
        "total_bytes_processed": 123456789,
        "table_last_modified_utc": "2026-08-15T20:59:00Z",
    }


def _bindings(root: Path, specs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    canonical_specs = json.loads(bq.canonical_bytes(specs))
    return {
        "profile_sha256": bq.sha256((root / bq.PROFILE_RELATIVE).read_bytes()),
        "schema_sha256": bq.sha256((root / bq.SCHEMA_RELATIVE).read_bytes()),
        "dictionaries_sha256": bq.sha256((root / "dictionaries.json").read_bytes()),
        "production_matcher_sha256": bq.sha256(
            (root / "src/fetch_ngrams_bq.py").read_bytes()
        ),
        "validator_sha256": bq.sha256(
            (root / "src/ngram_bq_attestation.py").read_bytes()
        ),
        "calibration_sha256": "cd" * 32,
        "matcher_specs": canonical_specs,
        "matcher_specs_sha256": bq.sha256(bq.canonical_bytes(canonical_specs)),
    }


def _aggregate_sides(specs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    groups = sorted(specs)
    totals = {group: 480 * (index + 1) for index, group in enumerate(groups)}
    denominator = 48 * 1000
    shares = {
        group: round(100.0 * totals[group] / denominator, 6) for group in groups
    }
    channel_sums: dict[str, float] = {}
    for group in groups:
        channel = str(specs[group]["channel"])
        channel_sums[channel] = channel_sums.get(channel, 0.0) + shares[group]
    return {
        "english_denominator": denominator,
        "group_numerators": totals,
        "shares": shares,
        "channel_sums": channel_sums,
    }


def _proof(root: Path, specs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sides = _aggregate_sides(specs)
    return bq.seal(
        {
            "schema_version": "3.0.0",
            "profile_id": bq.PROFILE_ID,
            "kind": "bq_equivalence_proof",
            "day": PROOF_DAY.isoformat(),
            "published_reference": sides,
            "bq_recomputation": json.loads(json.dumps(sides)),
            "exact_match": True,
            "bq_provenance": _provenance(),
            "method_bindings": _bindings(root, specs),
        }
    )


def _root(tmp_path: Path, specs: dict[str, dict[str, Any]]) -> Path:
    root = tmp_path / "root"
    for relative in (bq.PROFILE_RELATIVE, bq.SCHEMA_RELATIVE):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    (root / "dictionaries.json").write_text('{"synthetic": true}', encoding="utf-8")
    matcher = root / "src/fetch_ngrams_bq.py"
    matcher.parent.mkdir(parents=True, exist_ok=True)
    matcher.write_text("# synthetic matcher fixture\n", encoding="utf-8")
    shutil.copy2(
        ROOT / "src/ngram_bq_attestation.py", root / "src/ngram_bq_attestation.py"
    )
    ledger = root / bq.REFUSAL_LEDGER_RELATIVE / f"{TARGET.isoformat()}.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "target_date": TARGET.isoformat(),
                "failure_stage": "source",
                "reason_code": "source_acquisition_failed",
                "status": "refused_value_free",
                "generated": "2026-08-12 06:20 IST",
            }
        ),
        encoding="utf-8",
    )
    proof_path = root / bq.EQUIVALENCE_RELATIVE / f"{PROOF_DAY.isoformat()}.json"
    proof_path.parent.mkdir(parents=True, exist_ok=True)
    proof_path.write_text(json.dumps(_proof(root, specs)), encoding="utf-8")
    return root


def _windows(specs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    groups = sorted(specs)
    rows = []
    for bucket in range(48):
        start = f"{TARGET.isoformat()}T{bucket // 2:02d}:{(bucket % 2) * 30:02d}:00Z"
        rows.append(
            {
                "bucket": bucket,
                "window_start_utc": start,
                "row_count": 250_000 + bucket,
                "english_denominator": 1000,
                "group_numerators": {
                    group: 10 * (index + 1) for index, group in enumerate(groups)
                },
            }
        )
    return rows


def _attestation(root: Path, specs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    proof = json.loads(
        (root / bq.EQUIVALENCE_RELATIVE / f"{PROOF_DAY.isoformat()}.json").read_text(
            encoding="utf-8"
        )
    )
    windows = _windows(specs)
    groups = sorted(specs)
    totals = {
        group: sum(row["group_numerators"][group] for row in windows)
        for group in groups
    }
    denominator = sum(row["english_denominator"] for row in windows)
    shares = {
        group: round(100.0 * totals[group] / denominator, 6) for group in groups
    }
    channel_sums: dict[str, float] = {}
    for group in groups:
        channel = str(specs[group]["channel"])
        channel_sums[channel] = channel_sums.get(channel, 0.0) + shares[group]
    return bq.seal(
        {
            "schema_version": "3.0.0",
            "profile_id": bq.PROFILE_ID,
            "day": TARGET.isoformat(),
            "acquisition_regime": "bigquery_backfill",
            "refusal_disclosure": {
                "ledger_path": (
                    bq.REFUSAL_LEDGER_RELATIVE / f"{TARGET.isoformat()}.json"
                ).as_posix(),
                "reason_code": "source_acquisition_failed",
            },
            "equivalence_binding": {
                "day": PROOF_DAY.isoformat(),
                "proof_path": (
                    bq.EQUIVALENCE_RELATIVE / f"{PROOF_DAY.isoformat()}.json"
                ).as_posix(),
                "proof_record_sha256": proof["record_sha256"],
            },
            "expected_windows": 48,
            "located_windows": 48,
            "loaded_windows": 48,
            "bq_provenance": _provenance(),
            "method_bindings": _bindings(root, specs),
            "windows": windows,
            "aggregate_reconstruction": {
                "window_order": list(range(48)),
                "english_denominator": denominator,
                "group_numerators": totals,
                "shares": shares,
                "channel_sums": channel_sums,
            },
            "membership_reproducibility": bq.MEMBERSHIP_LIMIT,
        }
    )


def _refuses(value: dict[str, Any], root: Path, code: str) -> None:
    with pytest.raises(bq.BqAttestationError) as excinfo:
        bq.validate(value, target=TARGET, specs=_specs(), root=root)
    assert excinfo.value.code == code


def test_valid_backfill_attestation_passes(tmp_path: Path) -> None:
    specs = _specs()
    root = _root(tmp_path, specs)
    result = bq.validate(
        _attestation(root, specs), target=TARGET, specs=specs, root=root
    )
    assert result["acquisition_regime"] == "bigquery_backfill"
    assert result["aggregate_reconstruction"]["english_denominator"] == 48 * 1000


def test_calibration_pin_is_enforced_when_supplied(tmp_path: Path) -> None:
    specs = _specs()
    root = _root(tmp_path, specs)
    attestation = _attestation(root, specs)
    bq.validate(
        attestation,
        target=TARGET,
        specs=specs,
        root=root,
        expected_calibration_sha256="cd" * 32,
    )
    with pytest.raises(bq.BqAttestationError) as excinfo:
        bq.validate(
            attestation,
            target=TARGET,
            specs=specs,
            root=root,
            expected_calibration_sha256="ef" * 32,
        )
    assert excinfo.value.code == "bq_attestation_calibration_mismatch"


def test_regime_label_day_and_seal_are_pinned(tmp_path: Path) -> None:
    specs = _specs()
    root = _root(tmp_path, specs)
    attestation = _attestation(root, specs)

    relabeled = dict(attestation)
    relabeled["acquisition_regime"] = "file_feed"
    _refuses(relabeled, root, "bq_attestation_profile_invalid")

    wrong_day = dict(attestation)
    wrong_day["day"] = "2026-08-12"
    _refuses(wrong_day, root, "bq_attestation_profile_invalid")

    tampered = dict(attestation)
    reconstruction = json.loads(json.dumps(tampered["aggregate_reconstruction"]))
    reconstruction["english_denominator"] += 1
    tampered["aggregate_reconstruction"] = reconstruction
    _refuses(tampered, root, "bq_attestation_seal_invalid")


def test_closed_root_schema_refuses_missing_and_extra_fields(tmp_path: Path) -> None:
    specs = _specs()
    root = _root(tmp_path, specs)
    attestation = _attestation(root, specs)

    missing = {
        key: value
        for key, value in attestation.items()
        if key != "equivalence_binding"
    }
    _refuses(missing, root, "bq_attestation_fields_invalid")

    extra = dict(attestation)
    extra["source_records"] = []
    _refuses(extra, root, "bq_attestation_fields_invalid")


def test_identity_leak_keys_refuse_anywhere(tmp_path: Path) -> None:
    specs = _specs()
    root = _root(tmp_path, specs)
    attestation = _attestation(root, specs)
    poisoned = json.loads(json.dumps(attestation))
    poisoned["bq_provenance"] = dict(poisoned["bq_provenance"])
    poisoned["bq_provenance"]["titles"] = ["leak"]
    poisoned = bq.seal(poisoned)
    _refuses(poisoned, root, "bq_attestation_identity_leak")


def test_refusal_ledger_is_load_bearing(tmp_path: Path) -> None:
    specs = _specs()
    root = _root(tmp_path, specs)
    attestation = _attestation(root, specs)

    ledger_path = root / bq.REFUSAL_LEDGER_RELATIVE / f"{TARGET.isoformat()}.json"
    original = ledger_path.read_text(encoding="utf-8")

    ledger_path.unlink()
    _refuses(attestation, root, "bq_attestation_refusal_ledger_missing")

    ledger = json.loads(original)
    ledger["failure_stage"] = "gate"
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    _refuses(attestation, root, "bq_attestation_refusal_ledger_mismatch")

    ledger_path.write_text(original, encoding="utf-8")
    bq.validate(attestation, target=TARGET, specs=specs, root=root)


def test_equivalence_proof_is_load_bearing_and_exact(tmp_path: Path) -> None:
    specs = _specs()
    root = _root(tmp_path, specs)
    attestation = _attestation(root, specs)
    proof_path = root / bq.EQUIVALENCE_RELATIVE / f"{PROOF_DAY.isoformat()}.json"
    original = proof_path.read_text(encoding="utf-8")

    proof_path.unlink()
    _refuses(attestation, root, "bq_attestation_equivalence_proof_missing")

    drifted = json.loads(original)
    recomputed = dict(drifted["bq_recomputation"])
    recomputed["english_denominator"] += 1
    drifted["bq_recomputation"] = recomputed
    proof_path.write_text(json.dumps(bq.seal(drifted)), encoding="utf-8")
    _refuses(attestation, root, "bq_equivalence_proof_not_exact")

    exact_but_rebound = json.loads(original)
    exact_but_rebound["exact_match"] = False
    proof_path.write_text(
        json.dumps(bq.seal(exact_but_rebound)), encoding="utf-8"
    )
    _refuses(attestation, root, "bq_equivalence_proof_not_exact")

    proof_path.write_text(original, encoding="utf-8")
    binding = dict(attestation["equivalence_binding"])
    binding["day"] = TARGET.isoformat()
    self_referential = dict(attestation)
    self_referential["equivalence_binding"] = binding
    self_referential = bq.seal(self_referential)
    _refuses(self_referential, root, "bq_attestation_equivalence_binding_invalid")


def test_provenance_shape_is_closed(tmp_path: Path) -> None:
    specs = _specs()
    root = _root(tmp_path, specs)
    attestation = _attestation(root, specs)
    for mutation in (
        {"table": "gdelt-bq.gdeltv2.events"},
        {"query_text_sha256": "zz" * 32},
        {"job_id": ""},
        {"job_created_utc": "2026-08-15 21:00:00"},
        {"total_bytes_processed": -1},
    ):
        mutated = json.loads(json.dumps(attestation))
        mutated["bq_provenance"] = {**mutated["bq_provenance"], **mutation}
        mutated = bq.seal(mutated)
        _refuses(mutated, root, "bq_attestation_provenance_invalid")


def test_bound_sources_and_specs_are_pinned(tmp_path: Path) -> None:
    specs = _specs()
    root = _root(tmp_path, specs)
    attestation = _attestation(root, specs)

    (root / "dictionaries.json").write_text('{"synthetic": 2}', encoding="utf-8")
    _refuses(attestation, root, "bq_attestation_bound_source_mismatch")
    (root / "dictionaries.json").write_text('{"synthetic": true}', encoding="utf-8")

    with pytest.raises(bq.BqAttestationError) as excinfo:
        bq.validate(
            attestation,
            target=TARGET,
            specs={**specs, "g_gamma": {"channel": "shipping", "phrases": ["g"]}},
            root=root,
        )
    assert excinfo.value.code == "bq_attestation_specs_mismatch"


def test_window_discipline(tmp_path: Path) -> None:
    specs = _specs()
    root = _root(tmp_path, specs)

    def mutate(index: int, **changes: Any) -> dict[str, Any]:
        attestation = json.loads(json.dumps(_attestation(root, specs)))
        window = dict(attestation["windows"][index])
        window.update(changes)
        attestation["windows"][index] = window
        return bq.seal(attestation)

    _refuses(mutate(0, bucket=1), root, "bq_attestation_window_order_invalid")
    _refuses(
        mutate(0, window_start_utc=f"{TARGET.isoformat()}T00:15:00Z"),
        root,
        "bq_attestation_window_start_invalid",
    )
    _refuses(
        mutate(0, window_start_utc="2026-08-12T00:00:00Z"),
        root,
        "bq_attestation_window_start_invalid",
    )
    _refuses(mutate(0, row_count=0), root, "bq_attestation_row_count_invalid")
    _refuses(
        mutate(0, english_denominator=0), root, "bq_attestation_denominator_invalid"
    )
    _refuses(
        mutate(0, group_numerators={"g_alpha": 2000, "g_beta": 20}),
        root,
        "bq_attestation_numerator_invalid",
    )

    truncated = json.loads(json.dumps(_attestation(root, specs)))
    truncated["windows"] = truncated["windows"][:47]
    truncated["located_windows"] = 48
    truncated = bq.seal(truncated)
    _refuses(truncated, root, "bq_attestation_window_count_invalid")


def test_reconstruction_must_match_window_arithmetic(tmp_path: Path) -> None:
    specs = _specs()
    root = _root(tmp_path, specs)
    attestation = json.loads(json.dumps(_attestation(root, specs)))
    reconstruction = dict(attestation["aggregate_reconstruction"])
    shares = dict(reconstruction["shares"])
    first = sorted(shares)[0]
    shares[first] = round(shares[first] + 0.000001, 6)
    reconstruction["shares"] = shares
    attestation["aggregate_reconstruction"] = reconstruction
    attestation = bq.seal(attestation)
    _refuses(attestation, root, "bq_attestation_reconstruction_invalid")
