"""Regenerate data/geo/india_admin1.geojson from the full Natural Earth
admin-1 file (gitignored, 41 MB). Keeps India's 36 features and only the
three properties src/geo_split reads -- 0.8 MB, small enough to commit so
every lane can place events by coordinate rather than falling back to
FIPS codes that predate Telangana and Ladakh.

  python scripts/slim_geo.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "data" / "raw" / "naturalearth"
       / "ne_10m_admin_1_states_provinces.geojson")
OUT = ROOT / "data" / "geo" / "india_admin1.geojson"


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"[slim-geo] source absent: {SRC}")
    d = json.loads(SRC.read_text(encoding="utf-8"))
    feats = [f for f in d["features"]
             if (f["properties"].get("iso_a2") == "IN"
                 or f["properties"].get("adm0_a3") == "IND")]
    slim = {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "properties": {"name": f["properties"].get("name"),
                        "iso_3166_2": f["properties"].get("iso_3166_2"),
                        "iso_a2": "IN"},
         "geometry": f["geometry"]}
        for f in feats]}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(slim), encoding="utf-8")
    print(f"[slim-geo] {len(feats)} features -> {OUT.name} "
          f"({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
