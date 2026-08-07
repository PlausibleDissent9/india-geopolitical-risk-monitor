"""Cache-busting versions must be current, and stamped late enough to stick.

THE BUG THIS EXISTS FOR
-----------------------
Every page linked `site.css?v=20260807f`, a hand-typed string. Inside
that sheet:

    @import url("tokens.css");

no version. tokens.css holds the palette, the type ramp and the motion
scale -- the file most likely to change, depended on by both sheets, and
the only one a browser would never be told had changed.

That is not a stale-look bug, it is a broken-page bug. A returning
visitor gets the new style.css saying

    animation: igrm-drift var(--dur-ambient) var(--ease-loop) infinite;

against a cached tokens.css that has never heard of either name. An
undefined custom property does not fall back to an earlier value -- the
declaration is invalid at computed-value time and is dropped whole. The
same shape as the 2026-07-31 gap-chart crash, where homepage palette
names resolved empty inside site.css.

Three pages (corrections, codebook, methodology) linked `site.css` with
no query string at all, and reveal.js/labels.js were pinned at
`?v=20260729a` while the files had moved on.

WHY A TEST AND A LANE STEP
--------------------------
`src/render_site.py` writes `href="site.css"` unversioned and runs every
night, so this cannot be fixed once by hand -- it would be undone by the
next publish. `python -m src.stamp_assets` runs in daily.yml after
everything that writes HTML, and the ordering assertion below is the
same check the stamp_meta step needed after I placed that one wrong
twice by reasoning about it.
"""
from __future__ import annotations

import re
from pathlib import Path

from src import stamp_assets

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
WORKFLOWS = ROOT / ".github" / "workflows"


def test_every_asset_reference_is_current():
    stale = stamp_assets.stamp(write=False)
    assert not stale, (
        "these asset references do not match their file's content hash, so "
        "a returning visitor would be served a new file against a cached "
        f"old one: {stale}. Fix with: python -m src.stamp_assets")


def test_stamping_is_a_fixed_point():
    """Stamping a reference changes the referrer's own bytes, so the
    naive one-pass version leaves the referrer stale. If a single check
    pass is clean, the set has converged."""
    assert stamp_assets.stamp(write=False) == []


def test_no_reference_is_left_unversioned():
    """The three pages that linked `site.css` bare were invisible to any
    check that only compared version strings to each other: they had no
    version to compare."""
    unversioned = []
    for page in sorted(DOCS.glob("*.html")):
        text = page.read_text(encoding="utf-8")
        for m in re.finditer(r"(?:href|src)\s*=\s*[\"']([\w./-]+\.(?:css|js))[\"']",
                             text):
            unversioned.append(f"{page.name}: {m.group(1)}")
    for sheet in ("site.css", "style.css"):
        text = (DOCS / sheet).read_text(encoding="utf-8")
        for m in re.finditer(r"@import\s+url\(\s*[\"']?([\w./-]+\.css)[\"']?\s*\)",
                             text):
            unversioned.append(f"{sheet}: @import {m.group(1)}")
    assert not unversioned, (
        f"loaded with no cache-busting version: {unversioned}")


def test_the_import_of_tokens_is_versioned_specifically():
    """Named on its own because it is the dangerous one. tokens.css is
    the shared dependency of both sheets; a cached copy of it breaks
    rules in the OTHER files, which is why the failure would not look
    like a caching problem."""
    for sheet in ("site.css", "style.css"):
        text = (DOCS / sheet).read_text(encoding="utf-8")
        assert re.search(r'@import url\("tokens\.css\?v=[0-9a-f]{8}"\)', text), (
            f"{sheet} imports tokens.css without a content version")


def test_stamp_assets_runs_after_everything_that_writes_html():
    """Position, not intent. render_site.py emits an unversioned link
    every night; a stamp step placed before it would be silently undone
    on the next publish, and nothing would go red."""
    daily = (WORKFLOWS / "daily.yml").read_text(encoding="utf-8")
    order = re.findall(r"python -m src\.(\w+)", daily)
    assert "stamp_assets" in order, "the asset stamp step is gone from daily.yml"
    idx = order.index("stamp_assets")

    writers = set()
    for path in (ROOT / "src").glob("*.py"):
        if path.stem == "stamp_assets":
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r'\.html"\s*\)?\.write_text|/ f"\{slug\}\.html"', text):
            writers.add(path.stem)

    after = [m for m in order[idx + 1:] if m in writers]
    assert not after, (
        f"these modules write HTML AFTER the asset stamp: {after}. Their "
        "pages ship with unversioned or stale stylesheet links, and a "
        "returning reader keeps the CSS they first saw.")
