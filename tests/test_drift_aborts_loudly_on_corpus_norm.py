"""The drift lane's one hard dependency must fail with a name, not exit 1.

Runs #14, #15 and #16 of the weekly drift lane died with nothing but
"Process completed with exit code 1". Diagnosis required reproducing the
whole 25-minute command locally, where it SUCCEEDED -- the failure is the
GitHub runner's shared IP being throttled by GDELT until the retry ladder
exhausts, at the one fetch in `drift()` with no soft path: the corpus
norm, which is the promised denominator and must not fail soft.

So the contract is: artlist sampling degrades per-year with a printed
gap (already the case, kept); the corpus-norm fetch aborts with a printed
diagnosis and exit code 4, which drift.yml maps to a readable annotation.
"""
from __future__ import annotations

import pytest
from src import fetch_gdelt, validate


def test_corpus_norm_failure_exits_4_with_a_diagnosis(monkeypatch, capsys):
    def throttled(*args, **kwargs):
        raise RuntimeError("GDELT timelinevolraw failed after 6 attempts: "
                           "HTTP 429 rate limit: Please limit request")
    monkeypatch.setattr(fetch_gdelt, "fetch_corpus_norm", throttled)
    with pytest.raises(SystemExit) as exit_info:
        validate.drift()
    assert exit_info.value.code == 4, (
        "the corpus-norm abort must use its dedicated exit code; drift.yml "
        "maps 4 to the annotation that makes this failure readable")
    out = capsys.readouterr().out
    assert "drift ABORTED at the corpus-norm fetch" in out
    assert "429" in out, "the diagnosis must carry the underlying error"


def test_other_errors_are_not_swallowed_into_the_named_abort(monkeypatch):
    """Only the corpus-norm RuntimeError gets the named path. A TypeError
    from a code defect must still crash as itself -- a diagnosis that
    absorbs every failure stops meaning anything."""
    def broken(*args, **kwargs):
        raise TypeError("a genuine bug, not weather")
    monkeypatch.setattr(fetch_gdelt, "fetch_corpus_norm", broken)
    with pytest.raises(TypeError):
        validate.drift()
