"""A corpus pass that cannot finish must still leave progress behind.

WHAT WENT WRONG
The extended receipts scan reads up to 1440 minute-files for a day, and
`_cache_save` ran only after the whole loop. So a pass that could not
finish inside the workflow step's cap banked nothing, and the next run
began again at the first file. That does not make receipts slow, it makes
them impossible: once a day's corpus outgrew the budget the lane could
never complete another pass, and every run afterwards spent the same
hour reaching the same distance and threw it away.

Measured 2026-08-09 on the two most recent daily runs that reached this
step: daily #99 and daily #102 each recorded exactly 60.2 minutes for it,
which is its 60-minute cap, and receipts.json had not been rewritten
since 2026-08-07 -- three days of published receipts describing
2026-08-06 while the step burned an hour every night.

The step is `continue-on-error`, so none of that turned anything red. It
is the same shape as the multilingual lane's starvation: work that looks
like progress, repeated identically, converging on nothing.

These tests pin the property that fixes it -- an interrupted pass is
resumable -- without touching the network, by driving collect_corpus with
a stubbed fetcher and a zero budget.
"""
from __future__ import annotations

import gzip
import json
import re
from datetime import date
from pathlib import Path

import pytest
from src import receipts_ngrams

DAY = date(2026, 8, 8)
SPECS = {"pakistan_west": {"phrases": [("line", "of", "control")]}}


def _minute_file(docid: str) -> tuple[bytes, bytes]:
    """One minute-file pair carrying a single matching English article."""
    toc = json.dumps({"lang": "en", "ID": docid, "url": f"https://x/{docid}",
                      "title": f"title {docid}", "date": "20260808"})
    ngram = f"{docid}\tline of control\n"
    return (gzip.compress(toc.encode()), gzip.compress(ngram.encode()))


def test_an_interrupted_pass_banks_what_it_read(monkeypatch, tmp_path):
    """The defect, as one assertion.

    The old pass saved only after the loop, so an interrupted scan wrote
    no cache at all and the next run began at the first file again. Here
    the clock expires part-way through: what was read must be on disk,
    marked incomplete, with the files already read recorded."""
    stamps = [f"2026080800{i:02d}" for i in range(10)]
    monkeypatch.setattr(receipts_ngrams, "CORPUS_CACHE", tmp_path)
    monkeypatch.setattr(receipts_ngrams, "SCAN_DEADLINE_S", 100)
    monkeypatch.setattr(receipts_ngrams, "_day_minute_files",
                        lambda day, samples=None: list(stamps))
    monkeypatch.setattr(receipts_ngrams, "scoring_stamps",
                        lambda st, day: set(st))
    monkeypatch.setattr(receipts_ngrams, "prefetch_pairs",
                        lambda to_read: ((ts, *_minute_file(f"d{ts}"))
                                         for ts in to_read))

    # A clock that runs out after three files: one call sets the deadline,
    # then one per loop iteration.
    ticks = iter([0, 0, 0, 0, 10_000] + [10_000] * 50)
    monkeypatch.setattr(receipts_ngrams.time, "monotonic", lambda: next(ticks))

    corpus = receipts_ngrams.collect_corpus(DAY, SPECS, extended=True)
    assert corpus is not None, "a partial pass with data must still return it"
    assert corpus["complete"] is False
    assert len(corpus["done_stamps"]) == 3, (
        f"expected three files read, got {sorted(corpus['done_stamps'])}")
    assert corpus["n_samples"] == 3, "n_samples must count files actually read"

    on_disk = receipts_ngrams._cache_load(DAY, extended=True)
    assert on_disk is not None, (
        "an interrupted pass banked nothing -- the next run restarts at zero, "
        "which is the original defect")
    assert on_disk["complete"] is False
    assert on_disk["done_stamps"] == set(stamps[:3])


def test_a_cache_without_a_flag_is_treated_as_complete(tmp_path, monkeypatch):
    """Caches written before partial passes existed carry no flag and were
    whole passes by construction. Reading them as incomplete would rescan
    every settled day in the archive."""
    monkeypatch.setattr(receipts_ngrams, "CORPUS_CACHE", tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    legacy = {"n_docs_sampled": 5, "n_samples": 3, "extended": True,
              "scored_stamps": ["a"], "india": ["k"],
              "matched": {"pakistan_west": ["k"]}, "meta": {}}
    (tmp_path / f"{DAY.isoformat()}-extended.json").write_text(
        json.dumps(legacy), encoding="utf-8")
    loaded = receipts_ngrams._cache_load(DAY, extended=True)
    assert loaded is not None
    assert loaded["complete"] is True
    assert loaded["done_stamps"] == set()


def test_a_partial_cache_round_trips(tmp_path, monkeypatch):
    """done_stamps and the completeness flag must survive serialisation,
    or a resume silently rescans from the beginning."""
    monkeypatch.setattr(receipts_ngrams, "CORPUS_CACHE", tmp_path)
    corpus = {"n_docs_sampled": 7, "n_samples": 2, "extended": True,
              "scored_stamps": {"s1", "s2"}, "india": {"k1"},
              "matched": {"pakistan_west": {"k1"}}, "meta": {},
              "done_stamps": {"s1", "s2"}, "complete": False}
    receipts_ngrams._cache_save(DAY, corpus, extended=True)
    back = receipts_ngrams._cache_load(DAY, extended=True)
    assert back is not None
    assert back["complete"] is False
    assert back["done_stamps"] == {"s1", "s2"}


def test_a_resume_does_not_reread_finished_files(monkeypatch, tmp_path):
    """The point of banking progress: the second pass asks only for the
    files the first one did not reach."""
    stamps = [f"2026080800{i:02d}" for i in range(10)]
    monkeypatch.setattr(receipts_ngrams, "CORPUS_CACHE", tmp_path)
    monkeypatch.setattr(receipts_ngrams, "SCAN_DEADLINE_S", 3600)
    monkeypatch.setattr(receipts_ngrams, "_day_minute_files",
                        lambda day, samples=None: list(stamps))
    monkeypatch.setattr(receipts_ngrams, "scoring_stamps",
                        lambda st, day: set(st))
    tmp_path.mkdir(parents=True, exist_ok=True)
    partial = {"n_docs_sampled": 4, "n_samples": 6, "extended": True,
               "scored_stamps": stamps, "india": [],
               "matched": {"pakistan_west": []}, "meta": {},
               "done_stamps": stamps[:6], "complete": False}
    (tmp_path / f"{DAY.isoformat()}-extended.json").write_text(
        json.dumps(partial), encoding="utf-8")

    asked: list[str] = []

    def fake_pairs(to_read):
        for ts in to_read:
            asked.append(ts)
            yield ts, None, None

    monkeypatch.setattr(receipts_ngrams, "prefetch_pairs", fake_pairs)
    receipts_ngrams.collect_corpus(DAY, SPECS, extended=True)
    assert asked == stamps[6:], (
        f"resume re-read finished files: asked for {asked}")


def test_a_complete_cache_is_served_without_rescanning(monkeypatch, tmp_path):
    """A finished day must not be scanned again just because the resume
    path exists."""
    monkeypatch.setattr(receipts_ngrams, "CORPUS_CACHE", tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    done = {"n_docs_sampled": 9, "n_samples": 10, "extended": True,
            "scored_stamps": [], "india": [],
            "matched": {"pakistan_west": []}, "meta": {},
            "done_stamps": [f"s{i}" for i in range(10)], "complete": True}
    (tmp_path / f"{DAY.isoformat()}-extended.json").write_text(
        json.dumps(done), encoding="utf-8")

    def explode(_to_read):
        raise AssertionError("a complete cache must not trigger a scan")

    monkeypatch.setattr(receipts_ngrams, "prefetch_pairs", explode)
    monkeypatch.setattr(receipts_ngrams, "_day_minute_files",
                        lambda day, samples=None: [])
    got = receipts_ngrams.collect_corpus(DAY, SPECS, extended=True)
    assert got is not None and got["n_docs_sampled"] == 9


def test_the_budget_fits_inside_the_steps_cap():
    """The daily scoring-depth scan leaves time to bank and derive."""
    wf = (Path(__file__).resolve().parents[1]
          / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
    m = re.search(
        r"Receipts at scoring depth.*?timeout-minutes:\s*(\d+).*?"
        r"IGRM_RECEIPTS_DEADLINE_S:\s*[\"']?(\d+)",
        wf,
        re.S,
    )
    assert m, "cannot find the receipts step's timeout in daily.yml"
    cap = int(m.group(1)) * 60
    budget = int(m.group(2))
    assert budget < cap, (
        f"scan budget {budget}s is not inside the "
        f"{cap}s step cap")
    assert cap - budget >= 15 * 60, (
        "leave at least 15 minutes for the four commands that follow the "
        "scan in the same step")


def test_an_incomplete_scan_can_never_reach_public_assembly(monkeypatch):
    corpus = {
        "n_docs_sampled": 10,
        "n_samples": 2,
        "extended": True,
        "scored_stamps": set(),
        "india": set(),
        "matched": {},
        "meta": {},
        "done_stamps": {"a", "b"},
        "complete": False,
    }
    monkeypatch.setattr(receipts_ngrams, "collect_corpus", lambda *a, **k: corpus)
    monkeypatch.setattr(
        receipts_ngrams.sys,
        "argv",
        ["receipts_ngrams", "--extended", DAY.isoformat()],
    )

    with pytest.raises(receipts_ngrams.IncompleteCorpusScan):
        receipts_ngrams.main()


def test_a_located_but_missing_pair_is_retried_not_marked_done(
    monkeypatch, tmp_path,
):
    stamps = ["20260808000100", "20260808001600"]
    good_toc, good_ngram = _minute_file("d1")
    monkeypatch.setattr(receipts_ngrams, "CORPUS_CACHE", tmp_path)
    monkeypatch.setattr(receipts_ngrams, "SCAN_DEADLINE_S", 3600)
    monkeypatch.setattr(
        receipts_ngrams,
        "_day_minute_files",
        lambda day, samples=None: list(stamps),
    )
    monkeypatch.setattr(
        receipts_ngrams,
        "prefetch_pairs",
        lambda requested: iter([
            (stamps[0], good_toc, good_ngram),
            (stamps[1], None, None),
        ]),
    )

    corpus = receipts_ngrams.collect_corpus(DAY, SPECS, extended=True)

    assert corpus is not None
    assert corpus["complete"] is False
    assert corpus["done_stamps"] == {stamps[0]}
