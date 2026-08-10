"""The receipts lane must stage every tracked file its own steps modify.

WHAT HAPPENED
receipts-extended run #2 (2026-08-10) completed its 95-minute evidence scan,
built all four derivatives, stamped the payloads -- and published nothing.
The job's only failing step was the publish, and the annotation said why:

    publish refused before rebase: the working tree has unstaged changes,
    which makes 'git pull --rebase' fail instantly and burns all five
    retries without ever running the gate. Files: data/raw/syndication.csv

`python -m src.syndication` in the derivatives step appends the day's rows to
`data/raw/syndication.csv`, which is TRACKED. The publish step staged
`data/raw/receipt_days docs` and nothing else. publish_push.sh's pre-rebase
guard then did exactly what it exists to do: refuse to rebase over a dirty
tree rather than let `git pull --rebase` shred it.

The guard was right. The lane forgot its own product. Ninety-five minutes of
runner time went into the bin over one missing path in a `git add`.

WHY THIS IS A TEST AND NOT JUST A FIX
The lane's derivative list will grow. The next module someone adds that
persists tracked state outside `docs/` re-creates this failure exactly, and
it will again cost a full day's scan before anyone reads the annotation.
This file makes the coupling explicit: the history file the syndication
module writes is read FROM the module, not retyped here, so a moved file
fails loudly instead of silently splitting from the workflow.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import src.syndication as syndication

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "receipts-extended.yml"


def _history_relpath() -> str:
    return syndication.HISTORY.relative_to(ROOT).as_posix()


def _success_git_add() -> str:
    """The `git add` line of the success branch of the publish step."""
    text = WORKFLOW.read_text(encoding="utf-8")
    m = re.search(
        r'if \[ "\$\{\{ steps\.scan\.outcome \}\}" = "success" \];'
        r".*?git add ([^\n]+)", text, re.S)
    assert m, "the success-path git add is gone from receipts-extended.yml"
    return m.group(1).strip()


def test_the_syndication_history_is_staged_by_the_lane_that_writes_it() -> None:
    relpath = _history_relpath()
    staged = _success_git_add()
    assert relpath in staged.split(), (
        f"receipts-extended.yml's success path stages {staged!r} but "
        f"src.syndication (run in the SAME job, two steps earlier) appends "
        f"to {relpath}, which is tracked. publish_push.sh refuses a dirty "
        "tree before rebasing, so the whole scan publishes nothing -- this "
        "is exactly run #2 of 2026-08-10 again.")


def test_the_history_file_is_actually_tracked() -> None:
    """The failure mode requires trackedness -- an untracked file does not
    dirty a rebase. If this ever fails because the file was deliberately
    untracked, the day's syndication rows silently stop publishing, which
    is a different defect, not a fix."""
    out = subprocess.run(
        ["git", "ls-files", "--", _history_relpath()],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    assert out, (
        f"{_history_relpath()} is no longer tracked; the syndication history "
        "would vanish from every future publish rather than merely dirty "
        "the tree")


def test_every_derivative_module_that_writes_tracked_state_is_staged() -> None:
    """The generalisation, kept deliberately concrete: for each module the
    derivatives step runs, any ROOT-relative tracked path it opens for
    append/write outside docs/ must appear in the git add. Modules are read
    from the workflow so a new derivative is checked the day it is added."""
    text = WORKFLOW.read_text(encoding="utf-8")
    m = re.search(r"Build extended-evidence derivatives.*?run: \|(.*?)- name:",
                  text, re.S)
    assert m, "derivatives step not found"
    modules = re.findall(r"python -m (src\.\w+)", m.group(1))
    assert "src.syndication" in modules, (
        "src.syndication left the derivatives step; retire this test's "
        "coupling knowingly, not by accident")
    staged = _success_git_add().split()
    # docs is staged wholesale; only out-of-docs writers need naming.
    known_out_of_docs = {"src.syndication": _history_relpath(),
                         "src.receipts_archive": "data/raw/receipt_days"}
    for module, path in known_out_of_docs.items():
        if module in modules:
            assert any(s == path or path.startswith(s + "/") or s == path
                       for s in staged) or path in staged, (
                f"{module} persists {path} but the publish step does not "
                "stage it")
