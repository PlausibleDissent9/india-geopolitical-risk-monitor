"""Historical Intelligence v1: baselines, candidate breaks, analog retrieval.

WHAT THIS IS
The 1979-2019 back-extension has been a chart. This turns it into
something a researcher can interrogate: what a period's level actually
was and over what denominator, where the series changes level and how
that survives changing the settings, and which other months in the same
channel most resemble a chosen one.

WHAT THIS IS NOT
It is not history. The archive measures monthly event-mention share
under frozen actor-pair filters -- press attention, not conflict, risk,
escalation or outcome. A break is a break in attention. An analog is a
similarity between two months of one measured series, carrying no claim
that they shared circumstances and none whatever about what followed.
Nothing here forecasts, and the retrieval vocabulary is registered
against the words that would imply it.

EVERY REFUSAL IS PUBLISHED
Three of five channels do not publish, on grounds the source payload
already recorded: us_trade and gulf_energy failed the registered
2017-2019 overlap audit (r=0.216 and r=0.153) and shipping was excluded
at registration for lacking a defensible historical event analog. Those
are findings, so they travel in the payload rather than being dropped
from it. Likewise a period with too few observations, a month with too
few usable features, and a month with no human-authored archetype each
report unavailable WITH THE REASON, and never a zero.

Regenerate:  python -m src.historical_intelligence
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "governance" / "historical_intelligence_contract.json"
SOURCE_PATH = ROOT / "docs" / "data" / "back_extension.json"
OUT_PATH = ROOT / "docs" / "data" / "historical_intelligence.json"
BASELINES_CSV = ROOT / "docs" / "downloads" / "igrm-historical-regime-baselines.csv"
ANALOGS_CSV = ROOT / "docs" / "downloads" / "igrm-historical-analogs.csv"


class HistoricalIntelligenceError(RuntimeError):
    """A registered rule refused; the caller must not paper over it."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HistoricalIntelligenceError(code, str(exc)) from None
    if not isinstance(value, dict):
        raise HistoricalIntelligenceError(code, "not a JSON object")
    return value


# --------------------------------------------------------------------------
# month arithmetic, on "YYYY-MM" strings so the archive's own keys stay the
# identity everywhere and no date library can reinterpret them
# --------------------------------------------------------------------------
def _month_index(month: str) -> int:
    year, sep, mon = month.partition("-")
    if not sep or len(month) != 7:
        raise HistoricalIntelligenceError("historical_month_malformed", month)
    return int(year) * 12 + (int(mon) - 1)


def _in_period(month: str, start: str, end: str) -> bool:
    return _month_index(start) <= _month_index(month) <= _month_index(end)


# --------------------------------------------------------------------------
# descriptive statistics, written out rather than imported, so the published
# numbers depend on nothing that can change under us
# --------------------------------------------------------------------------
def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _percentile(values: list[float], pct: float) -> float:
    """Linear interpolation between order statistics."""
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * (pct / 100.0)
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return ordered[int(pos)]
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def _sample_stddev(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mu = _mean(values)
    return math.sqrt(sum((v - mu) ** 2 for v in values) / (len(values) - 1))


def _round(value: float | None, places: int = 6) -> float | None:
    if value is None:
        return None
    return round(value, places)


# --------------------------------------------------------------------------
# regime baselines
# --------------------------------------------------------------------------
def regime_baselines(contract: dict, series: dict) -> list[dict]:
    """Per channel and registered period, with every denominator stated."""
    spec = contract["regime_baselines"]
    min_observed = int(spec["min_observed_months"])
    eligible = contract["channel_eligibility"]["eligible"]
    rows: list[dict] = []
    for channel in eligible:
        chan = series[channel]
        months = chan["months"]
        for field in ("pctl_10y", "raw_share"):
            values = chan[field]
            for period in spec["periods"]:
                in_period = [
                    (m, v) for m, v in zip(months, values)
                    if _in_period(m, period["start"], period["end"])
                ]
                observed = [v for _, v in in_period if v is not None]
                n_calendar = len(in_period)
                row: dict[str, Any] = {
                    "channel": channel,
                    "series": field,
                    "period_id": period["id"],
                    "period_label": period["label"],
                    "period_start": period["start"],
                    "period_end": period["end"],
                    "n_months_in_period": n_calendar,
                    "n_observed": len(observed),
                    "coverage_fraction": (
                        _round(len(observed) / n_calendar, 4) if n_calendar else None
                    ),
                }
                if len(observed) < min_observed:
                    # A thin period reports WHY, not a number computed over
                    # whatever happened to be there. The first archive decade
                    # has no trailing-ten-year percentile at all, and a mean
                    # over its handful of defined months would read exactly
                    # like the others on the page.
                    row.update({
                        "available": False,
                        "unavailable_reason": (
                            f"only {len(observed)} observed months against a "
                            f"registered minimum of {min_observed}"
                        ),
                        "mean": None, "median": None, "p90": None,
                        "max": None, "min": None,
                    })
                else:
                    row.update({
                        "available": True,
                        "unavailable_reason": None,
                        "mean": _round(_mean(observed)),
                        "median": _round(_median(observed)),
                        "p90": _round(_percentile(observed, 90)),
                        "max": _round(max(observed)),
                        "min": _round(min(observed)),
                    })
                rows.append(row)
    return rows


# --------------------------------------------------------------------------
# candidate structural breaks
# --------------------------------------------------------------------------
def _prefix_sums(values: list[float]) -> tuple[list[float], list[float]]:
    s = [0.0]
    sq = [0.0]
    for v in values:
        s.append(s[-1] + v)
        sq.append(sq[-1] + v * v)
    return s, sq


def _segment_stats(s: list[float], sq: list[float], lo: int, hi: int
                   ) -> tuple[int, float, float]:
    """(n, mean, sample variance) for values[lo:hi], in constant time."""
    n = hi - lo
    total = s[hi] - s[lo]
    mean = total / n
    if n < 2:
        return n, mean, 0.0
    var = max((sq[hi] - sq[lo] - total * total / n) / (n - 1), 0.0)
    return n, mean, var


def _max_welch_t(values: list[float], min_segment: int) -> tuple[float, int]:
    """Largest |Welch t| over every admissible split, and its index."""
    s, sq = _prefix_sums(values)
    n = len(values)
    best_t = 0.0
    best_i = -1
    for split in range(min_segment, n - min_segment + 1):
        n1, m1, v1 = _segment_stats(s, sq, 0, split)
        n2, m2, v2 = _segment_stats(s, sq, split, n)
        denom = math.sqrt(v1 / n1 + v2 / n2)
        if denom <= 0.0:
            continue
        t = abs(m1 - m2) / denom
        if t > best_t:
            best_t = t
            best_i = split
    return best_t, best_i


def structural_breaks(contract: dict, series: dict) -> list[dict]:
    spec = contract["structural_breaks"]
    n_perm = int(spec["null_behaviour"]["n_permutations"])
    seed = int(spec["null_behaviour"]["seed"])
    rows: list[dict] = []
    for channel in contract["channel_eligibility"]["eligible"]:
        chan = series[channel]
        months = chan["months"]
        pairs = [(m, v) for m, v in zip(months, chan["raw_share"]) if v is not None]
        observed_months = [m for m, _ in pairs]
        values = [float(v) for _, v in pairs]
        sweep: list[dict] = []
        for min_segment in spec["sensitivity_settings"]:
            if len(values) < 2 * int(min_segment):
                sweep.append({
                    "min_segment_months": min_segment,
                    "available": False,
                    "unavailable_reason": (
                        f"{len(values)} observed months cannot support two "
                        f"segments of {min_segment}"
                    ),
                    "candidate_break_month": None,
                    "statistic": None,
                    "p_value": None,
                })
                continue
            stat, idx = _max_welch_t(values, int(min_segment))
            # The null destroys time ordering while keeping the value
            # distribution, so the question it answers is "does a series with
            # these values but no ordering produce a split this sharp".
            rng = random.Random(seed + int(min_segment))
            shuffled = list(values)
            hits = 0
            for _ in range(n_perm):
                rng.shuffle(shuffled)
                null_stat, _ = _max_welch_t(shuffled, int(min_segment))
                if null_stat >= stat:
                    hits += 1
            sweep.append({
                "min_segment_months": min_segment,
                "available": True,
                "unavailable_reason": None,
                "candidate_break_month": (
                    observed_months[idx] if 0 <= idx < len(observed_months) else None
                ),
                "statistic": _round(stat, 4),
                "p_value": _round((hits + 1) / (n_perm + 1), 5),
                "n_permutations": n_perm,
            })
        primary = next(
            (r for r in sweep
             if r["min_segment_months"] == spec["min_segment_months"]), None)
        stable = sorted({
            r["candidate_break_month"] for r in sweep
            if r["available"] and r["candidate_break_month"]
        })
        rows.append({
            "channel": channel,
            "series": "raw_share",
            "n_observed": len(values),
            "algorithm": spec["algorithm"],
            "primary": primary,
            "sensitivity_sweep": sweep,
            "distinct_candidates_across_settings": stable,
            "stable_across_all_settings": len(stable) == 1,
            "interpretation": (
                "Candidate break in the measured attention series, not a "
                "historical cause, turning point or explanation of any event."
            ),
        })
    return rows


# --------------------------------------------------------------------------
# analog retrieval
# --------------------------------------------------------------------------
def _features(chan: dict) -> dict[str, list[float | None]]:
    """The three registered features, with missingness preserved."""
    months = chan["months"]
    raw = chan["raw_share"]
    pctl = chan["pctl_10y"]
    change: list[float | None] = []
    vol: list[float | None] = []
    for i in range(len(months)):
        if i >= 12 and raw[i] is not None and raw[i - 12] is not None:
            change.append(raw[i] - raw[i - 12])
        else:
            change.append(None)
        window = [v for v in raw[max(0, i - 11):i + 1] if v is not None]
        vol.append(_sample_stddev(window) if len(window) >= 12 else None)
    return {
        "level_pctl_10y": list(pctl),
        "change_12m_raw_share": change,
        "volatility_12m_raw_share": vol,
    }


def _standardise(feature: list[float | None]) -> tuple[list[float | None], dict]:
    observed = [v for v in feature if v is not None]
    mu = _mean(observed) if observed else None
    sd = _sample_stddev(observed)
    if mu is None or not sd:
        return [None] * len(feature), {"mean": None, "stddev": None,
                                       "n_observed": len(observed)}
    return ([None if v is None else (v - mu) / sd for v in feature],
            {"mean": _round(mu), "stddev": _round(sd),
             "n_observed": len(observed)})


def analog_index(contract: dict, series: dict) -> tuple[dict, dict]:
    spec = contract["analog_retrieval"]
    n_return = int(spec["n_returned"])
    min_feats = int(spec["min_features_for_match"])
    window = int(spec["exclusion_window_months"])
    feature_ids = [f["id"] for f in spec["features"]]

    out: dict[str, Any] = {}
    standardisation: dict[str, Any] = {}
    for channel in contract["channel_eligibility"]["eligible"]:
        chan = series[channel]
        months = chan["months"]
        raw_feats = _features(chan)
        z: dict[str, list[float | None]] = {}
        standardisation[channel] = {}
        for fid in feature_ids:
            z[fid], standardisation[channel][fid] = _standardise(raw_feats[fid])

        entries: dict[str, Any] = {}
        for i, month in enumerate(months):
            usable_self = [f for f in feature_ids if z[f][i] is not None]
            if len(usable_self) < min_feats:
                entries[month] = {
                    "available": False,
                    "unavailable_reason": (
                        f"query month has {len(usable_self)} usable features "
                        f"against a registered minimum of {min_feats}"
                    ),
                    "features_present": usable_self,
                    "analogs": [],
                }
                continue
            scored: list[tuple[float, int, list[str], list[str]]] = []
            for j, other in enumerate(months):
                if abs(_month_index(other) - _month_index(month)) <= window:
                    continue
                used, excluded = [], []
                total = 0.0
                for fid in feature_ids:
                    a, b = z[fid][i], z[fid][j]
                    if a is None or b is None:
                        excluded.append(fid)
                        continue
                    total += (a - b) ** 2
                    used.append(fid)
                if len(used) < min_feats:
                    continue
                scored.append((math.sqrt(total), j, used, excluded))
            # Ties break on ascending month, so the same query is the same
            # ordered answer on every run and every platform.
            scored.sort(key=lambda r: (round(r[0], 12), months[r[1]]))
            entries[month] = {
                "available": True,
                "unavailable_reason": None,
                "features_present": usable_self,
                # The per-match reason is one sentence that was identical for
                # every match, so it is stated once at analog_retrieval.
                # reason_template rather than ~5000 times here: repeating it
                # tripled the payload without adding a fact, and a reader
                # deciding whether to trust a match needs the FEATURES, which
                # differ per pair, not the sentence, which does not.
                "analogs": [
                    {
                        "month": months[j],
                        "distance": _round(dist, 6),
                        "n_features_used": len(used),
                        "features_used": used,
                        "features_excluded_as_null": excluded,
                    }
                    for dist, j, used, excluded in scored[:n_return]
                ],
            }
        out[channel] = entries
    return out, standardisation


# --------------------------------------------------------------------------
# archetypes, human-authored only
# --------------------------------------------------------------------------
def archetypes(contract: dict, source: dict) -> list[dict]:
    cutoff = contract["knowledge_cutoff"]["archive_end"]
    eligible = contract["channel_eligibility"]["eligible"]
    refused = contract["channel_eligibility"]["refused"]
    rows: list[dict] = []
    for anchor in source.get("anchor_grades", []):
        month = anchor.get("month")
        channel = anchor.get("channel")
        if month and _month_index(month) > _month_index(cutoff):
            # Refused loudly rather than dropped: an annotation from after
            # the archive's registered end is exactly the leakage the
            # cutoff rule exists to stop, and silence would hide it.
            rows.append({
                "month": month, "channel": channel,
                "archetype": anchor.get("anchor"),
                "authorship": "human_authored_at_registration",
                "available": False,
                "unavailable_reason": (
                    f"anchor month {month} is after the registered knowledge "
                    f"cutoff {cutoff}"
                ),
            })
            continue
        available = channel in eligible
        rows.append({
            "month": month,
            "channel": channel,
            "archetype": anchor.get("anchor"),
            "pctl_trailing_10y": anchor.get("pctl_trailing_10y"),
            "top_decile": anchor.get("top_decile"),
            "authorship": "human_authored_at_registration",
            "available": available,
            "unavailable_reason": (
                None if available else refused.get(channel, "channel not eligible")
            ),
        })
    return rows


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------
def build() -> dict[str, Any]:
    contract = _load(CONTRACT_PATH, "historical_contract_unreadable")
    source = _load(SOURCE_PATH, "historical_source_unreadable")
    series = source.get("series")
    if not isinstance(series, dict):
        raise HistoricalIntelligenceError("historical_source_series_missing")
    for channel in contract["channel_eligibility"]["eligible"]:
        if channel not in series:
            raise HistoricalIntelligenceError(
                "historical_eligible_channel_absent", channel)

    analogs, standardisation = analog_index(contract, series)
    payload = {
        "_meta": {
            "schema": "igrm-historical-intelligence-v1",
            "what": contract["what"],
            "contract_path": "governance/historical_intelligence_contract.json",
            "contract_sha256": _sha256(CONTRACT_PATH),
            "source_path": "docs/data/back_extension.json",
            "source_sha256": _sha256(SOURCE_PATH),
            "implementation_path": "src/historical_intelligence.py",
            "implementation_sha256": _sha256(Path(__file__)),
            "knowledge_cutoff": contract["knowledge_cutoff"],
            "freshness_policy": contract["publication"]["freshness_policy"],
            "license": "CC BY 4.0",
            "citation": ("Krishna, Ishan (2026). India Geopolitical Risk "
                         "Monitor, Historical Intelligence v1. "
                         "https://igrm.in/history-lab.html"),
            "codebook": "https://igrm.in/codebook.html#historical-intelligence",
            "source": "https://igrm.in/data/historical_intelligence.json",
        },
        "channel_eligibility": contract["channel_eligibility"],
        "regime_baselines": {
            "registered_periods": contract["regime_baselines"]["periods"],
            "denominator_rule": contract["regime_baselines"]["denominator_rule"],
            "non_comparability": contract["regime_baselines"]["non_comparability"],
            "rows": regime_baselines(contract, series),
        },
        "structural_breaks": {
            "declared": contract["structural_breaks"]["declared"],
            "language_rule": contract["structural_breaks"]["language_rule"],
            "null_behaviour": contract["structural_breaks"]["null_behaviour"],
            "rows": structural_breaks(contract, series),
        },
        "analog_retrieval": {
            "policy": contract["analog_retrieval"]["policy"],
            "features": contract["analog_retrieval"]["features"],
            "distance": contract["analog_retrieval"]["distance"],
            "missingness_rule": contract["analog_retrieval"]["missingness_rule"],
            "reason_template": (
                "Nearest standardised distance over n_features_used of the "
                "registered features. Features listed in "
                "features_excluded_as_null were null for that pair and were "
                "excluded from the distance, never imputed and never zeroed."
            ),
            "exclusion_window_months": contract["analog_retrieval"][
                "exclusion_window_months"],
            "exclusion_reason": contract["analog_retrieval"]["exclusion_reason"],
            "determinism": contract["analog_retrieval"]["determinism"],
            "standardisation": standardisation,
            "by_channel": analogs,
        },
        "event_archetypes": {
            "policy": contract["event_archetypes"]["policy"],
            "machine_generated_permitted": False,
            "rows": archetypes(contract, source),
        },
        "limitations": contract["limitations"],
    }
    return payload


def _write_csvs(payload: dict) -> None:
    import csv

    BASELINES_CSV.parent.mkdir(parents=True, exist_ok=True)
    rows = payload["regime_baselines"]["rows"]
    with BASELINES_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    with ANALOGS_CSV.open("w", encoding="utf-8", newline="") as fh:
        rows_writer = csv.writer(fh)
        rows_writer.writerow(["channel", "query_month", "rank", "analog_month",
                              "distance", "n_features_used", "features_used",
                              "features_excluded_as_null"])
        for channel, entries in payload["analog_retrieval"]["by_channel"].items():
            for month in sorted(entries):
                entry = entries[month]
                for rank, a in enumerate(entry["analogs"], start=1):
                    rows_writer.writerow([
                        channel, month, rank, a["month"], a["distance"],
                        a["n_features_used"], "|".join(a["features_used"]),
                        "|".join(a["features_excluded_as_null"]),
                    ])


def main() -> None:
    payload = build()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    _write_csvs(payload)
    breaks = payload["structural_breaks"]["rows"]
    print(f"[historical-intelligence] wrote {OUT_PATH}")
    print(f"[historical-intelligence] baselines: "
          f"{len(payload['regime_baselines']['rows'])} rows")
    for row in breaks:
        primary = row["primary"] or {}
        print(f"[historical-intelligence] {row['channel']}: candidate break "
              f"{primary.get('candidate_break_month')} "
              f"stat={primary.get('statistic')} p={primary.get('p_value')} "
              f"stable_across_settings={row['stable_across_all_settings']}")


if __name__ == "__main__":
    main()
