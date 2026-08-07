"""An adversary that cannot be argued with: rebuild the index from the
PUBLISHED codebook and the PUBLISHED shares, and diff it against the
published series.

WHY THIS AND NOT A CRITIC
------------------------
The obvious way to push this project harder is a second model that reads
the work and objects to it. That does not work, and this repo has the
evidence. Every real defect found on 2026-08-06/07 was a VERIFICATION
failure, not a reasoning failure:

  * the blind-spot test was true 523/523 times by construction
  * the gap probe sampled a window with zero overlap with the gaps
  * the stamp step was placed wrong twice by reasoning and right once by
    listing the workflow's actual execution order
  * "one easing" was four; the duration test's regex could not see three
    of the durations it was cited as enforcing

A critic agent reasons over the same context and would have caught none
of them. Worse, its loop terminates when the writer produces prose the
critic finds satisfying, which optimises for persuasiveness rather than
truth.

So this adversary is not allowed to have opinions. Its only output is a
number and a diff.

THE RULE THAT MAKES IT BLIND
----------------------------
This module may read ONLY what a stranger can download:

    docs/codebook.html      the stated method
    docs/data/shares.csv    the published quantity
    docs/data/history.csv   the published result

It may not import src.scores or any other module that computes the
index, and `test_blind_replicator.py` enforces that by reading this
file's imports. If the transform here is wrong, the fix is to change the
CODEBOOK until a stranger could get it right -- never to peek at the
pipeline and quietly match it. Matching by peeking is what this is
designed to detect.

WHAT THE CODEBOOK SAYS
----------------------
Quoted from docs/codebook.html:

    "Channel percentile vs its own trailing 730 days, 0-100"
    "Every percentile is computed against the series' own trailing 730
     days, minimum 180 observations, never using future data."
    "Unweighted mean of the five channel percentiles, 0-100"
    "Composite percentile that day (null before 180 trailing obs)"

That is enough to write the transform. It is NOT enough to pin two
choices, and the whole value of this module is that it says so out loud
rather than guessing:

  1. What "percentile" means at ties and endpoints. Strictly-below,
     at-or-below, and midrank all satisfy "0-100" and differ by up to
     100/n points on the same data.
  2. Whether "trailing 730 days" counts CALENDAR days or OBSERVATIONS.
     The series has real gaps (2025-06-15..07-01 is missing upstream and
     is unfixable), so the two readings select different windows.

Rather than picking one, this evaluates the cross-product against the
published series and reports which combination reproduces it. That
turns an ambiguity into a measurement: the winning convention is the
sentence the codebook is missing, and the margin over the runners-up is
how much that missing sentence is worth.

  python -m src.blind_replicator            write docs/data/replication.json
  python -m src.blind_replicator --check    exit 1 if replication degrades
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"

CHANNELS = ["pakistan_west", "china_east", "gulf_energy", "us_trade", "shipping"]

WINDOW_DAYS = 730     # codebook: "its own trailing 730 days"
MIN_OBS = 180         # codebook: "minimum 180 observations"

# history.csv publishes one decimal place, so agreement is judged at the
# resolution actually published: round the rebuild the same way and
# require equality. The first version compared an UNROUNDED rebuild
# against a rounded file and reported three disagreements of exactly
# 0.05 -- 10.75 vs 10.8, 1.25 vs 1.2, 31.25 vs 31.2. All three were
# half-way values, and all three were an artifact of comparing different
# precisions, not a property of the pipeline. Comparing like with like is
# not tuning to match; it is the only comparison that means anything.
PRECISION = 1

# The unrounded gap is still reported, because it is the number that
# would grow first if the transform ever drifted.
NEAR = 0.05

# Measured: 19830 of 19830. An exact reproduction is either true or it
# is not, so the floor is exact. A legitimate methodology change WILL
# break this, and that is the point -- the codebook is then obliged to
# change with the method before the lane goes green again. Lowering this
# to clear a red run is the exact failure this module exists to expose.
MIN_AGREEMENT = 1.0


# --------------------------------------------------------------------
# The two conventions the codebook does not pin.
# --------------------------------------------------------------------
def _pctl_strict(window: list[float], x: float) -> float:
    """Share of the window strictly below x."""
    return 100.0 * sum(1 for v in window if v < x) / len(window)


def _pctl_weak(window: list[float], x: float) -> float:
    """Share of the window at or below x."""
    return 100.0 * sum(1 for v in window if v <= x) / len(window)


def _pctl_midrank(window: list[float], x: float) -> float:
    """Strictly-below plus half the ties -- the convention
    scipy.stats.percentileofscore calls kind='mean'."""
    below = sum(1 for v in window if v < x)
    ties = sum(1 for v in window if v == x)
    return 100.0 * (below + 0.5 * ties) / len(window)


PCTL_KINDS = {
    "strict": _pctl_strict,
    "weak": _pctl_weak,
    "midrank": _pctl_midrank,
}

WINDOW_KINDS = ["calendar", "observations"]


def read_shares() -> dict[str, dict[date, float]]:
    """docs/data/shares.csv -- 'The quantity, not the transform.'"""
    out: dict[str, dict[date, float]] = {c: {} for c in CHANNELS}
    with (SITE_DATA / "shares.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            d = date.fromisoformat(row["date"])
            for ch in CHANNELS:
                raw = (row.get(ch) or "").strip()
                if raw:
                    try:
                        out[ch][d] = float(raw)
                    except ValueError:
                        pass
    return out


def read_published() -> dict[date, dict[str, float]]:
    out: dict[date, dict[str, float]] = {}
    with (SITE_DATA / "history.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            d = date.fromisoformat(row["date"])
            vals: dict[str, float] = {}
            for col in CHANNELS + ["composite"]:
                raw = (row.get(col) or "").strip()
                if raw:
                    try:
                        vals[col] = float(raw)
                    except ValueError:
                        pass
            out[d] = vals
    return out


def replicate(shares: dict[str, dict[date, float]],
              pctl_kind: str,
              window_kind: str) -> dict[date, dict[str, float]]:
    """The codebook's transform, under one reading of the two ambiguities."""
    pctl = PCTL_KINDS[pctl_kind]
    scores: dict[date, dict[str, float]] = {}

    for ch in CHANNELS:
        series = sorted(shares[ch].items())
        values = [v for _, v in series]
        days = [d for d, _ in series]

        for i, (d, x) in enumerate(series):
            if window_kind == "calendar":
                # Every observation within 730 calendar days ending today,
                # inclusive. "never using future data" fixes the upper end.
                lo = d - timedelta(days=WINDOW_DAYS - 1)
                j = i
                while j > 0 and days[j - 1] >= lo:
                    j -= 1
                window = values[j:i + 1]
            else:
                # The last 730 observations, gaps ignored.
                window = values[max(0, i - WINDOW_DAYS + 1):i + 1]

            if len(window) < MIN_OBS:
                continue
            scores.setdefault(d, {})[ch] = pctl(window, x)

    # "Unweighted mean of the five channel percentiles, 0-100", published
    # "null before 180 trailing obs".
    for vals in scores.values():
        present = [vals[c] for c in CHANNELS if c in vals]
        if len(present) == len(CHANNELS):
            vals["composite"] = sum(present) / len(present)
    return scores


def compare(mine: dict[date, dict[str, float]],
            theirs: dict[date, dict[str, float]]) -> dict[str, Any]:
    """Agreement on the days and columns BOTH produced."""
    n = 0
    agree = 0
    worst = 0.0
    worst_at: str | None = None
    per_col: dict[str, dict[str, float]] = {}

    for d, published in theirs.items():
        got = mine.get(d, {})
        for col, want in published.items():
            if col not in got:
                continue
            diff = abs(got[col] - want)
            n += 1
            slot = per_col.setdefault(col, {"n": 0, "agree": 0, "max_diff": 0.0})
            slot["n"] += 1
            # Judged at the precision actually published.
            if round(got[col], PRECISION) == want:
                agree += 1
                slot["agree"] += 1
            slot["max_diff"] = max(slot["max_diff"], round(diff, 4))
            if diff > worst:
                worst, worst_at = diff, f"{d} {col}"

    return {
        "n_compared": n,
        "n_agree": agree,
        "agreement": round(agree / n, 6) if n else 0.0,
        "max_abs_diff": round(worst, 4),
        "max_abs_diff_at": worst_at,
        "per_column": {k: {**v, "agreement": round(v["agree"] / v["n"], 6)}
                       for k, v in sorted(per_col.items())},
    }


def run_all() -> list[dict[str, Any]]:
    shares = read_shares()
    published = read_published()
    results = []
    for pk in PCTL_KINDS:
        for wk in WINDOW_KINDS:
            res = compare(replicate(shares, pk, wk), published)
            res["percentile_convention"] = pk
            res["window_convention"] = wk
            results.append(res)
    results.sort(key=lambda r: (-r["agreement"], r["max_abs_diff"]))
    return results


def main() -> None:
    check = "--check" in sys.argv
    results = run_all()
    best = results[0]
    runner_up = results[1] if len(results) > 1 else None

    from src import stamp_meta
    payload: dict[str, Any] = {
        "_meta": {
            **stamp_meta.universal_fields("replication.json"),
            "what": (
                "An independent rebuild of the published index from the "
                "published codebook and the published shares, diffed "
                "against the published series. Written without reading "
                "the pipeline: if it disagrees, either the codebook does "
                "not say enough for a stranger to reproduce the number, "
                "or the pipeline does something the codebook does not "
                "describe. Both are defects, and neither can be argued "
                "away."),
            "inputs": [
                "docs/codebook.html", "docs/data/shares.csv",
                "docs/data/history.csv"],
            "why_not_a_critic": (
                "A second model reading the work and objecting to it "
                "reasons over the same context, and its loop ends when "
                "the writing becomes persuasive rather than when the "
                "number becomes right. This adversary is not permitted "
                "an opinion; its whole output is a diff."),
            "precision": PRECISION,
            "precision_note": (
                "history.csv publishes one decimal place, so the rebuild "
                "is rounded the same way and equality is required. An "
                "earlier version compared an unrounded rebuild against a "
                "rounded file and reported three 0.05 disagreements that "
                "were entirely an artifact of comparing different "
                "precisions."),
            "finding": (
                f"{best['n_agree']} of {best['n_compared']} published "
                "values are reproduced exactly, by code that has never "
                "read the pipeline, from the codebook and the shares "
                "file alone."
                if best["agreement"] >= 1.0 else
                f"{best['n_agree']} of {best['n_compared']} reproduced; "
                "the series is NOT currently reproducible from its own "
                "documentation."),
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "best": best,
        "all_conventions": results,
        "ambiguities_in_the_codebook": [
            {
                "ambiguity": (
                    "The codebook says 'percentile ... 0-100' but does "
                    "not define the convention at ties: strictly-below, "
                    "at-or-below and midrank all satisfy it and differ by "
                    "up to 100/n points on identical data."),
                "resolved_by_measurement": best["percentile_convention"],
                "margin_over_next": None,
            },
            {
                "ambiguity": (
                    "'trailing 730 days' does not say whether the window "
                    "counts calendar days or observations. The series has "
                    "real gaps (2025-06-15..07-01, missing upstream and "
                    "unfixable), so the two readings select different "
                    "windows."),
                "resolved_by_measurement": best["window_convention"],
                "margin_over_next": None,
            },
            {
                "ambiguity": (
                    "The codebook does not state how a value exactly "
                    "half-way between two published decimals is rounded. "
                    "Three days land there: 10.75, 1.25 and 31.25."),
                "resolved_by_measurement": (
                    "round-half-to-even (Python's round). 1.25 publishes "
                    "as 1.2 and 31.25 as 31.2, not 1.3 and 31.3."),
                "margin_over_next": None,
                "note": (
                    "Worth three values in twenty thousand, and listed "
                    "anyway: the point of this file is the complete set "
                    "of sentences a stranger would need, not the "
                    "important ones."),
            },
        ],
    }
    if runner_up:
        margin = round(best["agreement"] - runner_up["agreement"], 6)
        for a in payload["ambiguities_in_the_codebook"]:
            a["margin_over_next"] = margin

    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / "replication.json").write_text(
        json.dumps(payload, indent=1), encoding="utf-8")

    print(f"[blind_replicator] best: {best['percentile_convention']} / "
          f"{best['window_convention']} -- "
          f"{best['n_agree']}/{best['n_compared']} values agree "
          f"({best['agreement']:.4%}), max diff {best['max_abs_diff']} "
          f"at {best['max_abs_diff_at']}")
    for r in results[1:]:
        print(f"[blind_replicator]   {r['percentile_convention']:>8} / "
              f"{r['window_convention']:<12} {r['agreement']:.4%} "
              f"max {r['max_abs_diff']}")

    if check and best["agreement"] < MIN_AGREEMENT:
        raise SystemExit(
            f"[blind_replicator] an independent rebuild from the published "
            f"codebook reproduces only {best['agreement']:.4%} of published "
            f"values (floor {MIN_AGREEMENT:.4%}). Either the pipeline "
            f"changed without the codebook changing, or the codebook was "
            f"never sufficient. Do not lower MIN_AGREEMENT to clear this.")


if __name__ == "__main__":
    main()
