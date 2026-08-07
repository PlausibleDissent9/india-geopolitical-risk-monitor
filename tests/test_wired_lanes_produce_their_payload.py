"""A module wired into a lane must have produced its payload by now.

freshness.py catches payloads that STOP being written. Nothing caught
payloads that never STARTED. The difference is not academic: on
2026-08-07 the V5 multilingual lane had run 71 times across a week,
reported success on the last two, and `docs/data/multilingual.json` had
never existed at all. A file that was never written cannot be stale, so
the staleness auditor had nothing to say about it.

`test_every_payload_has_a_lane.py` checks the forward direction -- every
module that writes a payload is run by something. This is the inverse:
every module a workflow actually runs, which writes a payload, must have
that payload on disk. A lane wired up and producing nothing is a lane
whose failure is invisible by construction.

NOT_YET carries the ones that are legitimately still building, each with
a reason and the state of the work. An entry here is a claim with a date
on it, not a way to opt out -- and the whole point is that the list is
short and visible rather than the absence being silent.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DATA = ROOT / "docs" / "data"
WORKFLOWS = ROOT / ".github" / "workflows"

# Payload absent on purpose, with the reason and where it stands.
NOT_YET: dict[str, str] = {
    "multilingual.json": (
        "V5 backfill has never completed a single one of its fifteen "
        "series. The lane is wired and runs nightly; GDELT throttling is "
        "the blocker, not the code. Made visible 2026-08-07 -- the lane "
        "used to report success while landing nothing, and now goes red "
        "when a batch fetches nothing and errors."),
    "media_cloud.json": (
        "S5 is wired into drift.yml but fail-closed on a credential the "
        "founder has not issued: without MEDIACLOUD_API_KEY the module "
        "prints a skip line and writes nothing. Correct behaviour -- a "
        "cross-source check that invents its source is worse than no "
        "check -- but the lane has been running and producing nothing "
        "since it was added, and nothing said so. Found 2026-08-07 by "
        "this test, on its first run."),
}

WRITES = re.compile(r'SITE_DATA\s*/\s*"([\w.]+\.json)"')


def _modules_run_by_workflows() -> set[str]:
    seen: set[str] = set()
    for wf in WORKFLOWS.glob("*.yml"):
        seen.update(re.findall(r"python -m src\.(\w+)",
                               wf.read_text(encoding="utf-8")))
    return seen


def test_every_wired_module_has_produced_its_payload():
    run = _modules_run_by_workflows()
    missing: dict[str, str] = {}
    for module in sorted(run):
        path = SRC / f"{module}.py"
        if not path.exists():
            continue
        for payload in set(WRITES.findall(path.read_text(encoding="utf-8"))):
            if payload in NOT_YET:
                continue
            if not (DATA / payload).exists():
                missing[payload] = module

    assert not missing, (
        f"these payloads are written by modules a workflow runs, and do "
        f"not exist: {missing}. A lane that is wired up and producing "
        "nothing fails invisibly -- freshness.py can only age a file that "
        "is there. Either the lane is broken, or the payload belongs in "
        "NOT_YET with a reason.")


def test_the_not_yet_list_is_short_and_justified():
    """Same discipline as the freshness exemptions and the sitemap
    exclusions. 'Not built yet' is a claim with a date on it."""
    assert len(NOT_YET) <= 3, (
        f"{len(NOT_YET)} payloads pending is no longer a shortlist; the "
        "absence has become the normal state")
    for name, why in NOT_YET.items():
        assert len(why) > 40, f"{name} is excused without a real reason"


def test_a_pending_payload_leaves_the_list_once_it_lands():
    """The failure mode of any exemption list: the thing gets fixed and
    the entry stays, quietly excusing a future regression."""
    landed = [n for n in NOT_YET if (DATA / n).exists()]
    assert not landed, (
        f"these payloads now exist and should be removed from NOT_YET: "
        f"{landed}. Leaving them listed means a later disappearance would "
        "be excused by a note written when they were merely late.")
