"""
Assemble a versioned, self-contained release bundle for Zenodo.

Files only: the author uploads the bundle and mints the DOI from his
account. The bundle carries everything needed to understand and reuse
the data without the repository: site payloads, raw stores, the frozen
dictionaries and registrations, methodology, and codebook.

  python scripts/make_release.py 1.2.0
  -> releases/igrm-v1.2.0.zip + manifest with sha256 per file
"""
from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "releases"

INCLUDE = [
    "docs/data",
    "data/raw/gdelt_volume.csv",
    "data/raw/events_daily.csv",
    "data/raw/events_dyads.csv",
    "data/raw/events_states.csv",
    "data/raw/events_unavailable_days.json",
    "data/raw/portwatch_chokepoints.csv",
    "data/raw/chokepoint_salience.csv",
    "data/raw/comparator_salience.csv",
    "data/raw/wiki_volume.csv",
    "data/raw/ngram_calibration.json",
    "dictionaries.json",
    "dictionaries_alt.json",
    "dictionaries_placebo.json",
    "comparators.json",
    "validation",
    "methodology.md",
    "docs/codebook.md",
    "CITATION.cff",
    "README.md",
]


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: make_release.py <version>")
    version = sys.argv[1]
    OUT_DIR.mkdir(exist_ok=True)
    zip_path = OUT_DIR / f"igrm-v{version}.zip"
    manifest: dict[str, str] = {}
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for entry in INCLUDE:
            p = ROOT / entry
            files = sorted(p.rglob("*")) if p.is_dir() else [p]
            for f in files:
                if not f.is_file():
                    continue
                rel = f.relative_to(ROOT).as_posix()
                z.write(f, rel)
                manifest[rel] = hashlib.sha256(f.read_bytes()).hexdigest()
        meta = {"version": version, "date": date.today().isoformat(),
                "files": manifest}
        z.writestr("MANIFEST.json", json.dumps(meta, indent=1))
    print(f"[release] {zip_path.name}: {len(manifest)} files, "
          f"{zip_path.stat().st_size // (1024 * 1024)} MB")


if __name__ == "__main__":
    main()
