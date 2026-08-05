"""Every statistic the site's pages promise must exist in a published
payload. 2026-08-05: the validation page said "Coverage drift" and
showed "Not yet computed" for weeks because the drift mode existed but
was never run -- a promised-but-absent statistic is exactly the kind of
gap a hostile reviewer finds in one read (founder QA, MI1). This
registry is the contract: add a row when a page starts naming a new
statistic, and never remove a row without removing the page text."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"

# (payload file, key path into the payload, page that promises it)
PROMISED = [
    ("validation.json", ("hit_rate",), "validation.html: Event hit-rate"),
    ("validation.json", ("placebo",), "validation.html: Placebo channels"),
    ("validation.json", ("robustness",), "validation.html: Dictionary robustness"),
    ("validation.json", ("drift", "mean_daily_corpus_by_year"),
     "validation.html: Coverage drift"),
    ("validation.json", ("drift", "share_vs_corpus_corr"),
     "validation.html: Coverage drift"),
    ("precision.json", ("calibration_threshold",),
     "methodology.html: precision audit"),
    ("precision.json", ("author_labels_n",),
     "methodology.html: precision audit author labels"),
    ("event_study.json", (), "analysis.html: event study"),
    ("latest.json", ("date",), "index.html: headline score"),
]


@pytest.mark.parametrize("fname,path,promise", PROMISED,
                         ids=[p[2] for p in PROMISED])
def test_promised_statistic_exists(fname: str, path: tuple, promise: str):
    fpath = SITE_DATA / fname
    assert fpath.exists(), (
        f"{promise} is named on the site but {fname} is not published"
    )
    node = json.loads(fpath.read_text(encoding="utf-8"))
    walked = []
    for key in path:
        walked.append(key)
        assert isinstance(node, dict) and key in node, (
            f"{promise} is named on the site but {fname} has no "
            f"'{'.'.join(walked)}' -- the page is promising a statistic "
            f"the payload does not carry"
        )
        node = node[key]
    assert node not in (None, {}, []), (
        f"{promise}: {fname} '{'.'.join(path) or '(root)'}' is empty"
    )
