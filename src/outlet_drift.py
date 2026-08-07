"""
F15: outlet-set drift -- whether the index's outlet base is turning over.

Referee finding F15: the index cannot detect composition change. If
half the outlet population were quietly swapped for a different half,
the volume series would keep its level and say nothing. The referee
asked for outlet-set Jaccard BY YEAR. The committed archive cannot
support a year grain: the only committed store that carries outlet
identity is data/raw/receipt_days (the receipts day-caches, article
URLs included), and its depth is disclosed in this payload's _meta
rather than asserted here. What the archive supports honestly is the
same statistic at the DAY grain: pairwise Jaccard between every
archived day's outlet set, per channel and overall. The matrices widen
mechanically as new day-caches are committed -- the same way the
vintages panel widens -- so the coarser grains assemble themselves
from this code as the archive accumulates, instead of being faked now.

A stranger reads docs/data/outlet_drift.json to answer: between any
two archived days, how much of the outlet population is shared?
jaccard[i][j] near 1.0 means the same outlets carry the coverage;
near 0.0 means the population turned over. n_outlets sizes each day's
set; n_samples states the sampling depth each set was drawn at.

Construction. Outlet sets use the identical matched-article arithmetic
the receipts assembly applies (channel_doc_keys: sub-query union,
India anchor), mapped to domains from the cached article URLs, www
stripped. Only standard-depth day-caches enter: the -extended censuses
sample more corpus files, a deeper census mechanically enlarges the
set, and Jaccard between unequal depths manufactures drift that is
sampling, not composition. A day with no matched articles has no set,
so its cells are null, never zero -- absence of coverage is not
evidence of turnover.

Fails loudly (SystemExit / KeyError) rather than publishing a partial
matrix.

  python -m src.outlet_drift          write docs/data/outlet_drift.json
  python -m src.outlet_drift --check  compute and report, write nothing
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DAYS_DIR = ROOT / "data" / "raw" / "receipt_days"
SITE_DATA = ROOT / "docs" / "data"

OVERALL = "overall"


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def day_outlet_sets(cache: dict[str, Any]) -> dict[str, set[str]]:
    """Per channel plus OVERALL: the day's outlet (domain) sets, built
    with the same matched-article arithmetic the receipts assembly and
    spike_breadth apply -- the registered dictionaries chose every
    article whose domain is counted here."""
    from src import receipts_ngrams

    specs = receipts_ngrams.group_specs()
    corpus = {
        "matched": {g: set(keys) for g, keys in
                    (cache.get("matched") or {}).items()},
        "india": set(cache.get("india") or []),
    }
    meta = cache.get("meta") or {}
    out: dict[str, set[str]] = {}
    union: set[str] = set()
    for ch in receipts_ngrams.CHANNELS:
        keys = receipts_ngrams.channel_doc_keys(ch, specs, corpus)
        domains = {_domain(meta[k]["url"]) for k in keys
                   if k in meta and meta[k].get("url")}
        domains.discard("")
        out[ch] = domains
        union |= domains
    out[OVERALL] = union
    return out


def jaccard(a: set[str], b: set[str]) -> float | None:
    """|a n b| / |a u b|; null when either day has no set to compare."""
    if not a or not b:
        return None
    return round(len(a & b) / len(a | b), 4)


def _adjacent_summary(days: list[str],
                      matrix: list[list[float | None]]) -> dict[str, Any]:
    """Consecutive-day Jaccard, summarised. The mean answers the
    referee's question at the archive's native grain."""
    pairs = [matrix[i][i + 1] for i in range(len(days) - 1)]
    vals = [v for v in pairs if v is not None]
    if not vals:
        return {"n_pairs": 0, "mean": None, "min": None, "max": None}
    return {
        "n_pairs": len(vals),
        "mean": round(sum(vals) / len(vals), 4),
        "min": min(vals),
        "max": max(vals),
    }


def compute(only_days: list[str] | None = None) -> dict[str, Any]:
    """The full payload minus the generation timestamp, so the test can
    assert payload == compute() byte-for-value.

    `only_days` restricts the matrix to the named day-caches. The
    equality test passes the payload's own day list: the staging
    boundary (scripts/stage_daily_outputs.sh) legitimately banks a new
    raw cache while refusing the regenerated payload on a failed run,
    so disk can hold one more day than the payload without anything
    being wrong -- that gap is freshness.py's business. An unrestricted
    recompute here would have turned every such evidence commit into a
    red CI and failed the morning gate (caught by cross-review
    2026-08-08, proven with one extra cache day)."""
    from src import receipts_ngrams, stamp_meta

    standard = sorted(p for p in DAYS_DIR.glob("*.json")
                      if "-extended" not in p.stem)
    if only_days is not None:
        wanted = set(only_days)
        standard = [p for p in standard if p.stem in wanted]
        missing = wanted - {p.stem for p in standard}
        if missing:
            raise SystemExit(
                f"[outlet_drift] requested day-caches are absent: "
                f"{sorted(missing)}; the payload names days the archive "
                "no longer holds, which is a rewrite, not a lag")
    extended = sorted(p for p in DAYS_DIR.glob("*-extended.json"))
    if len(standard) < 2:
        raise SystemExit(
            "[outlet_drift] fewer than two standard-depth day-caches in "
            f"{DAYS_DIR}; a drift matrix needs at least two days")

    days: list[str] = []
    n_samples: dict[str, int] = {}
    sets_by_day: list[dict[str, set[str]]] = []
    for path in standard:
        cache = json.loads(path.read_text(encoding="utf-8"))
        days.append(path.stem)
        n_samples[path.stem] = int(cache["n_samples"])
        sets_by_day.append(day_outlet_sets(cache))

    channels: dict[str, Any] = {}
    adjacent: dict[str, Any] = {}
    for name in [*receipts_ngrams.CHANNELS, OVERALL]:
        sets = [s[name] for s in sets_by_day]
        matrix = [[jaccard(sets[i], sets[j]) for j in range(len(days))]
                  for i in range(len(days))]
        channels[name] = {
            "n_outlets": {d: len(s) for d, s in zip(days, sets)},
            "jaccard": matrix,
        }
        adjacent[name] = _adjacent_summary(days, matrix)

    return {
        "_meta": {
            **stamp_meta.universal_fields("outlet_drift.json"),
            "what": (
                "Outlet-set drift (referee finding F15): pairwise Jaccard "
                "similarity between the outlet (domain) sets of every "
                "archived day, per channel and overall. jaccard[i][j] "
                "compares days[i] with days[j]; near 1.0 the same outlets "
                "carry the coverage, near 0.0 the population turned over. "
                "Cells are null where a day has no matched articles for "
                "the channel: an absent set is not evidence of turnover."),
            "why": (
                "The referee asked for outlet-set Jaccard by year; the "
                "only committed store carrying outlet identity is the "
                "receipts day-cache archive, whose coverage window is the "
                "one disclosed below. The honest grain is therefore the "
                "day. The matrices extend mechanically as day-caches are "
                "committed, so coarser grains become computable from this "
                "same code as the archive accumulates."),
            "units": (
                "Jaccard similarity in [0, 1] between per-day sets of "
                "registrable article domains (www stripped)"),
            "construction": (
                "Outlet sets use the receipts assembly's own "
                "matched-article arithmetic (sub-query union, India "
                "anchor) over the standard-depth day-caches only; the "
                "-extended censuses sample more corpus files and a deeper "
                "census mechanically enlarges a set, so mixing depths "
                "would manufacture drift. Sets are drawn from sampled "
                "corpora: Jaccard between sampled sets understates the "
                "full-population overlap, comparably across equally "
                "sampled days -- n_samples states each day's depth."),
            "coverage": {
                "unit": "utc_day",
                "first_day": days[0],
                "last_day": days[-1],
                "n_units": len(days),
                "requested_grain": "year",
                "supported_grain": "day",
                "n_extended_caches_excluded": len(extended),
            },
        },
        "days": days,
        "n_samples": n_samples,
        "channels": channels,
        "adjacent_day": adjacent,
    }


def main() -> None:
    check = "--check" in sys.argv
    payload = compute()
    payload["_meta"]["generated"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    if not check:
        (SITE_DATA / "outlet_drift.json").write_text(
            json.dumps(payload), encoding="utf-8")
    cov = payload["_meta"]["coverage"]
    print(f"[drift] {cov['first_day']}..{cov['last_day']} "
          f"n_units={cov['n_units']}"
          + (" (check only)" if check else ""))
    for name, s in payload["adjacent_day"].items():
        print(f"[drift] {name}: adjacent-day J mean={s['mean']} "
              f"min={s['min']} max={s['max']} n_pairs={s['n_pairs']}")


if __name__ == "__main__":
    main()
