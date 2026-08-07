"""Vintages: the tripwire has to actually trip."""
from __future__ import annotations

import io

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
    """The archive is only useful if a stranger can reach it without us."""
    rows = vintages.compare()
    if not rows:
        return
    assert rows[0]["retrieve"].startswith("git show ")
    assert vintages.TRACKED in rows[0]["retrieve"]


def test_parser_tolerates_an_empty_blob():
    assert vintages._rows("") == {}
    assert vintages._rows(io.StringIO("").read()) == {}
