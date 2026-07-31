"""
Bake compact self-hosted SVG path assets for the two maps from Natural
Earth public-domain data (naturalearthdata.com, via the project's
GitHub mirror). Run rarely, by hand; the outputs are committed and the
site never fetches geometry from anywhere.

  docs/geo/world.json   110m admin-0, equirectangular, lat clipped to
                        [-60, 85] (Antarctica dropped), keyed ADM0_A3
                        (matches the CAMEO-style dyad partner codes).
  docs/geo/india.json   10m admin-1 filtered to India, keyed by the
                        FIPS code GDELT uses in events_states.csv.

Boundary depiction note: admin-0 uses Natural Earth's standard
(de facto) worldview; the admin-1 file carries Indian states as
administered, including Jammu and Kashmir and Ladakh. The depiction
choice is flagged for the author in NOTES_FOR_ISHAN.md.

  python scripts/prepare_map_geometry.py
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEO = ROOT / "docs" / "geo"
CACHE = ROOT / "data" / "raw" / "naturalearth"

BASE = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
        "master/geojson/")
WORLD_FILE = "ne_110m_admin_0_countries.geojson"
ADM1_FILE = "ne_10m_admin_1_states_provinces.geojson"

WORLD_W, WORLD_H = 1000.0, 520.0
WORLD_LAT_MAX, WORLD_LAT_MIN = 85.0, -60.0
INDIA_W, INDIA_H = 620.0, 700.0


def fetch(name: str) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    if not path.exists():
        print(f"[geo] downloading {name}")
        req = urllib.request.Request(BASE + name,
                                     headers={"User-Agent": "igrm-research"})
        with urllib.request.urlopen(req, timeout=600) as r:
            path.write_bytes(r.read())
    return json.loads(path.read_text(encoding="utf-8"))


def simplify(ring: list[list[float]], tol: float) -> list[list[float]]:
    """Iterative Douglas-Peucker on lon/lat rings."""
    if len(ring) < 4:
        return ring
    keep = [False] * len(ring)
    keep[0] = keep[-1] = True
    stack = [(0, len(ring) - 1)]
    # A closed ring starts and ends on the same point, which makes the
    # initial baseline degenerate and every distance zero (the whole
    # ring collapsed to two points). Anchor the farthest point from the
    # start before recursing.
    if ring[0] == ring[-1]:
        x0, y0 = ring[0]
        far = max(range(1, len(ring) - 1),
                  key=lambda i: (ring[i][0] - x0) ** 2 + (ring[i][1] - y0) ** 2)
        keep[far] = True
        stack = [(0, far), (far, len(ring) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = ring[a]
        bx, by = ring[b]
        dx, dy = bx - ax, by - ay
        norm = (dx * dx + dy * dy) ** 0.5 or 1e-12
        worst, wi = 0.0, -1
        for i in range(a + 1, b):
            px, py = ring[i]
            d = abs(dx * (ay - py) - dy * (ax - px)) / norm
            if d > worst:
                worst, wi = d, i
        if worst > tol:
            keep[wi] = True
            stack.extend([(a, wi), (wi, b)])
    return [p for p, k in zip(ring, keep) if k]


def rings(geom: dict) -> list[list[list[float]]]:
    if geom["type"] == "Polygon":
        return list(geom["coordinates"])
    if geom["type"] == "MultiPolygon":
        return [r for poly in geom["coordinates"] for r in poly]
    return []


def path_d(geom: dict, project, tol: float) -> str:
    parts = []
    for ring in rings(geom):
        s = simplify([list(p) for p in ring], tol)
        if len(s) < 3:
            continue
        pts = [project(x, y) for x, y in s]
        parts.append("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + "Z")
    return "".join(parts)


def build_world() -> None:
    data = fetch(WORLD_FILE)
    span = WORLD_LAT_MAX - WORLD_LAT_MIN

    def project(lon: float, lat: float) -> tuple[float, float]:
        lat = max(min(lat, WORLD_LAT_MAX), WORLD_LAT_MIN)
        return ((lon + 180.0) / 360.0 * WORLD_W,
                (WORLD_LAT_MAX - lat) / span * WORLD_H)

    countries = {}
    for f in data["features"]:
        code = f["properties"].get("ADM0_A3")
        name = f["properties"].get("NAME_LONG") or f["properties"].get("NAME")
        if not code or f["properties"].get("NAME") == "Antarctica":
            continue
        d = path_d(f["geometry"], project, tol=0.15)
        if d:
            countries[code] = {"name": name, "d": d}
    # States too small for 110m polygons but present in the dyad stream
    # render as point markers (lon, lat -> same projection).
    small = {
        "SGP": ("Singapore", 103.82, 1.35),
        "MDV": ("Maldives", 73.51, 4.19),
        "MUS": ("Mauritius", 57.55, -20.30),
        "BHR": ("Bahrain", 50.55, 26.05),
        "MLT": ("Malta", 14.40, 35.90),
        "MCO": ("Monaco", 7.42, 43.73),
        "SYC": ("Seychelles", 55.45, -4.62),
        "COM": ("Comoros", 43.87, -11.65),
    }
    for code, (name, lon, lat) in small.items():
        if code not in countries:
            x, y = project(lon, lat)
            countries[code] = {"name": name, "pt": [round(x, 1), round(y, 1)]}
    out = {"viewBox": f"0 0 {WORLD_W:.0f} {WORLD_H:.0f}", "countries": countries}
    GEO.mkdir(parents=True, exist_ok=True)
    p = GEO / "world.json"
    p.write_text(json.dumps(out), encoding="utf-8")
    print(f"[geo] world.json: {len(countries)} countries, "
          f"{p.stat().st_size // 1024} KB")


def build_india() -> None:
    data = fetch(ADM1_FILE)
    feats = [f for f in data["features"]
             if f["properties"].get("adm0_a3") == "IND"]
    lons, lats = [], []
    for f in feats:
        for ring in rings(f["geometry"]):
            for lon, lat in ring:
                lons.append(lon)
                lats.append(lat)
    lo_x, hi_x = min(lons), max(lons)
    lo_y, hi_y = min(lats), max(lats)
    pad = 0.5
    lo_x, hi_x, lo_y, hi_y = lo_x - pad, hi_x + pad, lo_y - pad, hi_y + pad
    sx = INDIA_W / (hi_x - lo_x)
    sy = INDIA_H / (hi_y - lo_y)
    s = min(sx, sy)

    def project(lon: float, lat: float) -> tuple[float, float]:
        return ((lon - lo_x) * s, (hi_y - lat) * s)

    states = {}
    for f in feats:
        props = f["properties"]
        fips = props.get("fips")
        name = props.get("name")
        if not fips:
            print(f"[geo] admin-1 without fips skipped: {name}")
            continue
        d = path_d(f["geometry"], project, tol=0.01)
        if d:
            states[fips] = {"name": name, "d": d}
    out = {"viewBox": f"0 0 {INDIA_W:.0f} {INDIA_H:.0f}", "states": states}
    p = GEO / "india.json"
    p.write_text(json.dumps(out), encoding="utf-8")
    print(f"[geo] india.json: {len(states)} states, "
          f"{p.stat().st_size // 1024} KB")


if __name__ == "__main__":
    build_world()
    build_india()
