"""Focused fail-closed tests for the visitor-visible D-1 final contract."""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Callable

import pandas as pd
import pytest
import requests
from src import fetch_gdelt, fetch_ngrams, final_publication, run_daily

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 8, 10)
TARGET = date(2026, 8, 9)
PREFIX_DAY = date(2026, 8, 8)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stamp(index: int) -> str:
    minute = index * 30
    return f"{TARGET:%Y%m%d}{minute // 60:02d}{minute % 60:02d}00"


def _specs() -> dict[str, dict]:
    return {
        "pakistan_west/q1": {
            "channel": "pakistan_west",
            "anchor": "india",
            "phrases": [("border",)],
        }
    }


def _complete_result(root: Path) -> dict:
    stamps = [_stamp(index) for index in range(48)]
    keys = [f"{stamps[0]}:A", f"{stamps[1]}:B"]
    canonical_specs = fetch_ngrams._canonical_specs(_specs())
    return {
        "date": TARGET.isoformat(),
        "n_docs_sampled": 100,
        "n_samples": 48,
        "n_samples_loaded": 48,
        "partial": False,
        "shares": {"pakistan_west/q1": 2.0},
        "_matcher_evidence": {
            "schema_version": "1.0.0",
            "day": TARGET.isoformat(),
            "located_stamps": stamps,
            "loaded_stamps": stamps,
            "missing_stamps": [],
            "matcher_specs": canonical_specs,
            "matcher_specs_sha256": _sha(
                json.dumps(
                    canonical_specs, sort_keys=True, separators=(",", ":")
                ).encode()
            ),
            "dictionaries_sha256": _sha((root / "dictionaries.json").read_bytes()),
            "production_matcher_sha256": _sha(
                (root / "src/fetch_ngrams.py").read_bytes()
            ),
            "india_document_keys": keys,
            "matched_document_keys": {"pakistan_west/q1": keys},
            "article_meta": {
                key: {
                    "date": f"{TARGET:%Y%m%d}",
                    "title": f"Eligible article {index}",
                    "url": f"https://example.test/{index}",
                }
                for index, key in enumerate(keys)
            },
        },
    }


def _publication_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "data/raw").mkdir(parents=True)
    (root / "docs/data").mkdir(parents=True)
    dictionary = {
        "pakistan_west": {
            "label": "Pakistan / western border",
            "terms": ['"border"'],
            "anchor": "india",
        }
    }
    (root / "dictionaries.json").write_text(
        json.dumps(dictionary) + "\n", encoding="utf-8"
    )
    (root / "src/fetch_ngrams.py").write_text(
        "# exact matcher fixture\n", encoding="utf-8"
    )
    (root / "data/raw/gdelt_volume.csv").write_text(
        "date,pakistan_west\n2026-08-08,0.25\n", encoding="utf-8"
    )
    (root / "data/raw/provenance.csv").write_text(
        "date,source,basis\n2026-08-08,ngram_bridge,recorded\n",
        encoding="utf-8",
    )
    (root / "data/raw/ngram_calibration.json").write_text(
        json.dumps({"pakistan_west": {"ratio": 2.0, "n_days": 5}}) + "\n",
        encoding="utf-8",
    )
    (root / "docs/data/latest.json").write_text(
        json.dumps({"date": PREFIX_DAY.isoformat()}) + "\n", encoding="utf-8"
    )
    (root / "docs/data/status.json").write_text(
        json.dumps({"_meta": {"generated": "2026-08-09T00:00:00Z"}}) + "\n",
        encoding="utf-8",
    )
    (root / "docs/index.html").write_text(
        "<!--final-publication-static:start-->old"
        "<!--final-publication-static:end-->",
        encoding="utf-8",
    )
    (root / "docs/status.html").write_text(
        "<!--final-publication-status-static:start-->old"
        "<!--final-publication-status-static:end-->",
        encoding="utf-8",
    )
    return root


def _acquire(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    result: dict | None,
) -> dict:
    monkeypatch.setattr(fetch_ngrams, "group_specs", _specs)
    return final_publication.acquire_target(
        TARGET,
        today=TODAY,
        root=root,
        base_commit="a" * 40,
        compute_day=lambda _day, _specs_arg: result,
    )


def test_exact_d_minus_one_complete_frame_promotes_target_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _publication_root(tmp_path)
    store_prefix = (root / "data/raw/gdelt_volume.csv").read_bytes()
    provenance_prefix = (root / "data/raw/provenance.csv").read_bytes()

    status = _acquire(root, monkeypatch, _complete_result(root))

    assert status["status"] == "target_ready"
    store = (root / "data/raw/gdelt_volume.csv").read_bytes()
    provenance = (root / "data/raw/provenance.csv").read_bytes()
    assert store.startswith(store_prefix)
    assert provenance.startswith(provenance_prefix)
    assert store.decode().splitlines()[-1] == "2026-08-09,1.0"
    assert provenance.decode().splitlines()[-1] == (
        "2026-08-09,ngram_bridge,recorded"
    )
    assert "2026-08-10" not in store.decode()
    receipt = final_publication.require_promotion_receipt(
        TARGET, root=root, require_bridge_receipt=True
    )
    assert receipt is not None
    assert receipt["frame"]["n_samples_located"] == 48
    assert receipt["frame"]["n_samples_loaded"] == 48
    assert receipt["append_contract"]["old_prefix_equal"] is True
    assert receipt["append_contract"]["d0_excluded"] is True
    assert set(receipt["bindings"]) == {
        "calibration_sha256",
        "calibration_records_sha256",
        "dictionary_sha256",
        "matcher_sha256",
        "matcher_specs_sha256",
        "candidate_row_sha256",
    }


@pytest.mark.parametrize(
    ("result_factory", "expected_state"),
    [
        (lambda _root: None, "source_unavailable"),
        (
            lambda root: {
                **_complete_result(root),
                "n_samples": 1,
                "n_samples_loaded": 1,
                "_matcher_evidence": {
                    **_complete_result(root)["_matcher_evidence"],
                    "located_stamps": [_stamp(0)],
                    "loaded_stamps": [_stamp(0)],
                },
            },
            "acquisition_failed",
        ),
    ],
)
def test_refusal_discloses_typed_state_without_banking_candidate_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    result_factory: Callable[[Path], dict | None],
    expected_state: str,
) -> None:
    root = _publication_root(tmp_path)
    value_paths = [
        root / "data/raw/gdelt_volume.csv",
        root / "data/raw/provenance.csv",
    ]
    before = {path: path.read_bytes() for path in value_paths}

    result = result_factory(root)
    status = _acquire(root, monkeypatch, result)

    assert status["status"] == expected_state
    assert status["value_fields_published"] is False
    assert status["provisional_substitution_allowed"] is False
    assert {path: path.read_bytes() for path in value_paths} == before
    assert not (root / f"data/raw/ngram_days/{TARGET}.json").exists()
    assert not (root / f"data/raw/final_publication_receipts/{TARGET}.json").exists()


@pytest.mark.parametrize("shape", ["47_of_47", "48_of_47", "partial_true"])
def test_every_incomplete_frame_shape_refuses_without_canonical_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    shape: str,
) -> None:
    root = _publication_root(tmp_path)
    result = _complete_result(root)
    evidence = result["_matcher_evidence"]
    if shape == "47_of_47":
        result["n_samples"] = 47
        result["n_samples_loaded"] = 47
        evidence["located_stamps"] = evidence["located_stamps"][:-1]
        evidence["loaded_stamps"] = evidence["loaded_stamps"][:-1]
    elif shape == "48_of_47":
        result["n_samples_loaded"] = 47
        evidence["loaded_stamps"] = evidence["loaded_stamps"][:-1]
        evidence["missing_stamps"] = [evidence["located_stamps"][-1]]
    else:
        result["partial"] = True
    store_before = (root / "data/raw/gdelt_volume.csv").read_bytes()
    provenance_before = (root / "data/raw/provenance.csv").read_bytes()

    status = _acquire(root, monkeypatch, result)

    assert status["status"] == "acquisition_failed"
    assert (root / "data/raw/gdelt_volume.csv").read_bytes() == store_before
    assert (root / "data/raw/provenance.csv").read_bytes() == provenance_before
    assert not (root / f"data/raw/ngram_days/{TARGET}.json").exists()


def test_typed_network_classification_distinguishes_404_from_transport_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Response:
        def __init__(self, status: int) -> None:
            self.status_code = status

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise requests.HTTPError(str(self.status_code))

    unavailable_root = _publication_root(tmp_path / "unavailable")
    monkeypatch.setattr(fetch_ngrams, "group_specs", _specs)
    monkeypatch.setattr(
        fetch_ngrams.requests,
        "head",
        lambda *_args, **_kwargs: Response(404),
    )
    monkeypatch.setattr(
        fetch_ngrams,
        "_day_minute_files",
        lambda *_args, **_kwargs: (
            []
            if fetch_ngrams._probe_window(TARGET, 0, 2) is None
            else pytest.fail("404 source unexpectedly located")
        ),
    )

    unavailable = final_publication.acquire_target(
        TARGET,
        today=TODAY,
        root=unavailable_root,
        compute_day=fetch_ngrams.compute_day,
    )

    failed_root = _publication_root(tmp_path / "failed")
    monkeypatch.setattr(
        fetch_ngrams.requests,
        "head",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            requests.Timeout("timed out")
        ),
    )
    failed = final_publication.acquire_target(
        TARGET,
        today=TODAY,
        root=failed_root,
        compute_day=fetch_ngrams.compute_day,
    )

    assert unavailable["status"] == "source_unavailable"
    assert failed["status"] == "acquisition_failed"
    assert "NgramAcquisitionError" in failed["reason"]


def test_typed_network_classification_treats_5xx_as_acquisition_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Response:
        status_code = 503

        @staticmethod
        def raise_for_status() -> None:
            raise requests.HTTPError("503")

    root = _publication_root(tmp_path)
    monkeypatch.setattr(fetch_ngrams, "group_specs", _specs)
    monkeypatch.setattr(
        fetch_ngrams.requests,
        "head",
        lambda *_args, **_kwargs: Response(),
    )

    status = final_publication.acquire_target(
        TARGET,
        today=TODAY,
        root=root,
        compute_day=lambda *_args: (
            None
            if fetch_ngrams._probe_window(TARGET, 0, 2) is None
            else pytest.fail("5xx source unexpectedly located")
        ),
    )

    assert status["status"] == "acquisition_failed"


def test_already_finalized_is_typed_and_does_not_reacquire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _publication_root(tmp_path)
    (root / "docs/data/latest.json").write_text(
        json.dumps({"date": TARGET.isoformat()}), encoding="utf-8"
    )
    monkeypatch.setattr(fetch_ngrams, "group_specs", _specs)

    status = final_publication.acquire_target(
        TARGET,
        today=TODAY,
        root=root,
        compute_day=lambda *_args: pytest.fail("already-finalized target reacquired"),
    )

    assert status["status"] == "already_finalized"


def test_receipt_revalidation_refuses_bound_input_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _publication_root(tmp_path)
    assert _acquire(root, monkeypatch, _complete_result(root))["status"] == "target_ready"
    calibration = root / "data/raw/ngram_calibration.json"
    calibration.write_text(
        json.dumps({"pakistan_west": {"ratio": 3.0, "n_days": 5}}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        final_publication.FinalPublicationError,
        match="^promotion_receipt_invalid$",
    ):
        final_publication.require_promotion_receipt(
            TARGET, root=root, require_bridge_receipt=True
        )


def test_cached_ineligible_day_cannot_stick_or_override_fresh_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _publication_root(tmp_path)
    cache = root / f"data/raw/ngram_days/{TARGET}.json"
    cache.parent.mkdir(parents=True)
    ineligible = _complete_result(root)
    ineligible["partial"] = True
    cache.write_text(json.dumps(ineligible), encoding="utf-8")

    status = _acquire(root, monkeypatch, _complete_result(root))

    assert status["status"] == "target_ready"
    banked = json.loads(cache.read_text(encoding="utf-8"))
    assert banked["partial"] is False
    assert banked["n_samples"] == 48


def test_daily_guard_requires_exact_d_minus_one_and_excludes_d0(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    days = pd.date_range("2025-01-01", TARGET)
    complete = pd.DataFrame({"pakistan_west": 1.0}, index=days)
    monkeypatch.setattr(run_daily, "SITE_DATA", Path("/path/that/does/not/exist"))

    accepted = run_daily._fail_loudly_on_partial_data(complete, TARGET)
    assert accepted.index.max().date() == TARGET

    with pytest.raises(SystemExit, match="exact D-1 target"):
        run_daily._fail_loudly_on_partial_data(complete.iloc[:-1], TARGET)

    with_d0 = pd.concat(
        [
            complete,
            pd.DataFrame(
                {"pakistan_west": [999.0]}, index=[pd.Timestamp(TODAY)]
            ),
        ]
    )
    with pytest.raises(SystemExit, match="rows after exact final target"):
        run_daily._fail_loudly_on_partial_data(with_d0, TARGET)


def test_target_nulls_and_null_composites_refuse_before_site_write() -> None:
    index = pd.to_datetime([TARGET])
    daily = pd.DataFrame(
        {"pakistan_west": [1.0], "composite": [1.0]}, index=index
    )
    headline = daily.copy()
    headline.loc[index[0], "composite"] = float("nan")
    with pytest.raises(SystemExit, match="headline target"):
        run_daily._require_exact_target_scores(daily, headline, TARGET)

    daily.loc[index[0], "pakistan_west"] = float("nan")
    with pytest.raises(SystemExit, match="daily target score row contains nulls"):
        run_daily._require_exact_target_scores(daily, daily.fillna(1.0), TARGET)


def test_written_latest_and_history_must_end_at_finite_target(tmp_path: Path) -> None:
    site = tmp_path / "docs/data"
    site.mkdir(parents=True)
    latest = {
        "date": TARGET.isoformat(),
        "composite": 50.0,
        "composite7": 51.0,
    }
    history = {"dates": [PREFIX_DAY.isoformat(), TARGET.isoformat()], "composite": [49.0, 50.0]}
    (site / "latest.json").write_text(json.dumps(latest), encoding="utf-8")
    (site / "history.json").write_text(json.dumps(history), encoding="utf-8")

    run_daily._require_written_target(TARGET, site_data=site)

    latest["composite"] = None
    (site / "latest.json").write_text(json.dumps(latest), encoding="utf-8")
    with pytest.raises(SystemExit, match="null or non-finite"):
        run_daily._require_written_target(TARGET, site_data=site)

    latest["composite"] = 50.0
    history["dates"][-1] = TODAY.isoformat()
    (site / "latest.json").write_text(json.dumps(latest), encoding="utf-8")
    (site / "history.json").write_text(json.dumps(history), encoding="utf-8")
    with pytest.raises(SystemExit, match="do not end at exact D-1"):
        run_daily._require_written_target(TARGET, site_data=site)


def test_provisional_payload_never_launders_a_missing_final(tmp_path: Path) -> None:
    root = _publication_root(tmp_path)
    (root / "docs/data/nowcast.json").write_text(
        json.dumps(
            {"date": TODAY.isoformat(), "provisional": True, "composite": 99.9}
        ),
        encoding="utf-8",
    )

    status = final_publication.public_status(root=root, today=TODAY)

    assert status["status"] == "delayed_final"
    assert status["latest_finalized_date"] == PREFIX_DAY.isoformat()
    assert status["finalized"] is False
    assert status["provisional_substitution_allowed"] is False
    assert "composite" not in status


def test_public_refusal_status_is_value_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _publication_root(tmp_path)
    marker = _acquire(root, monkeypatch, None)
    public = final_publication.public_status(root=root, today=TODAY)

    value_keys = {"composite", "composite7", "score", "score7", "channels", "shares"}

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {key for nested in value.values() for key in keys(nested)}
        if isinstance(value, list):
            return {key for nested in value for key in keys(nested)}
        return set()

    assert value_keys.isdisjoint(keys(marker))
    assert value_keys.isdisjoint(keys(public))
    assert marker["value_fields_published"] is False
    assert public["value_fields_published"] is False


def test_failed_pipeline_disclosure_uses_published_prefix_not_dirty_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _publication_root(tmp_path)
    assert _acquire(root, monkeypatch, _complete_result(root))["status"] == "target_ready"
    # Simulate run_daily having written an uncommitted candidate latest.json
    # before a later audit/gate refused publication.
    (root / "docs/data/latest.json").write_text(
        json.dumps({"date": TARGET.isoformat(), "composite": 99.9}),
        encoding="utf-8",
    )
    store_before = (root / "data/raw/gdelt_volume.csv").read_bytes()
    provenance_before = (root / "data/raw/provenance.csv").read_bytes()

    marker = final_publication.record_pipeline_failed(
        TARGET, root=root, base_commit="a" * 40
    )
    public = final_publication.write_public_status(root=root, today=TODAY)

    assert marker["status"] == "pipeline_failed"
    assert marker["latest_finalized_date"] == PREFIX_DAY.isoformat()
    assert public["status"] == "pipeline_failed"
    assert public["latest_finalized_date"] == PREFIX_DAY.isoformat()
    assert public["finalized"] is False
    assert "composite" not in public
    assert (root / "data/raw/gdelt_volume.csv").read_bytes() == store_before
    assert (root / "data/raw/provenance.csv").read_bytes() == provenance_before
    for path in (root / "docs/index.html", root / "docs/status.html"):
        text = path.read_text(encoding="utf-8")
        assert "publication validation failed" in text
        assert TARGET.isoformat() in text
        assert PREFIX_DAY.isoformat() in text


def test_refusal_ignores_unpushed_finalized_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _publication_root(tmp_path / "candidate")
    assert _acquire(candidate, monkeypatch, _complete_result(candidate))["status"] == "target_ready"
    (candidate / "docs/data/latest.json").write_text(
        json.dumps({"date": TARGET.isoformat(), "composite": 99.9}),
        encoding="utf-8",
    )
    finalized = final_publication.mark_finalized(TARGET, root=candidate)
    assert finalized["latest_finalized_date"] == TARGET.isoformat()

    # The workflow constructs disclosure from the frozen parent and copies
    # only the operational marker. The unpushed candidate date must not cross
    # that boundary when a later audit/derived step fails.
    refusal = _publication_root(tmp_path / "refusal")
    (refusal / final_publication.STATUS_RELATIVE).write_text(
        (candidate / final_publication.STATUS_RELATIVE).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    marker = final_publication.record_pipeline_failed(
        TARGET, root=refusal, base_commit="a" * 40, failure_stage="audit"
    )

    assert marker["status"] == "pipeline_failed"
    assert marker["latest_finalized_date"] == PREFIX_DAY.isoformat()


def test_hard_source_step_failure_is_typed_acquisition_failed(tmp_path: Path) -> None:
    root = _publication_root(tmp_path)

    marker = final_publication.record_pipeline_failed(
        TARGET, root=root, base_commit="a" * 40, failure_stage="source"
    )

    assert marker["status"] == "acquisition_failed"
    assert marker["latest_finalized_date"] == PREFIX_DAY.isoformat()
    assert marker["value_fields_published"] is False


def test_gdelt_target_vintage_preserves_old_prefix_and_excludes_d0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    store = raw / "gdelt_volume.csv"
    store.write_text(
        "date,pakistan_west\n2026-08-08,0.25\n", encoding="utf-8"
    )
    monkeypatch.setattr(fetch_gdelt, "RAW_DIR", raw)
    observed: list[tuple[date, date]] = []

    def fetch(_dictionary: dict, start: date, end: date) -> pd.DataFrame:
        observed.append((start, end))
        return pd.DataFrame(
            {"pakistan_west": [1.0]}, index=pd.Index([TARGET], name="date")
        )

    monkeypatch.setattr(fetch_gdelt, "fetch_all", fetch)
    result = fetch_gdelt.load_or_update(
        {"pakistan_west": {}},
        end_date=TARGET,
        immutable_through=PREFIX_DAY,
    )

    assert observed == [(TARGET, TARGET)]
    assert result.loc[PREFIX_DAY, "pakistan_west"] == 0.25
    assert result.loc[TARGET, "pakistan_west"] == 1.0
    assert TODAY not in result.index

    store.write_text(
        "date,pakistan_west\n2026-08-08,0.25\n2026-08-10,9.0\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="D0/future"):
        fetch_gdelt.load_or_update(
            {"pakistan_west": {}},
            end_date=TARGET,
            immutable_through=PREFIX_DAY,
        )


def test_morning_gate_is_bounded_once_per_candidate_and_cas_only() -> None:
    workflow = (ROOT / ".github/workflows/morning.yml").read_text(encoding="utf-8")
    assert (
        "python -m pytest -q tests/test_dictionaries.py "
        "tests/test_registration_freezes.py"
    ) in workflow
    assert "python -m pytest -q\n" not in workflow
    assert "bash scripts/publish_push.sh" not in workflow
    assert workflow.count("bash scripts/gate.sh --committed") == 2
    assert 'REMOTE_COMMIT=$(git rev-parse origin/main)' in workflow
    assert workflow.count('git push origin HEAD:main') == 1
    assert "/usr/bin/time -v" in workflow
    assert "git worktree add --detach" in workflow
    publish_lane = workflow.split(
        "- name: Gate and CAS-publish final or value-free refusal", 1
    )[1]
    refusal_function = publish_lane.split("publish_refusal()", 1)[1]
    assert "id: publish" in publish_lane
    assert "git add data/raw/final_publication_status.json docs/data/status.json" in refusal_function
    assert "failure disclosure attempted to stage candidate value bytes" in refusal_function
    assert '--failure-stage "$FAILURE_STAGE"' in refusal_function
    assert "FAILURE_STAGE=source" in refusal_function
    assert "steps.pipeline.outcome == 'success'" in workflow
    assert "steps.audit.outcome == 'success'" in workflow
    assert '${{ steps.derived.outcome }}" = "success"' in workflow
    success_dispatch = publish_lane.rsplit(
        'if [ "${{ steps.source.outcome }}" = "success" ]', 1
    )[1]
    assert "if publish_final; then" in success_dispatch
    assert "publish_refusal" not in success_dispatch.split("fi", 1)[0]
    for command in (
        "timeout --signal=TERM 14m python -m src.final_publication",
        "timeout --signal=TERM 7m python -m src.run_daily --final-only",
        "timeout --signal=TERM 2m python -m src.audit",
        "timeout --signal=TERM 5m bash -c",
    ):
        assert command in workflow
    assert "timeout --signal=TERM 27m" not in workflow
    assert "CI #533 (run 31360365274)" in workflow
    assert "36m42s" in workflow and "24m55s" in workflow
    assert "0.687s locally" in workflow and "run #43" in workflow
    assert "availability boundary" in workflow


def test_rescue_predicates_and_public_pages_use_final_date_contract() -> None:
    for relative in (
        ".github/workflows/nowcast.yml",
        ".github/workflows/watchdog.yml",
    ):
        workflow = (ROOT / relative).read_text(encoding="utf-8")
        assert "['date']" in workflow
        assert "['_meta']['generated']" not in workflow
        assert 'date -u -d "yesterday" +%F' in workflow

    homepage = (ROOT / "docs/index.html").read_text(encoding="utf-8")
    app = (ROOT / "docs/app.js").read_text(encoding="utf-8")
    status_page = (ROOT / "docs/status.html").read_text(encoding="utf-8")
    assert 'id="final-publication-status"' in homepage
    assert 'id="final-publication-status" hidden' not in homepage
    assert "exact D-1 target <b>2026-08-09</b>" in homepage
    assert "latest finalized measure remains <b>2026-08-08</b>" in homepage
    assert "A provisional nowcast is not a substitute" in app
    assert "exact D-1 target <b>2026-08-09</b>" in status_page
    assert "A provisional nowcast is not a substitute" in status_page
