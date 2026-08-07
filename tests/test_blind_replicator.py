"""The replicator must stay blind, and the replication must stay exact.

The value of `src/blind_replicator.py` is entirely in what it is NOT
allowed to see. A replicator that imports `src.scores` reproduces the
pipeline by construction and proves nothing -- it is the blind-spot
tautology (523/523 true because the test searched only where the answer
was) wearing a different hat. So the first test here reads the module's
own imports, and the rest check that the reproduction is still exact.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from src import blind_replicator as br

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "src" / "blind_replicator.py"

# The only project import permitted: stamp_meta supplies the licence and
# citation fields every payload carries. It computes no score, reads no
# share, and knows nothing about the transform.
ALLOWED_PROJECT_IMPORTS = {"stamp_meta"}


def test_the_replicator_cannot_see_the_pipeline():
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("src"):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("src."):
                    imported.add(a.name.split(".", 1)[1])

    leaked = imported - ALLOWED_PROJECT_IMPORTS
    assert not leaked, (
        f"blind_replicator imports project code: {sorted(leaked)}. A "
        "replicator that can see the pipeline reproduces it by "
        "construction and measures nothing. If the transform here is "
        "wrong, fix the CODEBOOK until a stranger could get it right.")


def test_it_reads_only_published_files():
    """A stranger has docs/. Anything under data/ or src/ is not theirs."""
    text = MODULE.read_text(encoding="utf-8")
    body = re.sub(r'""".*?"""', "", text, flags=re.S)  # docstrings are prose
    reads = re.findall(r"SITE_DATA\s*/\s*\"([\w.]+)\"", body)
    assert set(reads) <= {"shares.csv", "history.csv", "replication.json"}, (
        f"reads something a stranger could not download: {sorted(set(reads))}")
    assert "data/raw" not in body, "reaches into the private store"


def test_the_published_series_is_exactly_reproducible():
    """The headline claim, recomputed every run rather than remembered.

    Measured 2026-08-07: 19830 of 19830 published values, from
    docs/data/shares.csv and the transform as stated in the codebook,
    with no access to src/scores.py.
    """
    results = br.run_all()
    best = results[0]
    assert best["agreement"] >= br.MIN_AGREEMENT, (
        f"an independent rebuild from the published codebook reproduces "
        f"{best['n_agree']}/{best['n_compared']} values "
        f"({best['agreement']:.4%}); the floor is {br.MIN_AGREEMENT:.4%}. "
        "Either the pipeline changed without the codebook changing, or "
        "the codebook was never sufficient to reproduce the number.")


def test_the_floor_has_not_been_lowered():
    """The one way to make this module useless is to relax it after a
    red run. Naming the value in a test means moving it requires editing
    two files and explaining yourself in both."""
    assert br.MIN_AGREEMENT == 1.0, (
        "MIN_AGREEMENT is no longer exact. An exact reproduction is "
        "either true or it is not; a fractional floor lets a real "
        "divergence sit under it indefinitely.")


def test_the_winning_convention_beats_the_alternatives_decisively():
    """If two readings of the codebook scored alike, 'measurement
    resolved the ambiguity' would be a coin toss dressed up as a
    finding. Measured margin: 100% against 65.3%."""
    results = br.run_all()
    best, runner_up = results[0], results[1]
    margin = best["agreement"] - runner_up["agreement"]
    assert margin > 0.2, (
        f"the best reading of the codebook ({best['percentile_convention']}"
        f"/{best['window_convention']}, {best['agreement']:.4%}) is only "
        f"{margin:.4%} ahead of the next ({runner_up['agreement']:.4%}), "
        "which is not enough to call the ambiguity settled by evidence.")


def test_every_ambiguity_the_replicator_found_is_documented_in_the_codebook():
    """The replicator's real output is not the 100%, it is the list of
    sentences the codebook was missing. Finding them and not writing
    them down would waste the whole exercise."""
    codebook = (ROOT / "docs" / "codebook.html").read_text(encoding="utf-8")
    for phrase, why in [
        ("at or below", "the tie convention (weak, not strict or midrank)"),
        ("calendar", "the window basis (calendar days, not observations)"),
        ("half", "the half-way rounding rule"),
    ]:
        assert phrase.lower() in codebook.lower(), (
            f"the codebook does not state {why}; a stranger cannot "
            "reproduce the series without it, which is exactly what the "
            "replicator measured.")
