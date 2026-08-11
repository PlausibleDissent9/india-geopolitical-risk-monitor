"""
Make the codebook's self-description promise true (2026-08-07).

The codebook has said this since it was written:

    "Every dict-shaped JSON published by the pipeline embeds a _meta
    object (what the file is, units, license, citation, codebook link,
    generation date) so a downloaded file explains itself without this
    website."

It was not true. Measured across 64 dict payloads: `what` in 59,
`generated` in 62, and `license`, `citation` and `codebook` in **three**.
Someone downloading syndication.json or monthly.csv's JSON sidecar had
no way to know the licence terms or how to cite it, which is precisely
the situation the sentence promised would not arise -- and for a project
whose whole pitch is citability, a false claim about citability is the
worst one to leave standing.

Two ways to fix a documented promise the code does not keep: weaken the
document, or make the code keep it. Weakening was available and cheap
and would have been the wrong call, because the promise is the right
promise -- a downloaded file SHOULD explain itself.

So this stamps the four universal fields onto every published payload
after the lanes have run. It never overwrites a field a module set: a
lane that writes a precise `units` string knows more about its own
payload than this does. It only fills what is absent.

  python -m src.stamp_meta            stamp every payload
  python -m src.stamp_meta --check    report gaps, write nothing
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"

LICENSE = "CC BY 4.0"
CITATION = ("Krishna, Ishan (2026). India Geopolitical Risk Monitor. "
            "https://igrm.in/")
CODEBOOK = "https://igrm.in/codebook.html"
BASE_URL = "https://igrm.in/data/"

# The contract file is a hand-frozen promise about field stability, not
# a data payload; rewriting it here would let the "frozen" list drift by
# a side effect, which is exactly what it exists to prevent.
SKIP = {
    "api_contract.json",
    # Deterministic candidate-byte inventory. Any post-generation metadata
    # mutation would make its published bytes differ from the exact candidate
    # object validated by the publication barrier.
    "public_api_byte_manifest.json",
    # Registration commit 58ca6c0 promises the generated benchmark output
    # verbatim. Its own _meta carries the source, hashes, registration,
    # provider citation and redistribution limit; a generic post-run stamp
    # would break the published output hash.
    "ai_gpr_benchmark.json",
}


def universal_fields(name: str) -> dict[str, str]:
    return {
        "license": LICENSE,
        "citation": CITATION,
        "codebook": CODEBOOK,
        "source": BASE_URL + name,
    }


def stamp_file(path: Path, write: bool = True) -> list[str]:
    """Fill absent universal fields. Returns the field names added."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    # Arrays and scalars have nowhere to carry _meta. episodes.json is
    # the live example; it travels in the same commit as history.json,
    # which is stamped.
    if not isinstance(data, dict):
        return []

    meta = data.get("_meta")
    if not isinstance(meta, dict):
        meta = {}
    added = []
    for key, value in universal_fields(path.name).items():
        # Never overwrite. A lane that set its own citation or a more
        # precise licence knows more about its payload than this does.
        if not meta.get(key):
            meta[key] = value
            added.append(key)
    if not added:
        return []
    if write:
        data["_meta"] = meta
        path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return added


def main() -> None:
    check_only = "--check" in sys.argv
    stamped: dict[str, list[str]] = {}
    skipped_non_dict = []
    for path in sorted(SITE_DATA.glob("*.json")):
        if path.name in SKIP:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            skipped_non_dict.append(path.name)
            continue
        added = stamp_file(path, write=not check_only)
        if added:
            stamped[path.name] = added

    verb = "would stamp" if check_only else "stamped"
    print(f"[stamp-meta] {verb} {len(stamped)} payload(s)")
    for name, fields in sorted(stamped.items())[:10]:
        print(f"[stamp-meta]   {name}: {', '.join(fields)}")
    if len(stamped) > 10:
        print(f"[stamp-meta]   ... and {len(stamped) - 10} more")
    if skipped_non_dict:
        print(f"[stamp-meta] {len(skipped_non_dict)} non-dict payload(s) "
              f"cannot carry _meta: {', '.join(skipped_non_dict)}")

    if check_only and stamped:
        raise SystemExit(
            f"[stamp-meta] {len(stamped)} payload(s) are missing universal "
            "_meta fields the codebook promises every download carries")


def audit() -> dict[str, Any]:
    """Which payloads still lack which universal fields (read-only)."""
    gaps: dict[str, list[str]] = {}
    for path in sorted(SITE_DATA.glob("*.json")):
        if path.name in SKIP:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        meta = data.get("_meta") if isinstance(data.get("_meta"), dict) else {}
        missing = [k for k in universal_fields(path.name)
                   if not (meta or {}).get(k)]
        if missing:
            gaps[path.name] = missing
    return gaps


if __name__ == "__main__":
    main()
