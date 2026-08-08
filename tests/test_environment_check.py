"""The local committed gate must run against CI's declared direct packages."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts import check_environment

ROOT = Path(__file__).resolve().parents[1]
REPRODUCE = ROOT / "scripts" / "reproduce.sh"
REPRODUCE_WORKFLOW = ROOT / ".github" / "workflows" / "reproduce.yml"


def test_committed_requirement_files_are_exact_and_installed() -> None:
    pins = check_environment.required_pins(
        (ROOT / "requirements.txt", ROOT / "requirements-dev.txt")
    )
    assert "anthropic" in pins
    assert not check_environment.installed_mismatches(pins)


def test_clean_room_reproduction_installs_runtime_and_gate_pins() -> None:
    script = REPRODUCE.read_text(encoding="utf-8")
    install_lines = [
        line.strip()
        for line in script.splitlines()
        if ".venv/bin/pip install" in line
    ]
    assert install_lines == [
        ".venv/bin/pip install --quiet -r requirements.txt -r requirements-dev.txt"
    ]


def test_reproduction_environment_changes_trigger_a_proof_run() -> None:
    workflow = REPRODUCE_WORKFLOW.read_text(encoding="utf-8")
    for required_path in (
        ".github/workflows/reproduce.yml",
        "scripts/reproduce.sh",
        "requirements.txt",
        "requirements-dev.txt",
    ):
        assert f'      - "{required_path}"' in workflow


def test_environment_check_refuses_a_floating_requirement(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("anthropic>=0.116,<1\n", encoding="utf-8")

    with pytest.raises(check_environment.EnvironmentMismatch, match="not an exact"):
        check_environment.required_pins((requirements,))


def test_environment_check_reports_a_missing_distribution() -> None:
    mismatches = check_environment.installed_mismatches(
        {"igrm-package-that-cannot-exist": "1.0.0"}
    )
    assert mismatches == ["igrm-package-that-cannot-exist missing (expected 1.0.0)"]
