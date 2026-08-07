"""The stranger's replication notebook must execute, assert, and stay blind.

`notebooks/replicate_headlines.ipynb` recomputes the site's headline claims
-- the composite rebuild, the registered hit rate and its base rates, a
vintage reconstruction, a negative-results row -- from the published files
alone, and every section ends in an assert. That only means something if
the notebook actually RUNS on every CI push: an unexecuted notebook is
documentation wearing a lab coat, and it rots the day after it is written.

So this test executes it, cell by cell, with a dependency-free runner
(nbclient is not in the project's pinned requirements, and the notebook is
plain Python by design -- no magics, no display calls -- precisely so that
`exec` of its code cells IS its execution model).

The guards around the run keep the notebook honest the same way the blind
replicator's tests keep it blind:

  * enough cells must END in asserts -- a notebook that only prints cannot
    fail, and a replication that cannot fail is a brochure;
  * it may import only the standard library and numpy, never `src` -- a
    stranger does not have the pipeline, and a notebook that peeks at it
    reproduces the pipeline by construction and measures nothing;
  * it may read only published files -- docs/data payloads and the
    codebook -- for the same reason;
  * its prose may contain no digits at all, so every number a reader sees
    was printed by a cell they can re-run, never hand-typed and never
    stale.
"""
from __future__ import annotations

import ast
import json
import os
import re
import time
import traceback
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "replicate_headlines.ipynb"

# A stranger's toolkit: the standard library plus the scientific-Python
# baseline. Never src -- that is the whole point.
ALLOWED_IMPORTS = {"csv", "json", "re", "datetime", "pathlib", "numpy"}

# What a stranger can download. Everything the notebook opens must be one
# of these published names; data/raw and src are not theirs.
PUBLISHED_DATA_READS = {
    "shares.csv", "history.csv", "episodes.csv", "validation.json",
    "detection_baselines.json", "vintages_panel.json", "negative_results.json",
}
PUBLISHED_DOC_READS = {"codebook.md"}

# The notebook promises one assert-terminated section per headline claim:
# composite rebuild, hit-rate context, vintage recipe, register row.
MIN_ASSERT_CELLS = 4

# The suite gates every push, so the notebook must stay cheap. Trim the
# notebook if this trips; do not skip the test.
MAX_SECONDS = 60


def _cells(cell_type: str) -> list[str]:
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return ["".join(c["source"]) for c in nb["cells"]
            if c["cell_type"] == cell_type]


def test_every_code_cell_executes_without_error_and_fast() -> None:
    """Run the notebook the way a stranger would: top to bottom."""
    cells = _cells("code")
    assert cells, "the notebook has no code cells; nothing was replicated"

    namespace: dict = {"__name__": "__main__"}
    previous_cwd = os.getcwd()
    started = time.monotonic()
    # Execute from notebooks/ so the notebook's path discovery is exercised
    # from the directory a reader would launch it in.
    os.chdir(NOTEBOOK.parent)
    try:
        for i, source in enumerate(cells, 1):
            try:
                exec(compile(source, f"{NOTEBOOK.name} [code cell {i}]",
                             "exec"), namespace)
            except Exception:
                pytest.fail(
                    f"code cell {i} of {len(cells)} raised -- the published "
                    f"numbers no longer reproduce from the published files:\n"
                    f"{traceback.format_exc()}")
    finally:
        os.chdir(previous_cwd)

    elapsed = time.monotonic() - started
    assert elapsed < MAX_SECONDS, (
        f"the notebook took {elapsed:.1f}s; the budget is {MAX_SECONDS}s "
        "because this runs on every push. Trim the notebook's work -- do "
        "not skip this test, and do not raise the budget to clear a red "
        "run.")


def test_enough_cells_end_in_asserts() -> None:
    """A replication that cannot fail is a brochure. Counted structurally
    (ast), not by grepping for the word 'assert' in comments."""
    with_asserts = [
        i for i, source in enumerate(_cells("code"), 1)
        if any(isinstance(node, ast.Assert)
               for node in ast.walk(ast.parse(source)))
    ]
    assert len(with_asserts) >= MIN_ASSERT_CELLS, (
        f"only cells {with_asserts} contain asserts; the notebook promises "
        f"at least {MIN_ASSERT_CELLS} assert-terminated sections, one per "
        "headline claim. A section that lost its assert can no longer fail, "
        "which is the quiet way this artifact dies.")


def test_the_notebook_never_imports_the_pipeline() -> None:
    """A stranger does not have src/. A notebook that imports it reproduces
    the pipeline by construction and measures nothing -- the blind-spot
    tautology again."""
    for i, source in enumerate(_cells("code"), 1):
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            for module in modules:
                top = module.split(".")[0]
                assert top in ALLOWED_IMPORTS, (
                    f"code cell {i} imports {module!r}; the notebook may "
                    f"use only {sorted(ALLOWED_IMPORTS)}. If the "
                    "replication needs the pipeline, the codebook is not "
                    "sufficient -- fix the codebook, not the blindness.")


def test_the_notebook_reads_only_published_files() -> None:
    """Same rule the blind replicator lives under, same vacuous-truth
    guard: the detection regex must match something, or a refactor of how
    cells open files would pass this test on an empty set."""
    source = "\n".join(_cells("code"))
    data_reads = set(re.findall(r'DATA\s*/\s*"([\w.]+)"', source))
    doc_reads = set(re.findall(r'DATA\.parent\s*/\s*"([\w.]+)"', source))
    assert data_reads, (
        "the read-detection regex matched nothing; the notebook stopped "
        "opening files as DATA / \"name\" and this guard went blind")
    assert data_reads <= PUBLISHED_DATA_READS, (
        f"the notebook reads unpublished data: "
        f"{sorted(data_reads - PUBLISHED_DATA_READS)}")
    assert doc_reads <= PUBLISHED_DOC_READS, (
        f"the notebook reads unpublished docs: "
        f"{sorted(doc_reads - PUBLISHED_DOC_READS)}")
    assert "data/raw" not in source, "reaches into the private store"


def test_the_prose_hand_types_no_numbers() -> None:
    """Every number a reader sees must come out of a cell they can re-run.
    The enforceable version of that rule is blunt: markdown cells contain
    no digits, so there is nothing in the prose to go stale."""
    for i, source in enumerate(_cells("markdown"), 1):
        digits = sorted(set(re.findall(r"\d", source)))
        assert not digits, (
            f"markdown cell {i} contains digits {digits}; numbers belong "
            "in code-cell output, where re-running refreshes them. A "
            "hand-typed number is a claim the notebook cannot defend.")
