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
# multilingual.json left this list 2026-08-08: after 71 empty runs the
# V5 self-heal finally beat the GDELT throttle and the payload landed
# (bot commit 7a04222). The entry's own rule: landed means delisted.
NOT_YET: dict[str, str] = {
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

# Payload names built from a variable, e.g.
#     SITE_DATA / f"country_{name}.json"
# The first version of this file matched only literal strings, so
# country_monitor -- the China V8 lane -- was invisible to it, and
# country_china.json had never been produced. A test with a blind spot
# exactly where a lane is stalled is the failure this file exists to
# prevent, so the dynamic form is resolved from the workflow's own
# argument rather than skipped.
WRITES_F = re.compile(r'SITE_DATA\s*/\s*f"([\w]*)\{\w+\}([\w.]*\.json)"')


def _invocations() -> list[tuple[str, str]]:
    """(module, first positional arg) for every `python -m src.X [arg]`."""
    out = []
    for wf in WORKFLOWS.glob("*.yml"):
        for m in re.finditer(r"python -m src\.(\w+)([^\n|&;]*)",
                             wf.read_text(encoding="utf-8")):
            args = [a for a in m.group(2).split() if not a.startswith("-")]
            out.append((m.group(1), args[0] if args else ""))
    return out


def test_invocations_are_detected_at_all():
    """Guard for the detector itself: the regex keys on `python -m src.`,
    and a launcher change (e.g. $PY -m src.X) would empty the set and
    pass every test below on nothing."""
    assert len(set(_invocations())) >= 30, (
        f"only {len(set(_invocations()))} workflow invocations detected; "
        "~40 existed when this was written -- the detector has probably "
        "stopped matching how workflows invoke modules.")


def test_every_wired_module_has_produced_its_payload():
    missing: dict[str, str] = {}
    for module, arg in sorted(set(_invocations())):
        path = SRC / f"{module}.py"
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")

        expected = set(WRITES.findall(src))
        # Resolve f-string payload names using the argument the workflow
        # actually passes: `python -m src.country_monitor china` plus
        # `f"country_{name}.json"` means country_china.json is owed.
        if arg:
            expected |= {f"{pre}{arg}{post}" for pre, post in WRITES_F.findall(src)}

        for payload in expected:
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
    assert len(NOT_YET) <= 4, (
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
