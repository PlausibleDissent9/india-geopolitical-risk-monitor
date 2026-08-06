"""
V20 groundwork: the grey-states fix.

Telangana, Ladakh and Goa render grey on the maps because GDELT's
FIPS admin-1 geocoding predates their creation (Telangana 2014,
Ladakh 2019) or codes them under a parent; their events land under
IN02/IN12/IN36 and similar. The honest fix is not a lookup table of
guesses -- it is to place each event by its own coordinates.

This module does the placing: ray-cast point-in-polygon against a
committed India-only extract of the Natural Earth admin-1 polygons
(data/geo/india_admin1.geojson, 0.8 MB), no new dependencies,
deterministic. Events carry ActionGeo_Lat/Long in the
GDELT export (columns 53/54 of the v1 schema, beside the ADM1 code
the fetcher already reads), so the re-split needs no new source --
only the coordinates the fetcher will now keep.

Boundary depiction follows the site's existing decision (NOTES 0.2):
the states layer draws India's administered states.

  python -m src.geo_split --selftest    place known cities, no network
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
# India-only extract, COMMITTED (0.8 MB) so every lane can place
# points -- the full 41 MB Natural Earth world file is gitignored, so
# depending on it meant V20 worked on one laptop and silently fell back
# to FIPS codes everywhere else. Regenerate with scripts/slim_geo.py.
GEOJSON = ROOT / "data" / "geo" / "india_admin1.geojson"

# Cities whose state is unambiguous, used as the module's self-test.
# Three of them are exactly the states that render grey today.
SELFTEST = [
    ("Hyderabad", 17.3850, 78.4867, "Telangana"),
    ("Leh", 34.1526, 77.5771, "Ladakh"),
    ("Panaji", 15.4909, 73.8278, "Goa"),
    ("Mumbai", 19.0760, 72.8777, "Maharashtra"),
    ("Kolkata", 22.5726, 88.3639, "West Bengal"),
    ("Jaipur", 26.9124, 75.7873, "Rajasthan"),
    ("Srinagar", 34.0837, 74.7973, "Jammu and Kashmir"),
    ("Chennai", 13.0827, 80.2707, "Tamil Nadu"),
]


def _rings(geom: dict[str, Any]) -> list[list[list[float]]]:
    """Outer rings only: India's admin-1 polygons carry no holes that
    change a state assignment, and ignoring them keeps the test
    total (a point in a hole would otherwise be placed nowhere)."""
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]]
    if geom["type"] == "MultiPolygon":
        return [poly[0] for poly in geom["coordinates"]]
    return []


def load_states() -> list[dict[str, Any]]:
    """India's admin-1 features with their rings and bounding boxes
    precomputed -- the bbox test rejects almost every candidate in
    constant time, which is what makes a pure-Python re-split of
    millions of events tractable."""
    data = json.loads(GEOJSON.read_text(encoding="utf-8"))
    out = []
    for f in data["features"]:
        p = f["properties"]
        if (p.get("iso_a2") or "") != "IN" and (p.get("adm0_a3") or "") != "IND":
            continue
        rings = _rings(f["geometry"])
        if not rings:
            continue
        xs = [pt[0] for r in rings for pt in r]
        ys = [pt[1] for r in rings for pt in r]
        out.append({
            "name": p.get("name") or "",
            "iso_3166_2": p.get("iso_3166_2") or "",
            "rings": rings,
            "bbox": (min(xs), min(ys), max(xs), max(ys)),
        })
    return out


def point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    """Standard ray casting: count crossings of a rightward ray."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_cross:
                inside = not inside
        j = i
    return inside


def place(lat: float, lon: float,
          states: list[dict[str, Any]] | None = None) -> str | None:
    """The state containing this point, or None when no polygon does
    (offshore, a border sliver, or a bad geocode). None is published
    as unplaced -- never snapped to the nearest state, because a
    guessed placement is indistinguishable from a measured one once
    it is on a map."""
    for s in (states if states is not None else load_states()):
        x0, y0, x1, y1 = s["bbox"]
        if not (x0 <= lon <= x1 and y0 <= lat <= y1):
            continue
        if any(point_in_ring(lon, lat, r) for r in s["rings"]):
            return s["name"]
    return None


def selftest() -> int:
    states = load_states()
    print(f"[geo] loaded {len(states)} India admin-1 polygons")
    failures = 0
    for city, lat, lon, expected in SELFTEST:
        got = place(lat, lon, states)
        ok = got == expected
        failures += 0 if ok else 1
        print(f"[geo] {city:10s} -> {str(got):22s} "
              f"{'OK' if ok else 'MISMATCH, expected ' + expected}")
    print(f"[geo] selftest: {len(SELFTEST) - failures}/{len(SELFTEST)} placed "
          "correctly")
    return failures


def main() -> None:
    if "--selftest" in sys.argv:
        sys.exit(1 if selftest() else 0)
    print(__doc__)


if __name__ == "__main__":
    main()
