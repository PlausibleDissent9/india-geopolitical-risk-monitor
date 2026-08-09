"""Denominator, count-unit and public-surface checks for the event ledger."""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import pytest
from src import event_ledger

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def _json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, str]], fields: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_public_artifact_fails_closed_until_signed_source_rights_exist() -> None:
    event_ledger.check()
    payload = event_ledger.build()
    assert payload["_meta"]["artifact_status"] == "public_release_blocked_rights_review"
    assert payload["_meta"]["partial"] is True
    assert payload["rights_gate"]["authorized"] is False
    assert set(payload["rights_gate"]["blocked_source_ids"]) == set(
        event_ledger.REQUIRED_PUBLIC_SOURCES
    )
    assert payload["frame"] is None
    assert payload["aggregate_historical_series"] is None
    assert payload["episodes"] is None
    assert all(
        row["public_available"] is False and row["value"] is None
        for row in payload["count_units"].values()
    )


def test_internal_candidate_recomputes_moving_counts_without_freezing_them() -> None:
    candidate = event_ledger._build_candidate()
    units = candidate["count_units"]
    expected = {
        "valid_layout_export_rows": 0,
        "india_involving_rows": 0,
        "verbal_conflict_rows": 0,
        "material_conflict_rows": 0,
        "protest_rows": 0,
        "mentions_sum": 0,
    }
    with event_ledger.DAILY_PATH.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    mapping = {
        "valid_layout_export_rows": "n_global",
        "india_involving_rows": "n_india",
        "verbal_conflict_rows": "n_verbal_conflict",
        "material_conflict_rows": "n_material_conflict",
        "protest_rows": "n_protest",
        "mentions_sum": "mentions_sum",
    }
    for output, source in mapping.items():
        expected[output] = sum(int(row[source]) for row in rows)
    assert units["aggregate_source_rows"]["counts"] == expected
    episodes = _json(event_ledger.EPISODES_PATH)
    assert isinstance(episodes, list)
    assert units["detected_salience_episodes"]["count"] == len(episodes)
    assert len(candidate["episodes"]) == len(episodes)
    assert all(row["object_type"] == "detected_salience_episode" for row in candidate["episodes"])
    assert all(row["canonical_event_ids"] is None for row in candidate["episodes"])


def test_calendar_and_country_denominators_partition_exactly() -> None:
    payload = event_ledger._build_candidate()
    frame = payload["frame"]
    replay = payload["aggregate_historical_series"]

    assert frame["start"] == "2017-01-01"
    observed_dates = {
        row["date"]
        for row in csv.DictReader(event_ledger.DAILY_PATH.open(encoding="utf-8"))
    }
    unavailable = _json(event_ledger.UNAVAILABLE_PATH)
    assert isinstance(unavailable, dict)
    missing_dates = set(unavailable["days"])
    assert frame["end"] == max(observed_dates)
    assert frame["observed_aggregate_days"] == len(observed_dates)
    assert frame["legacy_unavailable_days"] == len(missing_dates)
    assert frame["calendar_days"] == (
        frame["observed_aggregate_days"] + frame["legacy_unavailable_days"]
    )
    assert len(replay["dates"]) == frame["calendar_days"]
    assert len(replay["states"]) == frame["calendar_days"]
    assert replay["states"].count("legacy_unavailable_without_retrieval_receipt") == len(
        missing_dates
    )
    for index, status in enumerate(replay["states"]):
        if status == "legacy_unavailable_without_retrieval_receipt":
            assert replay["valid_layout_export_rows"][index] is None
            assert replay["india_involving_rows"][index] is None
    world = _json(event_ledger.WORLD_PATH)
    relations = _json(event_ledger.RELATIONS_PATH)
    assert isinstance(world, dict) and isinstance(relations, dict)
    assert frame["global_geometry_members"] == len(world["countries"])
    assert frame["eligible_external_partner_members"] == len(world["countries"]) - 1
    assert frame["partner_members_mapped"] == len(relations["partners"])
    assert frame["partner_members_not_applicable_self"] == 1
    assert frame["partner_coverage_share"] is None
    assert frame["eligible_external_partner_members"] == (
        frame["partner_members_mapped"]
        + frame["partner_members_not_observed_reason_unresolved"]
    )


def test_aggregate_subset_spoof_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = list(csv.DictReader(event_ledger.DAILY_PATH.open(encoding="utf-8")))
    rows[-1]["n_india"] = str(int(rows[-1]["n_global"]) + 1)
    path = tmp_path / "events_daily.csv"
    _write_csv(path, rows, event_ledger.DAILY_FIELDS)
    monkeypatch.setattr(event_ledger, "DAILY_PATH", path)

    with pytest.raises(event_ledger.EventLedgerError) as exc:
        event_ledger.build()
    assert exc.value.code == "daily_subset_constraint_invalid"


def test_unavailable_day_cannot_overlap_an_observed_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unavailable = _json(event_ledger.UNAVAILABLE_PATH)
    assert isinstance(unavailable, dict)
    unavailable["days"].append("2026-08-06")  # type: ignore[index, union-attr]
    path = tmp_path / "events_unavailable_days.json"
    _write_json(path, unavailable)
    monkeypatch.setattr(event_ledger, "UNAVAILABLE_PATH", path)

    with pytest.raises(event_ledger.EventLedgerError) as exc:
        event_ledger.build()
    assert exc.value.code == "calendar_state_overlap"


def test_grouped_store_must_cover_the_exact_same_dates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = list(csv.DictReader(event_ledger.DYADS_PATH.open(encoding="utf-8")))
    rows = [row for row in rows if row["date"] != "2026-08-06"]
    path = tmp_path / "events_dyads.csv"
    _write_csv(path, rows, event_ledger.DYAD_FIELDS)
    monkeypatch.setattr(event_ledger, "DYADS_PATH", path)

    with pytest.raises(event_ledger.EventLedgerError) as exc:
        event_ledger.build()
    assert exc.value.code == "dyad_date_frame_mismatch"


def test_grouped_store_duplicate_member_day_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = list(csv.DictReader(event_ledger.DYADS_PATH.open(encoding="utf-8")))
    rows.append(dict(rows[0]))
    path = tmp_path / "events_dyads.csv"
    _write_csv(path, rows, event_ledger.DYAD_FIELDS)
    monkeypatch.setattr(event_ledger, "DYADS_PATH", path)

    with pytest.raises(event_ledger.EventLedgerError) as exc:
        event_ledger._build_candidate()
    assert exc.value.code == "dyad_key_duplicate"


def test_partner_projection_must_recompute_from_the_dyad_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relations = _json(event_ledger.RELATIONS_PATH)
    assert isinstance(relations, dict)
    first = next(iter(relations["partners"].values()))
    first["n"] += 1
    path = tmp_path / "map_relations.json"
    _write_json(path, relations)
    monkeypatch.setattr(event_ledger, "RELATIONS_PATH", path)

    with pytest.raises(event_ledger.EventLedgerError) as exc:
        event_ledger._build_candidate()
    assert exc.value.code == "partner_projection_count_mismatch"


def test_duplicate_detector_episode_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    episodes = _json(event_ledger.EPISODES_PATH)
    assert isinstance(episodes, list)
    episodes.append(dict(episodes[0]))
    path = tmp_path / "episodes.json"
    _write_json(path, episodes)
    monkeypatch.setattr(event_ledger, "EPISODES_PATH", path)

    with pytest.raises(event_ledger.EventLedgerError) as exc:
        event_ledger.build()
    assert exc.value.code == "episode_id_duplicate"


def test_detector_window_stays_provisional_until_full_cluster_gap_is_observed() -> None:
    rows = [
        {
            "channel": "shipping",
            "start": "2026-08-06",
            "end": "2026-08-06",
            "peak_date": "2026-08-06",
            "peak_value": 1.0,
            "n_spike_days": 1,
            "label": "Test window",
        }
    ]
    provisional = event_ledger._validate_episodes(
        rows, date(2017, 1, 1), date(2026, 8, 8)
    )
    closed = event_ledger._validate_episodes(
        rows, date(2017, 1, 1), date(2026, 8, 9)
    )
    assert provisional[0]["lifecycle_state"] == "provisional_open_window"
    assert closed[0]["lifecycle_state"] == "detector_window_closed"


def test_contract_cannot_promote_unidentified_or_canonical_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = _json(event_ledger.CONTRACT_PATH)
    assert isinstance(contract, dict)
    contract["count_units"][1]["candidate_available"] = True  # type: ignore[index]
    path = tmp_path / "event_ledger_contract.json"
    _write_json(path, contract)
    monkeypatch.setattr(event_ledger, "CONTRACT_PATH", path)

    with pytest.raises(event_ledger.EventLedgerError) as exc:
        event_ledger.build()
    assert exc.value.code == "contract_digest_mismatch"


def test_public_page_and_javascript_fail_closed_on_the_same_boundaries() -> None:
    html = (DOCS / "ledger.html").read_text(encoding="utf-8")
    js = (DOCS / "ledger.js").read_text(encoding="utf-8")
    assert 'href="data/event_ledger.json"' in html
    assert "Static fallback is value-free" in html
    assert "fails closed unless" in html
    assert "No language model may promote" in html
    assert "Read the current machine artifact" in html
    assert "Static fallback carries no detector values" in html
    assert "Loading the exact detector set" not in html
    assert "Validating every represented and unavailable day" not in html
    assert "data-ledger-date" in html
    assert '"Aggregate frame through " + p.frame.end' in js
    assert 'payload._meta.artifact_status === "public_release_blocked_rights_review"' in js
    assert "payload.rights_gate.authorized !== false" in js
    assert 'payload.canonical_event_layer.model_promotion !== "prohibited"' in js
    assert '!sha256(meta.artifact_integrity_sha256)' in js
    assert '!utcSecond(meta.released_at)' in js
    assert '"Artifact-integrity SHA-256: "' in js
    assert "value !== null" in js
    assert "replaceChildren" in js
    assert "innerHTML" not in js


def test_ledger_is_wired_into_atlas_catalog_sitemap_api_and_pipeline() -> None:
    catalog = _json(ROOT / "design" / "public_product_catalog.json")
    assert isinstance(catalog, dict)
    routes = {row["path"] for row in catalog["routes"]}  # type: ignore[index]
    assert "ledger.html" in routes
    assert "ledger.html" in catalog["protected_routes"]  # type: ignore[operator]
    assert 'href="ledger.html"' in (DOCS / "atlas.html").read_text(encoding="utf-8")
    assert 'href="ledger.html"' in (DOCS / "products.html").read_text(encoding="utf-8")
    assert "https://igrm.in/ledger.html" in (DOCS / "sitemap.xml").read_text(encoding="utf-8")

    contract = _json(DOCS / "data" / "api_contract.json")
    assert isinstance(contract, dict)
    endpoints = {row["path"] for row in contract["endpoints"]}  # type: ignore[index]
    assert "data/event_ledger.json" in endpoints

    daily = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert daily.index("python -m src.world_state") < daily.index(
        "python -m src.run_daily"
    ) < daily.index("python -m src.event_ledger") < daily.index(
        "python -m src.evolution_engine --write"
    ) < daily.index("python -m src.stamp_meta")
    ledger_step = daily.split("- name: Global Event and Episode Ledger", 1)[1].split(
        "- name:", 1
    )[0]
    assert "continue-on-error: true" in ledger_step
    assert "python -m src.event_ledger --check" in ci


def test_public_copy_contains_no_world_event_census_or_score_claim() -> None:
    text = json.dumps(event_ledger.build()).lower()
    assert "a global event census" in text
    assert "a world risk, severity or probability score" in text
    assert "model_promotion\": \"prohibited" in text


def test_release_identity_binds_every_published_candidate_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = event_ledger._build_candidate()
    rows = list(csv.DictReader(event_ledger.DAILY_PATH.open(encoding="utf-8")))
    rows[0]["n_verbal_conflict"] = str(int(rows[0]["n_verbal_conflict"]) + 1)
    path = tmp_path / "events_daily.csv"
    _write_csv(path, rows, event_ledger.DAILY_FIELDS)
    monkeypatch.setattr(event_ledger, "DAILY_PATH", path)
    changed = event_ledger._build_candidate()
    assert changed["_meta"]["measurement_state_sha256"] != baseline["_meta"][
        "measurement_state_sha256"
    ]
    assert changed["aggregate_historical_series"]["verbal_conflict_rows"][0] != (
        baseline["aggregate_historical_series"]["verbal_conflict_rows"][0]
    )


def test_previously_observed_day_cannot_be_laundered_into_unavailable() -> None:
    candidate = event_ledger._build_candidate()
    rights = {"authorized": True, "snapshot": "test"}
    previous = event_ledger._authorized_public_artifact(
        candidate, rights, None, "2026-08-09T12:00:00Z"
    )
    changed = json.loads(json.dumps(candidate))
    series = changed["aggregate_historical_series"]
    index = series["states"].index("observed_aggregate")
    series["states"][index] = "legacy_unavailable_without_retrieval_receipt"
    for field in (
        "valid_layout_export_rows",
        "india_involving_rows",
        "india_involving_share_of_valid_layout_export_rows_pct",
        "verbal_conflict_rows",
        "material_conflict_rows",
        "protest_rows",
    ):
        series[field][index] = None
    with pytest.raises(event_ledger.EventLedgerError) as exc:
        event_ledger._release_delta(previous, changed)
    assert exc.value.code == "previously_observed_day_became_unavailable"


def test_frozen_candidate_baseline_refuses_removal_before_first_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = list(csv.DictReader(event_ledger.DAILY_PATH.open(encoding="utf-8")))
    path = tmp_path / "events_daily.csv"
    _write_csv(path, rows[:1] + rows[2:], event_ledger.DAILY_FIELDS)
    monkeypatch.setattr(event_ledger, "DAILY_PATH", path)

    with pytest.raises(event_ledger.EventLedgerError) as exc:
        event_ledger._build_candidate()
    assert exc.value.code == "candidate_baseline_observed_day_removed"


def test_agent_key_and_expired_human_review_cannot_authorize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = "test-public-key"
    signer = {
        "signer_id": "invented_agent_key",
        "name": "Invented signer",
        "role": "agent",
        "public_key_ed25519_base64": key,
        "effective": "2026-08-01",
        "revoked_on": None,
    }

    def sources_with(review_due: str) -> dict[str, dict[str, object]]:
        return {
            source_id: {
                "source_id": source_id,
                "decision_state": "approved",
                "decision_id": f"approved:{source_id}",
                "permitted_uses": sorted(event_ledger.REQUIRED_PUBLIC_USES),
                "signer_id": signer["signer_id"],
                "review_due": review_due,
                "decision_artifact_sha256": "a" * 64,
            }
            for source_id in event_ledger.REQUIRED_PUBLIC_SOURCES
        }

    monkeypatch.setattr(
        event_ledger.publication_guard,
        "_validate_signers",
        lambda document: {"invented_agent_key": signer},
    )
    monkeypatch.setattr(
        event_ledger.publication_guard,
        "_validate_rights_registry",
        lambda document, root, signers: sources_with("2099-12-31"),
    )
    assert event_ledger._rights_gate(date(2026, 8, 9))["authorized"] is False

    signer["role"] = "founder_rights_approver"
    monkeypatch.setattr(event_ledger, "TRUSTED_RIGHTS_SIGNERS", {"invented_agent_key": key})
    monkeypatch.setattr(
        event_ledger.publication_guard,
        "_validate_rights_registry",
        lambda document, root, signers: sources_with("2026-08-08"),
    )
    assert event_ledger._rights_gate(date(2026, 8, 9))["authorized"] is False


def test_authorized_archive_head_survives_blocked_status_and_detects_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = event_ledger._build_candidate()
    rights = {"authorized": True, "snapshot": "test"}
    release = event_ledger._authorized_public_artifact(
        candidate, rights, None, "2026-08-09T12:00:00Z"
    )
    vintage_dir = tmp_path / "vintages"
    vintage_dir.mkdir()
    release_id = release["_meta"]["release_id"]
    archive = vintage_dir / f"{release_id}.json"
    _write_json(archive, release)
    monkeypatch.setattr(event_ledger, "VINTAGE_DIR", vintage_dir)

    history = event_ledger._authorized_history()
    assert len(history) == 1
    same = event_ledger._authorized_public_artifact(candidate, rights, history[-1])
    assert same["_meta"]["vintage_number"] == 1
    assert same["release_lineage"]["predecessor_release_integrity_sha256"] is None

    tampered = json.loads(json.dumps(release))
    tampered["boundary"]["purpose"] = "forged purpose"
    _write_json(archive, tampered)
    with pytest.raises(event_ledger.EventLedgerError) as exc:
        event_ledger._authorized_history()
    assert exc.value.code == "authorized_release_integrity_invalid"
