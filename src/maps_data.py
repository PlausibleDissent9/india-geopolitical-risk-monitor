"""
Map aggregates for the two V2 maps, from the three-layer events stores.

Refuses to publish while the 2017 events backfill is incomplete: a
country aggregate computed over a fraction of the range would read as
history and mislead. CI runs this daily with continue-on-error; the
first run after the chain finishes publishes the payloads.

  docs/data/map_relations.json   per-partner event counts, cooperation
                                 vs conflict split, Goldstein mean;
                                 full range and trailing 365 days
  docs/data/map_states.json      per-state counts, conflict and protest
                                 shares; full range and trailing 365 days

  python -m src.maps_data              publish (gated on completeness)
  python -m src.maps_data --force-partial   local verification ONLY;
                                 marks the payload partial=true and must
                                 never be committed

Old-vintage FIPS codes GDELT still emits are folded into today's
geometry (documented FIPS 10-4 renumberings); the pre-2000 parents
include their split-off children, disclosed in the codebook. CAMEO
regional actor codes (SAS, EUR, ...) are not countries and are listed
in the payload's excluded block with their row counts.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from .fetch_events import STORE_DYADS, STORE_STATES, _missing_days

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"
GEO = ROOT / "docs" / "geo"

# Pre-2000 FIPS 10-4 codes folded into their present-day successor
# geometry (the old parent includes the split-off child state).
FIPS_PATCH = {"IN09": "IN35", "IN33": "IN36", "IN25": "IN22", "IN06": "IN52"}
EXCLUDED_ADM1 = {"IN00"}  # country-level geocode, no state

RECENT_DAYS = 365


def _f(x: str) -> float:
    try:
        return float(x)
    except ValueError:
        return 0.0


def build_relations(world: dict) -> dict:
    cutoff = (date.today() - timedelta(days=RECENT_DAYS)).isoformat()
    agg: dict[str, dict] = defaultdict(lambda: {
        "n": 0, "n_coop": 0, "n_conflict": 0, "gold_sum": 0.0, "gold_n": 0,
        "r_n": 0, "r_coop": 0, "r_conflict": 0})
    excluded: dict[str, int] = defaultdict(int)
    with STORE_DYADS.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            p = row["partner"]
            if not p:
                continue
            if p not in world:
                excluded[p] += int(row["n"] or 0)
                continue
            a = agg[p]
            n, coop, conf = int(row["n"]), int(row["n_coop"]), int(row["n_conflict"])
            a["n"] += n
            a["n_coop"] += coop
            a["n_conflict"] += conf
            if row["goldstein_mean"]:
                a["gold_sum"] += _f(row["goldstein_mean"]) * n
                a["gold_n"] += n
            if row["date"] >= cutoff:
                a["r_n"] += n
                a["r_coop"] += coop
                a["r_conflict"] += conf
    partners = {}
    for p, a in agg.items():
        classified = a["n_coop"] + a["n_conflict"]
        r_classified = a["r_coop"] + a["r_conflict"]
        partners[p] = {
            "name": world[p]["name"],
            "n": a["n"],
            "conflict_share": (round(a["n_conflict"] / classified, 3)
                               if classified else None),
            "goldstein_mean": (round(a["gold_sum"] / a["gold_n"], 2)
                               if a["gold_n"] else None),
            "recent_n": a["r_n"],
            "recent_conflict_share": (round(a["r_conflict"] / r_classified, 3)
                                      if r_classified else None),
        }
    return {"partners": partners,
            "excluded_actor_codes": dict(sorted(excluded.items(),
                                                key=lambda kv: -kv[1]))}


def build_states(india: dict) -> dict:
    cutoff = (date.today() - timedelta(days=RECENT_DAYS)).isoformat()
    agg: dict[str, dict] = defaultdict(lambda: {
        "n": 0, "conf": 0, "prot": 0, "r_n": 0, "r_conf": 0, "r_prot": 0})
    excluded: dict[str, int] = defaultdict(int)
    with STORE_STATES.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            code = row["adm1"]
            if not code:
                continue
            key = FIPS_PATCH.get(code, code)
            if code in EXCLUDED_ADM1 or key not in india:
                excluded[code] += int(row["n"] or 0)
                continue
            a = agg[key]
            n, conf, prot = int(row["n"]), int(row["n_conflict"]), int(row["n_protest"])
            a["n"] += n
            a["conf"] += conf
            a["prot"] += prot
            if row["date"] >= cutoff:
                a["r_n"] += n
                a["r_conf"] += conf
                a["r_prot"] += prot
    states = {}
    for k, a in agg.items():
        states[k] = {
            "name": india[k]["name"],
            "n": a["n"],
            "conflict_share": round(a["conf"] / a["n"], 3) if a["n"] else None,
            "protest_share": round(a["prot"] / a["n"], 3) if a["n"] else None,
            "recent_n": a["r_n"],
            "recent_conflict_share": (round(a["r_conf"] / a["r_n"], 3)
                                      if a["r_n"] else None),
        }
    return {"states": states,
            "excluded_adm1": dict(sorted(excluded.items(), key=lambda kv: -kv[1]))}


def main() -> None:
    force = "--force-partial" in sys.argv
    missing = len(_missing_days())
    if missing and not force:
        raise SystemExit(
            f"[maps] {missing} days of the events history still missing; "
            "refusing to publish aggregates over partial history")
    world = json.loads((GEO / "world.json").read_text(encoding="utf-8"))["countries"]
    india = json.loads((GEO / "india.json").read_text(encoding="utf-8"))["states"]
    meta = {
        "what": ("Event counts by partner country and by Indian state from "
                 "the GDELT Events v1 stream, 2017-present. Counts of press-"
                 "recorded events; association, not causation."),
        "generated": date.today().isoformat(),
        "days_missing": missing,
        "partial": bool(missing),
        "recent_window_days": RECENT_DAYS,
    }
    rel = {"_meta": meta, **build_relations(world)}
    st = {"_meta": meta, **build_states(india)}
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / "map_relations.json").write_text(json.dumps(rel), encoding="utf-8")
    (SITE_DATA / "map_states.json").write_text(json.dumps(st), encoding="utf-8")
    print(f"[maps] wrote map_relations.json ({len(rel['partners'])} partners) "
          f"and map_states.json ({len(st['states'])} states)"
          + (" [PARTIAL, verification only]" if missing else ""))


if __name__ == "__main__":
    main()
