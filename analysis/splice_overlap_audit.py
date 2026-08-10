"""Independent audit of the July 2026 NGrams splice calibration.

The live store cannot be used as the denominator for this audit. After
the bridge ran, most recent store values were themselves computed as
NGrams share / production ratio. Regressing those values back onto the
same NGrams shares mechanically recovers the production ratio.

This audit instead pairs the retained NGrams day caches with the last
pre-bridge DOC-API store, preserved in git commit 091c25e and extracted
verbatim to analysis/splice_overlap_api_091c25e.csv. The snapshot has 18
independent overlap days for three channels and only one for US Trade and
Shipping. Those last two channels therefore remain untested out of sample.

Run from the repository root:

    python3 analysis/splice_overlap_audit.py
"""
from __future__ import annotations

import csv
import json
import math
from datetime import date
from pathlib import Path

from src import fetch_ngrams

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "analysis" / "splice_overlap_api_091c25e.csv"
CACHE = ROOT / "data" / "raw" / "ngram_days"
PRODUCTION = ROOT / "data" / "raw" / "ngram_calibration.json"
CHANNELS = (
    "pakistan_west",
    "china_east",
    "gulf_energy",
    "us_trade",
    "shipping",
)


def _ngram_channel_sums(day: str) -> dict[str, float]:
    parsed_day = date.fromisoformat(day)
    payload = json.loads(
        fetch_ngrams.read_retained_identity_cache(
            parsed_day,
            root=ROOT,
            cache_path=CACHE / f"{day}.json",
        )
    )
    shares = payload["shares"]
    return {
        channel: sum(
            float(value)
            for group, value in shares.items()
            if group.startswith(f"{channel}/")
        )
        for channel in CHANNELS
    }


def audit() -> dict[str, dict[str, float | int | None]]:
    production = json.loads(PRODUCTION.read_text(encoding="utf-8"))
    ratios: dict[str, list[float]] = {channel: [] for channel in CHANNELS}

    with SNAPSHOT.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            ngram = _ngram_channel_sums(row["date"])
            for channel in CHANNELS:
                if not row[channel]:
                    continue
                api_share = float(row[channel])
                if api_share > 0 and ngram[channel] > 0:
                    ratios[channel].append(ngram[channel] / api_share)

    result = {}
    for channel in CHANNELS:
        values = ratios[channel]
        logs = [math.log(value) for value in values]
        mean_log = sum(logs) / len(logs)
        ratio = math.exp(mean_log)
        log_sd = (
            sum((value - mean_log) ** 2 for value in logs)
            / max(len(logs) - 1, 1)
        ) ** 0.5
        frozen = float(production[channel]["ratio"])
        independent_n = len(values)
        production_n = int(production[channel]["n_days"])
        result[channel] = {
            "production_ratio": frozen,
            "production_n": production_n,
            "independent_ratio": round(ratio, 4),
            "independent_n": independent_n,
            "additional_independent_days": max(independent_n - production_n, 0),
            "relative_change_pct": (
                round(100 * (ratio / frozen - 1), 1)
                if independent_n > production_n
                else None
            ),
            "independent_log_sd": round(log_sd, 4),
        }
    return result


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
