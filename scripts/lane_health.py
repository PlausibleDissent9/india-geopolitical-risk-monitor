"""Open an issue when a lane has been failing, and close it when it recovers.

WHY THIS EXISTS
---------------
Between 2026-08-12 and 2026-08-17 the daily enrichment lane failed on
every scheduled run. Nobody knew for five days. Not because no check
caught it -- several did, loudly and correctly:

    ci                     red 6/6, listing 37 stale payloads by name
    daily-update           red 5/5
    freshness (in CI)      named comparators.json among the stale

The checks worked. What was missing was anything that made a red lane
ARRIVE somewhere a human would see it. GitHub emails per-failure, which
is exactly the shape people filter into a folder and stop reading, and it
cannot report a run that never started at all.

There is also a self-referential blind spot this compensates for.
docs/data/freshness.json is EXEMPT from its own audit -- reasonably, since
auditing your own output in the same run is circular -- so when the lane
stopped running, the published staleness report sat a week old reporting
"71 fresh, 0 stale" and looked healthy. The surface that reports rot is
the one surface that cannot report its own.

WHAT THIS DOES
--------------
Reads recent runs per workflow from the GitHub API. A lane with
FAIL_THRESHOLD consecutive non-successes gets one open issue, updated
rather than duplicated. When it goes green again the issue is closed with
the run that recovered it.

Deliberately NOT a replacement for an external dead-man's switch. This
runs inside GitHub Actions, so it cannot tell you that GitHub itself
stopped firing crons -- the failure this repo has already recorded
(2026-07-31, the 11:00 slot never fired at all). An off-platform ping is
the only thing that catches that, and it needs an account this process
must not create.

    python scripts/lane_health.py --check      # report only, exit 0
    python scripts/lane_health.py --escalate   # open/close issues
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

REPO = os.environ.get("GITHUB_REPOSITORY", "PlausibleDissent9/india-geopolitical-risk-monitor")
API = "https://api.github.com"

# Consecutive non-successes before a lane is escalated. Two is deliberate:
# one failure is weather -- GDELT throttles, a runner dies -- and waiting
# for three would have taken until 2026-08-15 to notice an outage that
# began on the 12th.
FAIL_THRESHOLD = 2

# Lanes whose failure means the product is wrong or going stale. Lanes not
# listed here still fail visibly in the Actions tab; they just do not page
# anyone. Keeping this list SHORT is what stops the signal becoming noise
# that gets filtered, which is how the last outage stayed invisible.
# Keyed by workflow FILE, not display name. The first version queried the
# global /actions/runs feed and filtered by name, which silently produced
# the bug this whole script exists to prevent: with many lanes active, no
# completed daily-update fell inside the 30-run window, the filtered list
# came back EMPTY, and an empty list scored as zero consecutive failures
# and printed "green" -- while the most recent completed daily-update had
# in fact failed. Absence read as success, in the health checker.
WATCHED = {
    "morning.yml": ("morning-contract", "the 06:00 publish itself"),
    "daily.yml": ("daily-update", "the derived plane; its failure is what froze 37 payloads"),
    "ci.yml": ("ci", "the gate every publish re-runs"),
}

ISSUE_MARKER = "<!-- lane-health:%s -->"


def _req(path: str, method: str = "GET", body: dict[str, Any] | None = None) -> Any:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("lane_health: GITHUB_TOKEN is not set")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API}{path}", data=data, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def consecutive_failures(workflow_file: str) -> tuple[int | None, list[dict[str, Any]]]:
    """Consecutive non-successes among this lane's COMPLETED runs.

    Returns None -- not 0 -- when there is no completed run to judge. "No
    data" and "healthy" must never be the same value; conflating them is
    how a health check reports green about a lane it cannot see.

    Counts cancelled as a failure: GitHub reports a job that hit its
    timeout as cancelled, and six of coverage-drift's ten "cancellations"
    were exactly that -- a hang, not an eviction by another lane.
    """
    runs = _req(f"/repos/{REPO}/actions/workflows/{workflow_file}/runs?per_page=20")
    completed = [r for r in runs.get("workflow_runs", []) if r["conclusion"]]
    if not completed:
        return None, []
    streak = 0
    for run in completed:
        if run["conclusion"] in ("success", "skipped"):
            break
        streak += 1
    return streak, completed[:5]


def _find_issue(workflow_name: str) -> dict[str, Any] | None:
    marker = ISSUE_MARKER % workflow_name
    issues = _req(f"/repos/{REPO}/issues?state=open&per_page=100")
    for issue in issues or []:
        if marker in (issue.get("body") or ""):
            return issue
    return None


def escalate(workflow_name: str, why: str, streak: int,
             recent: list[dict[str, Any]]) -> None:
    marker = ISSUE_MARKER % workflow_name
    lines = [
        marker,
        f"`{workflow_name}` has failed **{streak} consecutive runs**.",
        "",
        f"Why this lane is watched: {why}.",
        "",
        "| run | conclusion | created |",
        "| --- | --- | --- |",
    ]
    for run in recent:
        lines.append(f"| [{run['id']}]({run['html_url']}) | {run['conclusion']} | {run['created_at']} |")
    lines += [
        "",
        "This issue updates in place while the lane stays red and closes "
        "itself when a run succeeds. It is not a dead man's switch: it runs "
        "inside Actions and so cannot report that GitHub stopped firing "
        "crons at all.",
    ]
    body = "\n".join(lines)
    existing = _find_issue(workflow_name)
    if existing:
        _req(f"/repos/{REPO}/issues/{existing['number']}", "PATCH", {"body": body})
        print(f"[lane-health] updated #{existing['number']} for {workflow_name} (streak {streak})")
    else:
        made = _req(f"/repos/{REPO}/issues", "POST", {
            "title": f"{workflow_name} has failed {streak} runs in a row",
            "body": body,
        })
        print(f"[lane-health] opened #{made['number']} for {workflow_name}")


def resolve(workflow_name: str) -> None:
    existing = _find_issue(workflow_name)
    if not existing:
        return
    _req(f"/repos/{REPO}/issues/{existing['number']}/comments", "POST",
         {"body": f"`{workflow_name}` is green again. Closing."})
    _req(f"/repos/{REPO}/issues/{existing['number']}", "PATCH", {"state": "closed"})
    print(f"[lane-health] closed #{existing['number']} for {workflow_name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="report only")
    parser.add_argument("--escalate", action="store_true", help="open/close issues")
    args = parser.parse_args(argv)
    if not (args.check or args.escalate):
        parser.print_help()
        return 2

    for workflow_file, (name, why) in sorted(WATCHED.items()):
        try:
            streak, recent = consecutive_failures(workflow_file)
        except urllib.error.HTTPError as exc:
            print(f"[lane-health] {name}: API error {exc.code}", file=sys.stderr)
            continue
        if streak is None:
            # Said out loud rather than treated as healthy. A watched lane
            # with no completed run is itself worth seeing.
            print(f"[lane-health] {name}: NO COMPLETED RUNS to judge")
            continue
        state = "RED" if streak >= FAIL_THRESHOLD else ("wobbling" if streak else "green")
        print(f"[lane-health] {name}: {streak} consecutive failures ({state})")
        if not args.escalate:
            continue
        if streak >= FAIL_THRESHOLD:
            escalate(name, why, streak, recent)
        else:
            resolve(name)

    # --check never fails the build: this is a reporter, and a reporter that
    # can redden a lane becomes one more thing to silence.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
