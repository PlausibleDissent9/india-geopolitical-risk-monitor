"""
E4: per-sector feeds. One machine-consumable JSON per registered
sector, assembled nightly from already-published payloads -- the
single-sector cut of exactly what the exposure page computes, so a
consumer can poll docs/data/sector_textiles_apparel.json instead of
joining four payloads themselves.

Nothing new is computed here: scores from latest.json, bands from
uncertainty.json, weights under the registered rule (the sector as a
whole profile), measured sensitivity cells where a signed NSE mapping
exists. Salience-not-risk travels in every file's _meta.

  python -m src.sector_feeds     writes docs/data/sector_<key>.json x N
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.exposure import load_sectors, profile_weights

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"

DISCLAIMER = (
    "IGRM measures press salience -- the share of global news coverage "
    "matching registered channel dictionaries, ranked against each "
    "channel's own trailing two years. It is not a measure of risk and "
    "makes no forecasts. This feed re-cuts published numbers by one "
    "registered sector's frame and adds no new claim."
)


def _load(name: str) -> dict[str, Any] | None:
    path = SITE_DATA / name
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_feed(key: str, spec: dict[str, Any], sectors: dict[str, Any],
               latest: dict[str, Any], unc: dict[str, Any] | None,
               sens: dict[str, Any] | None) -> dict[str, Any]:
    weights = profile_weights({key: 1.0}, sectors)
    day = latest.get("date")
    bands = (unc or {}).get("days", {}).get(day, {}) if unc else {}
    channels: dict[str, Any] = {}
    for ch, w in weights.items():
        lch = (latest.get("channels") or {}).get(ch) or {}
        channels[ch] = {
            "label": lch.get("label"),
            "score": lch.get("score"),
            "band95": bands.get(ch),
            "weight": w,
            "receipts": f"https://igrm.in/receipts.html#{ch}",
        }
    feed: dict[str, Any] = {
        "_meta": {
            "what": (f"Per-sector feed for {spec['label']}: the sector's "
                     "registered channels with today's published scores, "
                     "95% sampling bands, and weights under the "
                     "registered exposure rule. " + DISCLAIMER),
            "sector_registration": "sectors.json",
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "sector": key,
        "label": spec["label"],
        "rationale": spec.get("rationale"),
        "date": day,
        "channels": channels,
    }
    s = (sens or {}).get("sectors", {}).get(key)
    if s:
        feed["measured_sensitivity"] = {
            "nse_index": s["nse_index"],
            "channels": s["channels"],
            "note": ("Historical association only, Benjamini-Hochberg "
                     "corrected across the full grid; see "
                     "sector_sensitivity.json _meta for the discipline "
                     "and the current negative result."),
        }
    return feed


def main() -> None:
    sectors = load_sectors()
    latest = _load("latest.json")
    if latest is None:
        raise SystemExit("[sector-feeds] no latest.json")
    unc = _load("uncertainty.json")
    sens = _load("sector_sensitivity.json")
    n = 0
    for key, spec in sorted(sectors["sectors"].items()):
        feed = build_feed(key, spec, sectors, latest, unc, sens)
        (SITE_DATA / f"sector_{key}.json").write_text(
            json.dumps(feed), encoding="utf-8")
        n += 1
    print(f"[sector-feeds] wrote {n} sector feeds for {latest.get('date')}")


if __name__ == "__main__":
    main()
