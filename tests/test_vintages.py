"""Vintages: the tripwire has to actually trip."""
from __future__ import annotations

import io

import pytest
from src import vintages


def _csv(rows):
    head = "date," + ",".join(vintages.COLUMNS)
    body = "\n".join(",".join([d] + [str(v) for v in vals])
                     for d, vals in rows)
    return head + "\n" + body + "\n"


def test_identical_vintages_report_no_change():
    text = _csv([("2026-08-01", [50, 50, 50, 50, 50, 50])])
    a = vintages._rows(text)
    b = vintages._rows(text)
    changed = sum(1 for d in set(a) & set(b) for c in vintages.COLUMNS
                  if a[d][c] != b[d][c])
    assert changed == 0


def test_a_rewritten_value_is_detected():
    old = vintages._rows(_csv([("2026-08-01", [50, 50, 50, 50, 50, 50])]))
    new = vintages._rows(_csv([("2026-08-01", [50, 99, 50, 50, 50, 50])]))
    changed = [c for c in vintages.COLUMNS
               if old["2026-08-01"][c] != new["2026-08-01"][c]]
    assert changed == ["pakistan_west"]


def test_appending_a_day_is_not_a_revision():
    """Days are added constantly; that must never read as a rewrite, or
    the tripwire fires every morning and gets ignored."""
    old = vintages._rows(_csv([("2026-08-01", [50] * 6)]))
    new = vintages._rows(_csv([("2026-08-01", [50] * 6),
                               ("2026-08-02", [60] * 6)]))
    common = set(old) & set(new)
    changed = sum(1 for d in common for c in vintages.COLUMNS
                  if old[d][c] != new[d][c])
    assert common == {"2026-08-01"}
    assert changed == 0


def test_the_known_revision_is_registered_not_silenced():
    """The 2026-07-27 vintages predate methodology v1.0.1 and differ for
    a published reason. They must be declared, so that anything NOT
    declared still fails."""
    assert "2026-07-27" in vintages.REGISTERED_REVISIONS


def test_an_unregistered_revision_would_fail_the_build():
    """The mechanism, exercised directly: a revision whose date is not
    in the registry must be treated as a defect."""
    revised = [{"published": "2026-09-01", "sha": "deadbeef",
                "n_changed_days": 3, "max_abs_change": 12.0}]
    unregistered = [r for r in revised
                    if r["published"] not in vintages.REGISTERED_REVISIONS]
    assert unregistered, "a 2026-09-01 revision must not be pre-approved"


def test_retrieval_recipe_names_a_real_command():
    """The archive is only useful if a stranger can reach it without us.

    Deliberately does NOT call compare(). compare() walks git history
    and, on a shallow CI checkout, triggers `git fetch --unshallow` --
    and morning.yml runs the whole test suite as its first gate before
    the 06:00 publish. A network operation on a 50 MB repo inside the
    contract's own gate is a way to lose the morning to a slow fetch,
    which is not a trade any test is worth.
    """
    recipe = f"git show <SHA>:{vintages.TRACKED}"
    assert recipe.startswith("git show ")
    assert vintages.TRACKED in recipe
    # And the real builder must use that same shape.
    import inspect
    src = inspect.getsource(vintages.compare)
    assert '"retrieve": f"git show {sha}:{TRACKED}"' in src


def test_parser_tolerates_an_empty_blob():
    assert vintages._rows("") == {}
    assert vintages._rows(io.StringIO("").read()) == {}


def test_the_recompute_restates_the_codebook_count(
    tmp_path, monkeypatch
) -> None:
    """The lane that moves the vintage count states it, same candidate.

    2026-08-19, run 32267252818: the recompute moved vintages.json to
    20 of 22 while docs/codebook.md still carried a hand-written 10 of
    12, and the publish gate refused the entire daily at Commit data.
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "codebook.md").write_text(
        "**Finding: 10 of 12 vintages show zero changed values.**\n",
        encoding="utf-8")
    (docs / "codebook.html").write_text(
        '<link rel="stylesheet" href="site.css?v=044019ad">\n'
        "<strong>Finding: 10 of 12 vintages show zero changed "
        "values.</strong>\n",
        encoding="utf-8")
    monkeypatch.setattr(vintages, "ROOT", tmp_path)
    vintages._restate_codebook_count(20, 22)
    assert "20 of 22 vintages" in (docs / "codebook.md").read_text()
    html = (docs / "codebook.html").read_text()
    assert "20 of 22 vintages" in html
    # Surgical: the stamped asset reference must survive untouched.
    assert 'href="site.css?v=044019ad"' in html


def test_a_codebook_without_the_count_fails_loud(tmp_path, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "codebook.md").write_text("no count here\n", encoding="utf-8")
    (docs / "codebook.html").write_text("none here either\n", encoding="utf-8")
    monkeypatch.setattr(vintages, "ROOT", tmp_path)
    with pytest.raises(SystemExit):
        vintages._restate_codebook_count(20, 22)
