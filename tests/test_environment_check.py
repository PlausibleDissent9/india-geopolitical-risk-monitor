"""The local committed gate must run against CI's declared direct packages."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts import check_environment

ROOT = Path(__file__).resolve().parents[1]


def test_committed_requirement_files_are_exact_and_installed() -> None:
    pins = check_environment.required_pins(
        (ROOT / "requirements.txt", ROOT / "requirements-dev.txt")
    )
    assert "anthropic" in pins
    assert not check_environment.installed_mismatches(pins)


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
