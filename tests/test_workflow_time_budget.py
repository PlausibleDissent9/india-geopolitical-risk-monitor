"""Publisher wall clocks must include the fail-closed post-rebase gate."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_gfg_probe_budget_includes_the_measured_full_publish_gate() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "bq-gfg-probe.yml"
    ).read_text(encoding="utf-8")
    match = re.search(r"(?m)^    timeout-minutes:\s*(\d+)\s*$", workflow)
    assert match, "bq-gfg-probe has no explicit job-level timeout"
    assert int(match.group(1)) >= 25, (
        "the lane needs its probe time plus the measured ~10-minute "
        "committed-tree publication gate; 10 minutes cancelled run #9"
    )
    assert 'bash scripts/publish_push.sh "gfg probe:' in workflow
