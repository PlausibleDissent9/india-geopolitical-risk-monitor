"""The local committed gate must run against CI's declared direct packages."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts import check_environment

ROOT = Path(__file__).resolve().parents[1]
REPRODUCE = ROOT / "scripts" / "reproduce.sh"
REPRODUCE_WORKFLOW = ROOT / ".github" / "workflows" / "reproduce.yml"


def test_committed_requirement_files_are_exact_and_installed() -> None:
    """Runtime pins must be present; gate pins only where a gate runs.

    This asserted both files at once, which is true of ci.yml, the local
    gate and reproduce.yml -- and false of daily.yml and morning.yml,
    which install requirements.txt alone and then run this very suite as
    their first step. So the nightly publish and the 06:30 IST contract
    both failed on ruff and mypy being absent, which is exactly how those
    lanes are built on purpose. daily-update #100 died here at 15:53Z on
    2026-08-08 having computed nothing.

    A version that DRIFTS is still a failure everywhere, and a partially
    installed gate environment is still a failure -- only a wholly
    runtime-only environment is allowed to skip the gate half. That keeps
    the false-green this test was written to close.
    """

    runtime = check_environment.required_pins((ROOT / "requirements.txt",))
    gate = check_environment.required_pins((ROOT / "requirements-dev.txt",))
    assert "anthropic" in runtime
    assert not check_environment.installed_mismatches(runtime)

    gate_problems = check_environment.installed_mismatches(gate)
    if len(gate_problems) == len(gate) and all(
        " missing (" in problem for problem in gate_problems
    ):
        pytest.skip(
            "runtime-only environment: every gate pin is absent, which is "
            "how the publishing lanes are installed on purpose")
    assert not gate_problems


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


def test_public_workflow_uses_the_rights_safe_reconstruction_path() -> None:
    workflow = REPRODUCE_WORKFLOW.read_text(encoding="utf-8")
    assert "run: bash scripts/reproduce.sh --public" in workflow
    assert "run: bash scripts/reproduce.sh --use-cache" not in workflow

    script = REPRODUCE.read_text(encoding="utf-8")
    public_environment = script.index('if [[ "$MODE" == "--public" ]]')
    test_run = script.index('pytest -q -m "not live"')
    public_start = script.index('if [[ "$MODE" == "--public" ]]', test_run)
    public_exit = script.index("  exit 0", public_start)
    cache_pipeline = script.index('REBUILD_MARK="$WORK/rebuild_start"')
    public_block = script[public_start:public_exit]
    assert "src.blind_replicator --check" in public_block
    assert "src.run_daily" not in public_block
    assert public_exit < cache_pipeline

    offline_export = script.index("export IGRM_OFFLINE=1", public_environment)
    assert public_environment < offline_export < test_run < public_start
    assert "IGNORE_TAIL_DAYS" not in script
    assert "MARKET_TOL" not in script
    assert "list lengths" in script


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
