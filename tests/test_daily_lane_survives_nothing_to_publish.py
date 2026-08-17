"""Nothing to publish must not fail the enrichment lane.

WHAT HAPPENED (found 2026-08-17)

morning.yml publishes the 06:00 contract. daily.yml refreshes the derived
plane. Both call into final_publication, and daily.yml's "Run pipeline"
step asked run_daily to publish D-1 unconditionally.

On every day the contract lane WORKED, the newest closed day was already
published by the time daily.yml got there. require_ordered_target demands
the exact next UNPUBLISHED day before UTC D0, found none, and raised
final_target_invalid. The step failed, and GitHub skipped the 27 steps
after it -- the derived lanes, the freshness audit, the universal _meta
stamp, the machine answers.

Measured on run 31975757637: 20 succeeded, 1 failed, 27 skipped. The
commit step then logged "refusing every derived docs change" and banked
raw evidence only. So the lane that exists to refresh the derived plane
died before refreshing it, once per day, for days, while the published
index itself stayed perfectly correct. 37 payloads went stale that way.

It is the deadlock daily.yml's own header already records -- the live
freshness test running as step one and killing the lane "before it could
refresh the very payloads whose staleness it was complaining about" --
recurring behind a different gate. That is the fourth plane this shape
has appeared on in this repo, so it gets a behavioural lock rather than a
comment.

These tests run the step's REAL shell body out of the workflow file with
a stubbed `python` on PATH. A text match would pass on a body that had
been rewritten to fail again.
"""
from __future__ import annotations

import re
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / ".github" / "workflows" / "daily.yml"

# What GitHub substitutes before bash ever sees the body. final_source
# must read "success" or the step refuses earlier, for an unrelated and
# correct reason; backfill must be false to reach the nightly branch.
EXPRESSIONS = {
    "${{ steps.final_source.outcome }}": "success",
    "${{ github.event.inputs.backfill }}": "false",
    "${{ steps.final_contract.outputs.today }}": "2026-08-17",
    "${{ steps.final_contract.outputs.target }}": "2026-08-16",
    "${{ github.run_number }}": "999",
}


def _step_body() -> str:
    lines = DAILY.read_text(encoding="utf-8").splitlines()
    start = next(n for n, line in enumerate(lines)
                 if line.strip() == "- name: Run pipeline")
    end = next(n for n in range(start + 1, len(lines))
               if re.match(r"^      - name: ", lines[n]))
    block = lines[start:end]
    run_at = next(n for n, line in enumerate(block) if line.strip() == "run: |")
    body = textwrap.dedent("\n".join(block[run_at + 1:]))
    for expression, value in EXPRESSIONS.items():
        body = body.replace(expression, value)
    remaining = re.findall(r"\$\{\{[^}]*\}\}", body)
    assert not remaining, (
        f"unsubstituted workflow expressions {remaining}; add them to "
        "EXPRESSIONS so this test keeps exercising the real body")
    return body


def _run(tmp_path: Path, next_target: str) -> tuple[int, str, Path]:
    """Execute the step body with a fake `python` that reports next_target."""
    marker = tmp_path / "run_daily_was_called"
    stub = tmp_path / "python"
    stub.write_text(
        "#!/bin/bash\n"
        'for a in "$@"; do\n'
        '  if [ "$a" = "--next-target" ]; then echo "' + next_target + '"; exit 0; fi\n'
        '  if [ "$a" = "src.run_daily" ]; then printf "%s" "$*" > "'
        + str(marker) + '"; exit 0; fi\n'
        "done\n"
        "exit 0\n",
        encoding="utf-8")
    stub.chmod(0o755)
    # timeout(1) would exec the real python; stub it to just run its command.
    (tmp_path / "timeout").write_text(
        '#!/bin/bash\nshift\nexec "$@"\n', encoding="utf-8")
    (tmp_path / "timeout").chmod(0o755)

    proc = subprocess.run(
        ["bash", "-e", "-c", _step_body()],
        cwd=ROOT, capture_output=True, text=True,
        env={"PATH": f"{tmp_path}:/usr/bin:/bin", "HOME": str(tmp_path)},
    )
    return proc.returncode, proc.stdout + proc.stderr, marker


def test_the_body_is_valid_shell():
    proc = subprocess.run(["bash", "-n", "-c", _step_body()],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_nothing_to_publish_skips_instead_of_failing(tmp_path):
    """The regression. Exit 0 means the 27 derived steps below still run."""
    code, output, marker = _run(tmp_path, "none")
    assert code == 0, (
        "the step failed when there was nothing to publish, so every "
        f"derived step after it is skipped again:\n{output}")


def test_nothing_to_publish_never_invokes_the_PUBLISHING_pipeline(tmp_path):
    """The invariant is about MODE, not about calling run_daily at all.

    The first version of this asserted run_daily was never invoked, and
    that was too strong -- it forbade the fix for a second bug found the
    same night. event_study.json is refreshed only by run_daily's
    non-final branch, so on every day the contract lane published (the
    good case) nothing recomputed it and it sat 8 days old with both
    lanes green. The repair is to run `--derived-only` here, which
    returns before require_ordered_target and publishes nothing.

    So what must stay true is narrower and sharper: no invocation that
    reaches the publication guards. That means no --target, since a
    target is exactly what require_ordered_target would reject.
    """
    code, output, marker = _run(tmp_path, "none")
    assert code == 0, output
    if not marker.exists():
        return  # not invoked at all is also fine
    argv = marker.read_text(encoding="utf-8")
    assert "--derived-only" in argv, (
        f"run_daily was invoked with no unpublished target, and not in "
        f"--derived-only mode: {argv!r}. It would reach "
        "require_ordered_target, raise final_target_invalid, and fail the "
        "lane -- the outage this file exists to prevent.")
    assert "--target" not in argv, (
        f"--derived-only was passed a target ({argv!r}); the derived path "
        "must take none, or it is a publish with the guards skipped")


def test_a_real_target_is_still_published(tmp_path):
    """Guard the guard: skipping must not become skipping ALWAYS."""
    code, output, marker = _run(tmp_path, "2026-08-16")
    assert code == 0, output
    assert marker.exists(), (
        "an unpublished day was available and run_daily was never called; "
        "the lane would silently stop publishing")
    assert "2026-08-16" in marker.read_text(encoding="utf-8")


def test_the_target_comes_from_next_target_not_a_blind_d_minus_one(tmp_path):
    """require_ordered_target accepts exactly one value.

    Passing D-1 could only ever succeed when D-1 happened to BE the next
    unpublished day. When a backlog exists it is guaranteed to fail, which
    is how a single missed day used to wedge the lane indefinitely.
    """
    code, _output, marker = _run(tmp_path, "2026-08-11")
    assert code == 0
    assert marker.exists()
    published = marker.read_text(encoding="utf-8")
    assert "2026-08-11" in published, (
        "the step published something other than the next unpublished day")
    assert "2026-08-16" not in published, (
        "the step is still passing the blind D-1 from final_contract; "
        "require_ordered_target would refuse it whenever a backlog exists")


@pytest.mark.parametrize("phrase", ["--next-target", "src.run_daily"])
def test_the_step_still_does_both_jobs(phrase):
    assert phrase in _step_body()
