"""Registered benchmark against the Iacoviello-Tong AI-GPR India series.

The registration and this script ship before any statistic is computed.
The result writer publishes aggregates and ranks only; it never republishes
the provider's monthly values.

Run after the registration commit is public:

    python -m src.ai_gpr_benchmark
    python -m src.ai_gpr_benchmark --source /path/to/pinned.csv
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from calendar import monthrange
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "docs" / "data" / "history.csv"
EPISODES = ROOT / "validation" / "validation_episodes.json"
REGISTRATION = ROOT / "analysis" / "ai_gpr_benchmark_registration.json"
OUTPUT = ROOT / "docs" / "data" / "ai_gpr_benchmark.json"

AI_GPR_URL = "https://www.matteoiacoviello.com/ai_gpr_files/ai_gpr_country_monthly.csv"
AI_GPR_SHA256 = "22750ad1e1bf0e3420f87a0810da3fbebf00d308d67d103ee5a236db3d9d17e3"
AI_GPR_DATA_THROUGH = "2026-07-01"
IGRM_HISTORY_SHA256 = "79885e7bf472a66faf48d8ee50e7fcc9a909171e4e2d8106a4f20ed46d24b32c"
EPISODES_SHA256 = "5730d7a8b611b466d94adffd004373bf7df25731abbde625fdd78082b44f8254"

IGRM_SERIES = [
    "composite",
    "pakistan_west",
    "china_east",
    "gulf_energy",
    "us_trade",
    "shipping",
]
AI_SERIES = ["India_all", "India_initiator", "India_respondent", "India_spillover"]

MIN_DAYS = 15
BOOTSTRAP_DRAWS = 10_000
BLOCK_LENGTHS = [6, 12]
RANDOM_SEED = 20_260_807


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _verify_registration() -> dict[str, Any]:
    """Fail before reading data if the registered analysis code changed."""
    script_hash = _sha256(Path(__file__).read_bytes())
    registration = json.loads(REGISTRATION.read_text(encoding="utf-8"))
    registered_script_hash = registration["analysis_script_sha256"]
    if script_hash != registered_script_hash:
        raise SystemExit(
            "[ai-gpr] analysis script changed after registration: expected "
            f"{registered_script_hash}, got {script_hash}"
        )
    return registration


def _verify_local_inputs() -> None:
    """Pin the IGRM vintage and the descriptive event list used in the run."""
    pinned = [
        (HISTORY, IGRM_HISTORY_SHA256, "IGRM history"),
        (EPISODES, EPISODES_SHA256, "episode list"),
    ]
    for path, expected, label in pinned:
        observed = _sha256(path.read_bytes())
        if observed != expected:
            raise SystemExit(
                f"[ai-gpr] {label} changed after registration: expected {expected}, got {observed}"
            )


def _source_bytes(source: Path | None) -> bytes:
    if source is not None:
        data = source.read_bytes()
    else:
        response = requests.get(
            AI_GPR_URL,
            timeout=90,
            headers={"User-Agent": "IGRM research benchmark (igrm.in)"},
        )
        response.raise_for_status()
        data = response.content
    digest = _sha256(data)
    if digest != AI_GPR_SHA256:
        raise SystemExit(
            "[ai-gpr] source vintage changed: expected "
            f"{AI_GPR_SHA256}, got {digest}; do not run the registered "
            "analysis on an unregistered vintage"
        )
    return data


def _load_ai(data: bytes) -> pd.DataFrame:
    frame = pd.read_csv(io.BytesIO(data), parse_dates=["Date"])
    missing = [column for column in AI_SERIES if column not in frame.columns]
    if missing:
        raise SystemExit(f"[ai-gpr] source is missing registered columns: {missing}")
    if frame["Date"].duplicated().any():
        raise SystemExit("[ai-gpr] source has duplicate months")
    frame = frame.set_index("Date").sort_index()
    if not frame.index.is_monotonic_increasing:
        raise SystemExit("[ai-gpr] source dates are not monotonic")
    if any(date.day != 1 for date in frame.index):
        raise SystemExit("[ai-gpr] source dates are not month starts")
    through = frame.index.max().date().isoformat()
    if through != AI_GPR_DATA_THROUGH:
        raise SystemExit(
            f"[ai-gpr] registered data-through is {AI_GPR_DATA_THROUGH}, got {through}"
        )
    return frame[AI_SERIES].apply(pd.to_numeric, errors="coerce")


def _load_igrm() -> tuple[pd.DataFrame, pd.Series]:
    daily = pd.read_csv(HISTORY, parse_dates=["date"]).set_index("date").sort_index()
    missing = [column for column in IGRM_SERIES if column not in daily.columns]
    if missing:
        raise SystemExit(f"[ai-gpr] history.csv is missing registered columns: {missing}")
    monthly = daily[IGRM_SERIES].resample("MS").mean()
    counts = daily["composite"].resample("MS").count()
    return monthly, counts


def _sample(ai: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    igrm, counts = _load_igrm()
    common = igrm.index.intersection(ai.index).sort_values()
    complete = pd.Timestamp(AI_GPR_DATA_THROUGH)
    eligible = [
        month
        for month in common
        if counts.get(month, 0) >= MIN_DAYS
        and month <= complete
        and pd.notna(ai.at[month, "India_all"])
    ]
    levels = pd.concat(
        [
            igrm.loc[eligible].add_prefix("igrm__"),
            ai.loc[eligible].add_prefix("ai__"),
        ],
        axis=1,
    )
    months = [month.date().isoformat() for month in levels.index]
    return levels, months


def _consecutive_changes(levels: pd.DataFrame) -> pd.DataFrame:
    month_number = levels.index.year * 12 + levels.index.month
    consecutive = np.r_[False, np.diff(month_number) == 1]
    return levels.diff().loc[consecutive]


def _corr(x: pd.Series, y: pd.Series, method: str) -> tuple[float | None, int]:
    joint = pd.concat([x, y], axis=1).dropna()
    if len(joint) < 3 or joint.iloc[:, 0].nunique() < 2 or joint.iloc[:, 1].nunique() < 2:
        return None, int(len(joint))
    value = joint.iloc[:, 0].corr(joint.iloc[:, 1], method=method)
    return round(float(value), 3), int(len(joint))


def _rank_corr_arrays(x: np.ndarray, y: np.ndarray) -> float:
    xr = pd.Series(x).rank(method="average").to_numpy()
    yr = pd.Series(y).rank(method="average").to_numpy()
    return float(np.corrcoef(xr, yr)[0, 1])


def _candidate_blocks(index: pd.DatetimeIndex, length: int) -> list[list[int]]:
    """Return paired blocks without ever crossing a calendar-chain break.

    Full-length moving windows come from segments at least ``length`` months
    long. A shorter segment remains eligible as one whole block, so chain-edge
    observations are not silently discarded from the registered bootstrap.
    """
    month_number = index.year * 12 + index.month
    breaks = np.flatnonzero(np.diff(month_number) != 1) + 1
    segments = np.split(np.arange(len(index)), breaks)
    blocks: list[list[int]] = []
    for segment in segments:
        if not len(segment):
            continue
        if len(segment) < length:
            blocks.append(segment.tolist())
            continue
        blocks.extend(
            segment[start : start + length].tolist() for start in range(len(segment) - length + 1)
        )
    return blocks


def _moving_block_ci(
    pairs: pd.DataFrame,
    block_length: int,
    draws: int = BOOTSTRAP_DRAWS,
    seed: int = RANDOM_SEED,
) -> list[float]:
    clean = pairs.dropna()
    blocks = _candidate_blocks(clean.index, block_length)
    if len(clean) < 3 or not blocks:
        raise SystemExit("[ai-gpr] too few paired observations for registered bootstrap")
    rng = np.random.default_rng(seed + block_length)
    values = clean.to_numpy(dtype=float)
    n = len(values)
    estimates = np.empty(draws, dtype=float)
    for draw in range(draws):
        for _attempt in range(1_000):
            sampled: list[int] = []
            while len(sampled) < n:
                sampled.extend(blocks[int(rng.integers(0, len(blocks)))])
            take = sampled[:n]
            estimate = _rank_corr_arrays(values[take, 0], values[take, 1])
            if np.isfinite(estimate):
                estimates[draw] = estimate
                break
        else:
            raise SystemExit("[ai-gpr] bootstrap repeatedly produced an undefined rho")
    return [
        round(float(np.quantile(estimates, 0.025)), 3),
        round(float(np.quantile(estimates, 0.975)), 3),
    ]


def _autocorrelation(series: pd.Series) -> float | None:
    clean = series.dropna()
    if len(clean) < 3 or clean.nunique() < 2:
        return None
    return round(float(clean.autocorr(lag=1)), 3)


def _decision_language(rho: float, ci: list[float]) -> str:
    low, high = ci
    if rho < 0 and high < 0:
        return (
            "The measures diverge systematically; published as found, "
            "investigation registered separately."
        )
    if low > 0 and rho >= 0.5:
        return "Month-over-month movements in the two measures co-move substantially."
    if low > 0 and 0 < rho < 0.5:
        return "The two measures share a common component but are far from redundant."
    return (
        "At monthly frequency the two measures are largely distinct; "
        "divergence months are listed for inspection."
    )


def _exploratory(levels: pd.DataFrame, changes: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for igrm_name in IGRM_SERIES:
        for ai_name in AI_SERIES:
            level_rho, n_levels = _corr(
                levels[f"igrm__{igrm_name}"], levels[f"ai__{ai_name}"], "spearman"
            )
            change_rho, n_changes = _corr(
                changes[f"igrm__{igrm_name}"], changes[f"ai__{ai_name}"], "spearman"
            )
            rows.append(
                {
                    "igrm_series": igrm_name,
                    "ai_gpr_series": ai_name,
                    "spearman_levels": level_rho,
                    "n_levels": n_levels,
                    "spearman_changes": change_rho,
                    "n_changes": n_changes,
                }
            )
    return rows


def _episode_month_ranks(levels: pd.DataFrame) -> list[dict[str, Any]]:
    episodes = json.loads(EPISODES.read_text(encoding="utf-8"))["episodes"]
    ai_rank = levels["ai__India_all"].rank(pct=True, method="average") * 100
    rows: list[dict[str, Any]] = []
    for episode in episodes:
        month = pd.Timestamp(episode["date"]).to_period("M").to_timestamp()
        if month not in levels.index or pd.isna(ai_rank.get(month)):
            continue
        rows.append(
            {
                "name": episode["name"],
                "channel": episode["channel"],
                "event_date": episode["date"],
                "month": month.date().isoformat(),
                "ai_gpr_india_all_within_sample_rank": round(float(ai_rank.at[month]), 1),
            }
        )
    return rows


def _divergence_months(levels: pd.DataFrame) -> list[dict[str, Any]]:
    pair = levels[["igrm__composite", "ai__India_all"]].dropna()
    ranks = pair.rank(pct=True, method="average") * 100
    ranks["absolute_gap"] = (ranks.iloc[:, 0] - ranks.iloc[:, 1]).abs()
    ordered = ranks.sort_values(by="absolute_gap", ascending=False, kind="mergesort")
    selected: list[tuple[pd.Timestamp, pd.Series]] = []
    for month, row in ordered.iterrows():
        ordinal = month.year * 12 + month.month
        if any(abs(ordinal - (prior.year * 12 + prior.month)) == 1 for prior, _ in selected):
            continue
        selected.append((month, row))
        if len(selected) == 5:
            break

    rows: list[dict[str, Any]] = []
    for month, row in selected:
        last_day = monthrange(month.year, month.month)[1]
        rows.append(
            {
                "month": month.date().isoformat(),
                "igrm_composite_rank": round(float(row["igrm__composite"]), 1),
                "ai_gpr_india_all_rank": round(float(row["ai__India_all"]), 1),
                "absolute_gap": round(float(row["absolute_gap"]), 1),
                "igrm_evidence_url": (
                    "https://igrm.in/explorer.html?from="
                    f"{month.date().isoformat()}&to={month.year}-{month.month:02d}-{last_day:02d}"
                ),
            }
        )
    return rows


def build(source: Path | None = None) -> dict[str, Any]:
    _verify_registration()
    _verify_local_inputs()
    source_data = _source_bytes(source)
    ai = _load_ai(source_data)
    levels, months = _sample(ai)
    changes = _consecutive_changes(levels)

    primary_pairs = changes[["igrm__composite", "ai__India_all"]].dropna()
    primary_rho, n_changes = _corr(primary_pairs.iloc[:, 0], primary_pairs.iloc[:, 1], "spearman")
    if primary_rho is None:
        raise SystemExit("[ai-gpr] registered primary correlation is undefined")
    ci_by_block = {str(length): _moving_block_ci(primary_pairs, length) for length in BLOCK_LENGTHS}

    level_spearman, n_levels = _corr(levels["igrm__composite"], levels["ai__India_all"], "spearman")
    level_pearson, _ = _corr(levels["igrm__composite"], levels["ai__India_all"], "pearson")
    change_pearson, _ = _corr(changes["igrm__composite"], changes["ai__India_all"], "pearson")

    script_hash = _sha256(Path(__file__).read_bytes())

    return {
        "_meta": {
            "what": (
                "Pre-registered comparison of monthly IGRM salience with the "
                "Iacoviello-Tong AI-GPR India series. Aggregates and ranks "
                "only; no AI-GPR source values are redistributed."
            ),
            "registration": "analysis/ai_gpr_benchmark_registration.json",
            "analysis_script_sha256": script_hash,
            "source_url": AI_GPR_URL,
            "source_sha256": _sha256(source_data),
            "source_data_through": AI_GPR_DATA_THROUGH,
            "igrm_history_sha256": IGRM_HISTORY_SHA256,
            "episode_list_sha256": EPISODES_SHA256,
            "provider_citation": (
                "Iacoviello, Matteo and Jonathan Tong (2026), 'The AI-GPR "
                "Index: Measuring Geopolitical Risk using Artificial Intelligence.'"
            ),
            "raw_values_redistributed": False,
            "deviations_from_registration": [],
            "forbidden_claims": [
                "beats",
                "outperforms",
                "more accurate",
                "validates",
                "confirms IGRM measures risk",
            ],
            "registered_discussion_frames": [
                "corpus difference: three US newspapers versus global GDELT coverage",
                "construct difference: geopolitical risk intensity versus press-salience share",
                "anchoring difference: a global country score versus India-specific fault-line channels",
            ],
        },
        "sample": {
            "months": months,
            "n_levels": n_levels,
            "n_changes": n_changes,
            "minimum_valid_igrm_days_per_month": MIN_DAYS,
            "changes_bridge_missing_months": False,
        },
        "primary": {
            "statistic": "Spearman rho, month-over-month changes",
            "rho": primary_rho,
            "moving_block_bootstrap_95_ci": ci_by_block,
            "bootstrap_draws": BOOTSTRAP_DRAWS,
            "random_seed": RANDOM_SEED,
            "decision_language": _decision_language(primary_rho, ci_by_block["6"]),
        },
        "descriptive_primary": {
            "spearman_levels": level_spearman,
            "pearson_changes": change_pearson,
            "pearson_levels": level_pearson,
            "autocorrelation": {
                "igrm_composite_levels_lag1": _autocorrelation(levels["igrm__composite"]),
                "ai_gpr_india_all_levels_lag1": _autocorrelation(levels["ai__India_all"]),
                "igrm_composite_changes_lag1": _autocorrelation(changes["igrm__composite"]),
                "ai_gpr_india_all_changes_lag1": _autocorrelation(changes["ai__India_all"]),
            },
        },
        "exploratory_correlations": _exploratory(levels, changes),
        "episode_month_ranks": {
            "warning": (
                "Descriptive only. The episode list was selected for IGRM's "
                "construct; no AI-GPR detection rate is computed."
            ),
            "rows": _episode_month_ranks(levels),
        },
        "largest_rank_divergences": _divergence_months(levels),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    payload = build(args.source)
    OUTPUT.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    primary = payload["primary"]
    print(
        "[ai-gpr] wrote ai_gpr_benchmark.json: "
        f"rho={primary['rho']}, CI={primary['moving_block_bootstrap_95_ci']['6']}"
    )


if __name__ == "__main__":
    main()
