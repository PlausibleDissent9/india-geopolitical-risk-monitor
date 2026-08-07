"""Every script a committed workflow invokes must itself be committed.

On 2026-08-07 the Commit-data step's `stage_daily_outputs.sh` was wired
into daily.yml and pushed while the script sat uncommitted in the
working tree -- the next scheduled run would have died at the publish
step, ending the morning contract. The file-ahead-of-its-pair failure,
caught by an agent's out-of-scope flag eight hours before the cron.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

REF = re.compile(r"(?:bash|python3?)\s+(scripts/[\w./-]+)")


def test_every_workflow_referenced_script_is_committed():
    refs: dict[str, list[str]] = {}
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        for script in REF.findall(wf.read_text(encoding="utf-8")):
            refs.setdefault(script, []).append(wf.name)
    assert len(refs) >= 3, (
        f"the workflow scan found only {len(refs)} script references; "
        "either the workflows stopped using scripts/ or this regex went "
        "blind -- both need a human look")
    missing = {s: wfs for s, wfs in refs.items() if not (ROOT / s).is_file()}
    assert not missing, (
        f"workflows invoke scripts that do not exist in the tree: "
        f"{missing}. A lane that references an uncommitted script dies "
        "at that step on its next scheduled run.")
