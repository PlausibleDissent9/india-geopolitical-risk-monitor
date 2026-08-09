"""A cited hash must be the hash of the file that ships.

WHAT WAS WRONG
`src/assistant_answers.py` records a `source_sha256` beside every fact
it answers with, so a reader can verify the answer against the exact
bytes it came from. That guarantee is order-dependent, and daily.yml had
the order backwards.

`build_index.write_site_outputs` writes latest.json with a `_meta`
carrying what / units / license / citation / codebook / generated -- but
NOT `source`. `src/stamp_meta` adds `source`. So a lane that generates
the answers and stamps afterwards records the hash of a file that no
longer exists by the time it commits, and
`test_the_payload_is_exactly_what_the_assistant_answers` refuses the
publish.

REPRODUCED, 2026-08-09, both directions:

    remove _meta.source from docs/data/latest.json, then
      assistant_answers -> stamp_meta   FAILS
      stamp_meta -> assistant_answers   passes

morning.yml ran them in the correct order. daily.yml ran
assistant_answers inside its derived-lanes block, ~180 lines before the
stamp.

WHY POSITION, NOT INTENT
The comment in daily.yml explaining the order is not the thing CI runs.
This reads the workflow's real step sequence, the same way
test_asset_versions.py guards the asset stamp's position.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / "\x2egithub" / "workflows"

# A module whose output embeds a hash of another published payload, and
# therefore has to run after every module that rewrites one.
HASH_CITING = "assistant_answers"
# The last module that rewrites a payload's bytes before the commit.
LAST_WRITER = "stamp_meta"


def _module_order(workflow: Path) -> list[str]:
    return re.findall(r"python -m src\.(\w+)", workflow.read_text(encoding="utf-8"))


def _workflows_running_both() -> list[Path]:
    out = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        order = _module_order(path)
        if HASH_CITING in order and LAST_WRITER in order:
            out.append(path)
    return out


def test_some_lane_actually_runs_both() -> None:
    """Guard the guard: if the module names change, the checks below
    would pass vacuously by matching nothing."""
    both = _workflows_running_both()
    assert both, (
        f"no workflow runs both src.{HASH_CITING} and src.{LAST_WRITER}; "
        "either a lane lost a step or these module names are stale")


def test_answers_are_generated_after_the_last_payload_rewrite() -> None:
    for path in _workflows_running_both():
        order = _module_order(path)
        # The LAST occurrence of each: a lane may run the writer early and
        # again late, and what matters is the final write.
        last_write = len(order) - 1 - order[::-1].index(LAST_WRITER)
        last_answer = len(order) - 1 - order[::-1].index(HASH_CITING)
        assert last_answer > last_write, (
            f"{path.name} runs src.{HASH_CITING} at step {last_answer} but "
            f"src.{LAST_WRITER} at step {last_write}. The answers would "
            "cite a source_sha256 that stamp_meta then invalidates, and "
            "the publish is refused by test_assistant_answers.")


def test_the_stamp_still_adds_a_field_build_index_omits() -> None:
    """The reason the order matters, asserted at its root.

    If build_index ever emitted a complete _meta, stamp_meta would be a
    no-op on latest.json and the ordering would stop mattering -- and
    this test should then be revisited rather than silently kept.
    """
    build = (ROOT / "src" / "build_index.py").read_text(encoding="utf-8")
    stamp = (ROOT / "src" / "stamp_meta.py").read_text(encoding="utf-8")
    meta_block = re.search(r"def _file_meta.*?\n\n", build, re.S)
    assert meta_block, "build_index._file_meta not found"
    assert '"source"' not in meta_block.group(0), (
        "build_index._file_meta now emits `source`; stamp_meta may have "
        "become a no-op on latest.json, so re-derive whether the step "
        "order above is still load-bearing")
    assert '"source"' in stamp, (
        "stamp_meta no longer adds `source`; re-derive the ordering rule")
