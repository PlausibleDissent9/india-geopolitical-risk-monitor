"""
Exposure engine core (E1, founder-approved 2026-08-05 "execute all").

Maps a reader's sector profile to the registered channels that touch
it, deterministically, from the REGISTERED sectors.json (v1.0.0) --
the same file the founder may amend only with a dated changelog entry.

THE HARD LINE (NOTES 0.13, non-negotiable): this is retrieval,
description, and disclosed historical association only. The engine
computes which published numbers concern a profile and how much weight
each carries under a stated rule; it never predicts, advises, or
scores risk. Every derived surface must carry the salience-not-risk
statement and show its own computation.

The weighting rule, registered here and printed in the payload:
  * a profile is a set of sectors with non-negative shares
    (unspecified shares mean equal split);
  * shares are normalized to sum to 1;
  * each sector's share divides EQUALLY across its registered
    channels (sectors.json names the channels; it records no
    intra-sector ordering, so none is invented);
  * a channel's weight is the sum of what it receives from every
    sector in the profile.

  python -m src.exposure     writes docs/data/exposure_sectors.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"

WEIGHT_RULE = (
    "Shares normalize to 1; each sector's share divides equally across "
    "its registered channels; channel weight is the sum across sectors. "
    "No intra-sector channel ordering exists in the registration, so "
    "none is invented."
)


def load_sectors() -> dict[str, Any]:
    return json.loads((ROOT / "sectors.json").read_text(encoding="utf-8"))


def profile_weights(
    profile: dict[str, float], sectors: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Channel weights for a {sector_key: share} profile under the
    registered rule. Raises on unknown sectors and non-positive
    profiles -- a silent guess would be a fabricated exposure."""
    spec = (sectors or load_sectors())["sectors"]
    unknown = sorted(set(profile) - set(spec))
    if unknown:
        raise ValueError(f"unknown sectors: {unknown}")
    if not profile or any(v < 0 for v in profile.values()):
        raise ValueError("profile needs non-negative shares")
    total = sum(profile.values())
    if total <= 0:
        raise ValueError("profile shares sum to zero")
    weights: dict[str, float] = {}
    for key, share in profile.items():
        channels = spec[key]["channels"]
        for ch in channels:
            weights[ch] = weights.get(ch, 0.0) + (share / total) / len(channels)
    return {ch: round(w, 6) for ch, w in sorted(weights.items())}


def main() -> None:
    sectors = load_sectors()
    payload = {
        "_meta": {
            "what": ("The registered sector-to-channel exposure map "
                     "(sectors.json v" + str(sectors["_meta"].get("version"))
                     + ") with the deterministic weighting rule the "
                     "exposure page computes with. Retrieval and "
                     "description only: the instrument measures press "
                     "salience, not risk, and makes no forecasts; an "
                     "exposure profile re-cuts published numbers by the "
                     "reader's own frame and adds no new claim."),
            "weight_rule": WEIGHT_RULE,
            "registration": sectors["_meta"].get("status"),
            "version": sectors["_meta"].get("version"),
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "sectors": sectors["sectors"],
    }
    (SITE_DATA / "exposure_sectors.json").write_text(
        json.dumps(payload), encoding="utf-8")
    print(f"[exposure] wrote exposure_sectors.json: "
          f"{len(sectors['sectors'])} sectors")


if __name__ == "__main__":
    main()
