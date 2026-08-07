"""Every module that writes a published payload must be run by something.

This exists because `src/publish_shares.py` shipped on 2026-08-07 as the
answer to a referee finding -- raw shares promoted to "a first-class
published artifact" -- and was wired into no workflow at all. It ran
once, by hand, and `docs/data/shares.csv` would have sat frozen on
2026-08-06 forever while the site advertised it as the daily quantity.
Nothing failed. Nothing went red. The file was simply never written
again.

That is the most dangerous shape of bug this project can have, because
the honesty surfaces are exactly the things nobody looks at twice: a
stale gap list, a frozen provenance record, a syndication multiplier
from last week. They keep serving plausible numbers after they stop
being true.

So: if a module writes into docs/data and can be run as a script, some
workflow must invoke it.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
WORKFLOWS = ROOT / ".github" / "workflows"

# Modules that write a payload but are deliberately invoked BY another
# module rather than by a workflow line of their own. Each one needs a
# named caller, so an entry here is a claim that can be checked, not a
# way to opt out of the rule.
INVOKED_BY_ANOTHER_MODULE = {
    "build_index": "src.run_daily",
    "render_site": "src.run_daily",
    "event_study": "src.run_daily",
    "maps_data": "its own workflow step",
    "receipts": "src.receipts_ngrams (artlist fallback)",
    "nowcast": "nowcast.yml",
    # Genuinely one-shot or human-paced, not oversights. Each is
    # justified here because "it doesn't need a lane" is a claim, and an
    # unjustified entry is how this test gets hollowed out.
    "fetch_cow": ("static: Correlates of War MID 5.0 is a frozen "
                  "historical release, fetched once, 208 years that do "
                  "not change overnight"),
    "fetch_ucdp": ("pinned release, manual --backfill; UCDP publishes "
                   "annually and the version is deliberately fixed"),
    "fetch_trends": ("Google Trends is rate-limited and unreliable "
                     "enough that an automated daily call would fail "
                     "more often than it succeeded; run deliberately"),
    "retest": ("founder-paced: writes a blind labelling sheet for a "
               "human to fill, so regenerating it nightly would "
               "reissue the draw before anyone answered it"),
}

WRITES_PAYLOAD = re.compile(
    r"SITE_DATA\s*/|docs\"\s*/\s*\"data\"|docs/data/[\w.]+\"")


def _module_names_run_by_workflows() -> set[str]:
    seen: set[str] = set()
    for wf in WORKFLOWS.glob("*.yml"):
        text = wf.read_text(encoding="utf-8")
        seen.update(re.findall(r"python -m src\.(\w+)", text))
    # run_daily orchestrates several modules in-process.
    rd = (SRC / "run_daily.py").read_text(encoding="utf-8")
    seen.update(re.findall(r"from \. import ([\w, ]+)", rd)[0].split(", ")
                if re.findall(r"from \. import ([\w, ]+)", rd) else [])
    return seen


def test_every_payload_writing_module_is_invoked_somewhere():
    run = _module_names_run_by_workflows()
    orphans = []
    for path in sorted(SRC.glob("*.py")):
        name = path.stem
        if name.startswith("_"):
            continue
        text = path.read_text(encoding="utf-8")
        if not WRITES_PAYLOAD.search(text):
            continue
        if 'if __name__ == "__main__"' not in text:
            continue
        if name in run or name in INVOKED_BY_ANOTHER_MODULE:
            continue
        orphans.append(name)

    assert not orphans, (
        "these modules write into docs/data but no workflow runs them, so "
        "their payloads would freeze at whatever value they last had "
        f"while the site keeps serving them: {orphans}. Wire them into a "
        "workflow, or add them to INVOKED_BY_ANOTHER_MODULE with the "
        "name of the caller.")


def test_the_shares_lane_specifically_is_wired():
    """The regression that motivated this file. Named explicitly so a
    future reordering that drops it fails with an obvious message."""
    run = _module_names_run_by_workflows()
    assert "publish_shares" in run, (
        "publish_shares is not invoked by any workflow; docs/data/shares.csv "
        "would go stale while being advertised as the daily quantity")


def test_shares_dependencies_run_in_the_right_order():
    """provenance -> publish_shares -> monthly. Out of order, each
    silently consumes yesterday's version of the previous one."""
    daily = (WORKFLOWS / "daily.yml").read_text(encoding="utf-8")
    order = [m for m in re.findall(r"python -m src\.(\w+)", daily)
             if m in ("provenance", "publish_shares", "monthly")]
    assert order == ["provenance", "publish_shares", "monthly"], (
        f"dependency order broken in daily.yml: {order}")
