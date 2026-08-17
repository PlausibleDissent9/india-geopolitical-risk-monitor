"""Every file the daily lane writes must be a file the daily lane stages.

WHAT HAPPENED (2026-08-17, run 32069493627)

All 48 steps ran. The derived lanes refreshed the plane. And the publish
still died, on this:

    publish refused before rebase: the working tree has unstaged changes
    Files: validation/forecast_questions.json

src.forecasts runs in daily.yml and nowhere else, and writes that file to
"ensure the NEXT Monday's questions exist (commit-before-open)".
scripts/stage_daily_outputs.sh staged docs, data/raw, notes-inbox and
.trigger. Not validation. So the file was written on every run and staged
on none, and publish_push.sh -- correctly, by the guard it grew for
exactly this -- refused the whole publish rather than sweep an unreviewed
path into it.

The dirty tree was the cheap half of the damage. The expensive half is
that validation/forecast_questions.json held FIVE questions, all for
window_start 2026-08-10: the founder-signed launch commit, and nothing
after it. Every Monday since was generated inside a runner and thrown
away. The V11 experiment's whole warrant is that a question is COMMITTED
before its window opens. A question that never reaches a commit is not
pre-registered; it is arithmetic with a nice name.

WHAT THIS CHECKS

For every module daily.yml actually invokes: find its module-level path
constants, keep the ones the module WRITES to, and require each to live
under a root the staging script stages. Writes, not references -- a
module that merely reads validation/forecast_logit_frozen.json is not a
staging problem, and a check that cannot tell those apart would flag
five modules here and get deleted for crying wolf.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
STAGE_SCRIPT = ROOT / "scripts" / "stage_daily_outputs.sh"

sys.path.insert(0, str(ROOT / "tests"))
import test_every_payload_has_a_lane as lanes  # noqa: E402

# Methods that mean "this path is an output".
WRITE_CALLS = {"write_text", "write_bytes", "to_csv", "to_json"}

# Paths a daily-lane module can write and must NOT be staged, each with
# the reason. An exemption is a claim, so it is written down and a second
# test checks the claim still holds.
#
# The first run of this file surfaced exactly one, and it resolves the
# opposite way to the bug that prompted the file. src/forecasts.py does
# write validation/forecast_logit_frozen.json -- but only under
# `if not FROZEN.exists()`, and its own docstring says the coefficients
# are "fit once ... then FROZEN. Refits are new registrations, never
# silent updates." Staging it would let an automated lane commit a refit
# of a signed registration, which is the thing the methodology forbids.
# So it stays unstaged ON PURPOSE: if it is ever written, the tree goes
# dirty, the publish refuses, and a human finds out. That is the correct
# outcome, not a bug to be plumbed around.
UNSTAGED_BY_DESIGN: dict[str, str] = {
    "validation/forecast_logit_frozen.json":
        "frozen registered coefficients; an automated commit of a refit "
        "would be a silent re-registration. Written only under "
        "`if not FROZEN.exists()`, so a dirty tree here is the alarm.",
}


def _staged_roots() -> set[str]:
    """Top-level paths the success branch of the staging script adds."""
    text = STAGE_SCRIPT.read_text(encoding="utf-8")
    head = text.split('if [ "$JOB_STATUS" = "success" ]', 1)[1]
    head = head.split("\nfi", 1)[0]
    roots: set[str] = set()
    for line in head.splitlines():
        line = line.strip()
        if line.startswith("#") or not line.startswith("git add "):
            continue
        for token in line[len("git add "):].split():
            if token in ("||", "true"):
                continue
            roots.add(token)
    return roots


def _module_paths(tree: ast.Module) -> dict[str, str]:
    """NAME -> "dir/file" for module-level `NAME = ROOT / "a" / "b"`."""
    out: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        parts: list[str] = []
        cur: ast.expr = node.value
        while isinstance(cur, ast.BinOp) and isinstance(cur.op, ast.Div):
            if isinstance(cur.right, ast.Constant) and isinstance(cur.right.value, str):
                parts.append(cur.right.value)
            cur = cur.left
        if isinstance(cur, ast.Name) and cur.id == "ROOT" and parts:
            out[target.id] = "/".join(reversed(parts))
    return out


def _written_names(tree: ast.Module) -> set[str]:
    """Names used as a write target: NAME.write_text(...) or x.to_csv(NAME)."""
    written: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in WRITE_CALLS:
            if isinstance(func.value, ast.Name):
                written.add(func.value.id)
            for arg in node.args:
                if isinstance(arg, ast.Name):
                    written.add(arg.id)
    return written


def _daily_modules() -> list[str]:
    return sorted(set(lanes._invocations(lanes.WORKFLOWS / "daily.yml")))


def _covered(rel: str, roots: set[str]) -> bool:
    return any(rel == r or rel.startswith(r.rstrip("/") + "/") for r in roots)


def test_the_staging_script_still_has_a_success_branch_to_read():
    """Guard the guard: if the parse finds nothing, every assertion below
    passes by matching nothing."""
    roots = _staged_roots()
    assert roots, "parsed no `git add` paths from the staging script's success branch"
    assert "docs" in roots, f"docs is not staged? parsed: {sorted(roots)}"


@pytest.mark.parametrize("module", _daily_modules())
def test_every_path_this_daily_module_writes_is_staged(module):
    path = SRC / f"{module}.py"
    if not path.exists():
        return
    tree = ast.parse(path.read_text(encoding="utf-8"))
    consts = _module_paths(tree)
    written = _written_names(tree)
    roots = _staged_roots()
    unstaged = sorted(
        rel for name, rel in consts.items()
        if name in written
        and not _covered(rel, roots)
        and rel not in UNSTAGED_BY_DESIGN
    )
    assert not unstaged, (
        f"src/{module}.py runs in daily.yml and writes {unstaged}, which "
        f"scripts/stage_daily_outputs.sh does not stage (it stages "
        f"{sorted(roots)}). The write leaves the tree dirty, so "
        "publish_push.sh refuses the whole publish before it rebases -- and "
        "whatever the file was recording never reaches a commit at all. "
        "Add the exact path to the staging script, not its parent directory.")


def test_the_forecast_registry_is_named_exactly_not_by_directory():
    """validation/ also holds frozen registrations and signed records.
    `git add validation` would sweep those into an automated publish,
    which is the class of accident publish_push.sh refuses to guess
    about. The lane writes one file there and must name that one file."""
    text = STAGE_SCRIPT.read_text(encoding="utf-8")
    success = text.split('if [ "$JOB_STATUS" = "success" ]', 1)[1].split("\nfi", 1)[0]
    assert "validation/forecast_questions.json" in success, (
        "the forecast question registry is no longer staged; the evidence "
        "clock stops the moment it is not committed")
    assert not re.search(r"^\s*git add\s+validation\s*(\|\||$)", success, re.M), (
        "the staging script stages all of validation/; frozen registrations "
        "and signed records must never be swept into an automated publish")


def test_every_staging_exemption_still_earns_it():
    """An exemption is a claim about the code, and claims rot.

    forecast_logit_frozen.json is exempt because its write is guarded by
    an existence check, so it cannot fire on an ordinary run. Remove that
    guard and the exemption becomes a hole: the lane would refit frozen
    coefficients every night and the only thing stopping a silent
    re-registration would be that nobody staged the file.
    """
    for rel, why in UNSTAGED_BY_DESIGN.items():
        assert len(why) > 40, f"{rel} is exempt without a stated reason"
    text = (SRC / "forecasts.py").read_text(encoding="utf-8")
    assert re.search(r"if not FROZEN\.exists\(\):\s*\n\s*FROZEN\.write_text", text), (
        "src/forecasts.py no longer guards the frozen-coefficient write "
        "with `if not FROZEN.exists()`. Its staging exemption in this file "
        "assumed that guard: without it the lane refits a signed "
        "registration on every run.")
