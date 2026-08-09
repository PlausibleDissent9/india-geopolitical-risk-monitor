"""The cross-runtime parity tests must not silently become no-ops in CI.

WHAT THIS IS ABOUT
Release integrity binds a signature to a digest computed in Python, and a
browser re-computes that digest with docs/typed-canonical.js. Whether those
two implementations agree is the single property that most needs
cross-runtime testing, and two tests guard it:

    tests/test_nary_association_trace.py
        test_trace_tuple_wrapper_matches_browser_typed_canonical_if_available
    tests/test_shock_compiler.py
        test_public_shock_script_parses_when_node_is_available

Both open with `if shutil.which("node") is None: pytest.skip(...)`. That is
the right behaviour on a developer laptop: a Mac without Node should not fail
the suite over a missing optional runtime, and the `_if_available` naming is
honest about it.

THE HOLE
`.github/workflows/ci.yml` never installs Node and never asserts it exists.
The parity guarantee therefore rests on Node happening to be preinstalled on
GitHub's runner image -- undeclared, unpinned, and outside this repo's
control. If that image changed, or the job moved to a slim container, both
tests would skip, the suite would stay green, and nothing anywhere would say
the parity check had stopped running.

That is the shape this repo has paid for twice already: a check that cannot
fail the way the real one does. scripts/gate.sh exists because of it.

Found 2026-08-09 while re-running the Shock/OGES/Capability/Evolution suites
as an independent reviewer: 126 passed, 2 skipped, and the two skips were
exactly the cross-runtime tests.

WHAT THIS FILE DOES
Local runs are unchanged -- skipping without Node stays correct. In CI, a
missing Node becomes a failure, because there the skip is not a developer
convenience, it is the guarantee quietly switching itself off.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Tests that verify a Python implementation against its JavaScript twin, and
# that skip themselves when Node is absent.
PARITY_TESTS = {
    "tests/test_nary_association_trace.py":
        "test_trace_tuple_wrapper_matches_browser_typed_canonical_if_available",
    "tests/test_shock_compiler.py":
        "test_public_shock_script_parses_when_node_is_available",
}


def _in_ci() -> bool:
    """GitHub Actions sets CI=true; so does almost every other runner."""
    return os.environ.get("CI", "").lower() == "true"


def test_the_parity_tests_still_exist_and_still_guard_on_node() -> None:
    """If one is renamed or its guard removed, the assertion below would
    be protecting a test that no longer does this job."""
    for relative, name in PARITY_TESTS.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert f"def {name}(" in text, (
            f"{relative} no longer defines {name}; update PARITY_TESTS or "
            "this file is guarding nothing")
        guard = re.search(
            rf"def {re.escape(name)}\(.*?\n(.*?)(?=\ndef |\Z)", text, re.S)
        assert guard and 'shutil.which("node")' in guard.group(1), (
            f"{name} no longer skips on a missing node; if it now fails "
            "outright, this file is redundant and should be deleted rather "
            "than left as decoration")


@pytest.mark.skipif(not _in_ci(), reason="local runs may skip parity tests")
def test_node_is_present_in_ci_so_the_parity_tests_are_not_skipped() -> None:
    assert shutil.which("node") is not None, (
        "Node is missing in CI, so both cross-runtime parity tests skipped "
        "and the suite stayed green while the Python/JavaScript digest "
        "agreement went untested. Add actions/setup-node to ci.yml, or "
        "install node in the checks job. Do not delete this assertion: the "
        "failure mode it catches is silent by construction.")
