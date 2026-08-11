"""Deterministic public conformance vector for the four-output engine.

The fixture uses the OGES synthetic release and public test-only signing keys.
It contains no real event, entity, source, right, exposure or recommendation.
The committed JSON and ZIP are rebuilt from the same production compiler used
by the CLI; they are a structural test vector, not a claim that a real-data
output pipeline is operational.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from src import oges_fixture

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_OUTPUT = ROOT / "docs" / "data" / "evidence_outputs_demo.json"
PUBLIC_ARCHIVE = ROOT / "docs" / "downloads" / "igrm-evidence-outputs-demo.zip"

_EVENT_ID = "evt:oges.fixture.policy.001"
_TARGET_ID = "ent:commodity.synthetic_crude"


def _install_contract(root: Path) -> None:
    copies = (
        ("src/evidence_outputs.py", "src/evidence_outputs.py"),
        ("src/exposure_graph.py", "src/exposure_graph.py"),
        (
            "governance/evidence_output_registry.json",
            "governance/evidence_output_registry.json",
        ),
        (
            "governance/exposure_projection_registry.json",
            "governance/exposure_projection_registry.json",
        ),
        (
            "schemas/evidence-output-set.schema.json",
            "schemas/evidence-output-set.schema.json",
        ),
    )
    for source, destination in copies:
        target = root / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source, target)


def build_fixture(destination: Path) -> oges_fixture.Fixture:
    """Build one signed OGES fixture with the output contract installed."""

    fixture = oges_fixture.build_fixture(destination)
    _install_contract(fixture.root)
    return fixture


def build_demo_artifacts() -> tuple[dict[str, Any], bytes]:
    """Return the public artifacts from the one composed Max fixture world."""

    # Local import avoids a module cycle: the composed fixture installs this
    # module's contract, then publishes every engine record it actually joins.
    from src import max_state_join_fixture

    artifacts = max_state_join_fixture.build_published_artifacts()
    return artifacts.evidence_outputs, artifacts.evidence_archive


def _build_demo_payload(
    output_set: dict[str, Any], archive: bytes
) -> dict[str, Any]:
    """Wrap one already-compiled output without rebuilding a private world."""

    archive_sha = hashlib.sha256(archive).hexdigest()
    described = output_set["outputs"]["offline_audit_bundle"]["artifact"]
    if archive_sha != described["sha256"] or len(archive) != described["bytes"]:
        raise RuntimeError("demo_archive_descriptor_mismatch")
    payload = {
        "_meta": {
            "schema": "igrm-evidence-outputs-demo-v1",
            "generated": "2026-08-08T13:00:00Z",
            "date": "2026-08-08",
            "what": (
                "Deterministic synthetic demonstration of one signed evidence "
                "release producing a research package, board-brief draft, newsroom "
                "claim card and offline audit bundle from identical registered facts."
            ),
            "scope": "synthetic_test_vector_only",
            "production_release": False,
            "real_event_entity_source_right_exposure_or_adoption_claims": False,
            "model_generated_facts_numbers_dates_citations_or_confidence": False,
            "forecast_probability_causation_advice_or_scalar_score": False,
            "license": "CC BY 4.0",
            "citation": (
                "Krishna, Ishan (2026). India Geopolitical Risk Monitor. "
                "https://igrm.in/"
            ),
            "source": "https://igrm.in/data/evidence_outputs_demo.json",
            "codebook": "https://igrm.in/standard.html",
            "method": "method:igrm.evidence_outputs@1.0.0",
        },
        "download": {
            "url": "https://igrm.in/downloads/igrm-evidence-outputs-demo.zip",
            "sha256": archive_sha,
            "bytes": len(archive),
            "media_type": "application/zip",
            "authentication_warning": (
                "Authenticate this digest outside the ZIP before extraction; never "
                "execute code merely because it is bundled."
            ),
        },
        "synthetic_labels": {
            _EVENT_ID: "Synthetic policy action",
            _TARGET_ID: "Synthetic crude input",
        },
        "output_set": output_set,
    }
    return payload


def build_demo() -> dict[str, Any]:
    """Return only the deterministic public JSON wrapper."""

    payload, _ = build_demo_artifacts()
    return payload


def main() -> None:
    payload, archive = build_demo_artifacts()
    PUBLIC_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    PUBLIC_ARCHIVE.write_bytes(archive)
    print(PUBLIC_OUTPUT)
    print(PUBLIC_ARCHIVE)


if __name__ == "__main__":
    main()
