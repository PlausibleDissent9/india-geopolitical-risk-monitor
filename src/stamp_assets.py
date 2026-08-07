"""Cache-busting versions, derived from content instead of typed by hand.

WHAT WAS WRONG
--------------
Every page linked `site.css?v=20260807f`, and inside that sheet sat

    @import url("tokens.css");

with no version at all. tokens.css is the single source of truth for the
palette, the type ramp and the motion scale -- the file most likely to
change and the one every other sheet depends on -- and it was the one
file no reader would ever be told had changed.

The failure mode is not a stale look, it is a BROKEN one. A returning
visitor gets the new style.css, which says

    animation: igrm-drift var(--dur-ambient) var(--ease-loop) infinite;

against a cached old tokens.css that has never heard of --dur-ambient or
--ease-loop. An undefined custom property makes the whole declaration
invalid at computed-value time, so the rule does not fall back, it
vanishes. This is the same shape as the 2026-07-31 gap-chart crash,
where homepage palette names resolved empty inside site.css.

Three further pages -- corrections, codebook, methodology -- linked
`site.css` with no query string whatsoever, so for anyone who had
visited before, those three were frozen at whatever CSS they first saw.

And the JS was worse: reveal.js and labels.js were pinned at
`?v=20260729a` while the files themselves had moved on.

WHY DERIVE IT
-------------
A hand-typed version is one more thing two places have to agree about,
and this project has now been bitten four times by exactly that: two
copies of the palette, two copies of the keyframes, two copies of the
chart colours, a doc claiming a spacing scale that did not exist. The
answer each time was to compute the second copy instead of maintaining
it.

So: the version of an asset IS the first 8 hex of the sha256 of its
bytes. Change the file, the version changes. Do not change it, and it
does not. Nobody has to remember anything, and `test_asset_versions.py`
recomputes the whole set and fails with the exact command to fix it.

ORDER MATTERS
-------------
tokens.css is imported BY style.css and site.css, so stamping the import
line changes those sheets' own bytes and therefore their own hashes.
Leaves are stamped first and referrers second, and the result is a fixed
point -- running this twice in a row is a no-op, which the test also
checks.

  python -m src.stamp_assets            rewrite references in place
  python -m src.stamp_assets --check    exit 1 if anything is stale
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
QUOTES = "\"'()"

# Stamped in dependency order: an asset must appear after everything it
# imports, because stamping a reference changes the referrer's bytes.
ASSETS = [
    "fonts.css",
    "tokens.css",
    "site.css",
    "style.css",
    "vendor/chart.umd.min.js",
    "motion.js",
    "labels.js",
    "reveal.js",
    "app.js",
]

# Files that may contain a reference: every page, plus the two sheets
# that @import tokens.css and fonts.css.
def _referrers() -> list[Path]:
    return sorted(DOCS.glob("*.html")) + [DOCS / "site.css", DOCS / "style.css"]


def version_of(asset: str) -> str:
    return hashlib.sha256((DOCS / asset).read_bytes()).hexdigest()[:8]


def _pattern(asset: str) -> re.Pattern[str]:
    """Match the asset only where it is actually LOADED.

    The first version anchored on any quote or paren, which stamped a
    prose comment in site.css reading "(style.css): paper / ink / rule".
    That is not a reference, and versioning it did real damage: site.css
    then changed its bytes every time style.css changed, so every one of
    the twenty-one pages was re-stamped for a documentation sentence.

    A cache-busting query belongs on `href=`, `src=` and `url(` and
    nowhere else. Prose that happens to name a file is prose.
    """
    return re.compile(
        r"(?P<lead>(?:href|src)\s*=\s*[\"']|url\(\s*[\"']?)"
        + re.escape(asset)
        + r"(?:\?v=[^\"')\s]*)?(?P<close>[\"']|(?=\s*\)))")


def stamp(write: bool) -> list[str]:
    """Rewrite every reference; return the list of stale ones found."""
    stale: list[str] = []
    for asset in ASSETS:
        path = DOCS / asset
        if not path.exists():
            raise SystemExit(f"[stamp_assets] listed asset is missing: {asset}")
        want = version_of(asset)
        pat = _pattern(asset)
        for ref in _referrers():
            text = ref.read_text(encoding="utf-8")
            # Bound explicitly: the lambda closes over the loop variables
            # and is only safe because sub() runs inside this iteration.
            # That is the kind of "correct by accident" this project keeps
            # finding, so it is made correct on purpose.
            def _sub(m: re.Match[str], a: str = asset, v: str = want) -> str:
                return f"{m.group('lead')}{a}?v={v}{m.group('close')}"

            new = pat.sub(_sub, text)
            if new != text:
                # Report per reference, not per file, so the message names
                # what actually moved.
                for m in pat.finditer(text):
                    if f"?v={want}" not in m.group(0):
                        was = m.group(0).strip(QUOTES)
                        stale.append(f"{ref.name}: {was} -> {asset}?v={want}")
                if write:
                    ref.write_text(new, encoding="utf-8")
    return stale


def main() -> None:
    check = "--check" in sys.argv
    stale = stamp(write=not check)

    if check:
        if stale:
            for s in stale:
                print(f"[stamp_assets] stale: {s}")
            raise SystemExit(
                f"[stamp_assets] {len(stale)} asset references are stale. A "
                "returning visitor would get a new sheet against a cached "
                "old one, and an undefined custom property does not fall "
                "back -- the whole declaration is dropped. Fix with: "
                "python -m src.stamp_assets")
        print(f"[stamp_assets] all references current "
              f"({len(ASSETS)} assets)")
        return

    if stale:
        for s in stale:
            print(f"[stamp_assets] {s}")
    # Stamping a reference changes the referrer's own bytes, so a single
    # pass can leave the referrer's own version out of date. Iterate to a
    # fixed point rather than assuming one pass is enough.
    for _ in range(5):
        again = stamp(write=True)
        if not again:
            break
        for s in again:
            print(f"[stamp_assets] {s}")
    else:
        raise SystemExit("[stamp_assets] did not reach a fixed point in 5 "
                         "passes; a reference is probably self-referential")
    print(f"[stamp_assets] stamped {len(ASSETS)} assets, "
          f"{len(stale)} references updated")


if __name__ == "__main__":
    main()
