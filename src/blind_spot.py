"""
The detector cannot see a second crisis (referee finding #26,
2026-08-07).

Episode detection fires when a channel's share exceeds its trailing
90-day mean plus two standard deviations, both lagged one day. The rule
is registered, frozen, and defensible. It also has a structural
consequence that the project had never quantified: a crisis raises its
own future threshold, because the crisis days enter the very window the
threshold is computed from. The mean rises, the standard deviation rises
faster, and the bar climbs for ninety days -- peaking, absurdly, *after*
the crisis is over.

Measured on pakistan_west through Pahalgam and Sindoor:

    2025-04-21 (day before Pahalgam)  threshold 0.0244
    2025-05-10 (ceasefire)            threshold 0.4740   19.4x
    2025-06-10 (seven weeks later)    threshold 0.6334   26.0x
    2025-07-20 (ninety days after)    threshold 0.6912   28.4x

On 2025-05-20 the channel's share was 0.1340 -- five and a half times
the pre-crisis threshold, an unambiguous spike by the standard that
applied three weeks earlier -- and the detector stayed silent, because
by then the bar was 0.6207.

So the honest statement is not "the detector may miss things during
crises". It is: for roughly ninety days after a major episode, a
channel is close to blind, and the larger the first crisis the blinder
it goes. A second event has to rival the first to be seen at all.

WHY THE RULE IS NOT CHANGED
---------------------------
Every obvious fix is worse. Excluding spike days from the baseline
means the analyst decides what counts as a spike before measuring
spikes. A fixed historical threshold abandons the per-channel
adaptivity that makes the five channels comparable. A longer window
delays first detection, which is the thing the detector is actually
for. The rule was registered in advance and it stays; what changes is
that its cost is now measured, published, and attached to the episode
list rather than left for a user to infer.

This module computes, for every detected episode, how high the bar goes
and how many days afterwards carry a share that the PRE-crisis
threshold would have flagged and the live threshold did not. That last
count is the blind spot in days, not in adjectives.

  python -m src.blind_spot     writes docs/data/detector_blindness.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src import build_index as bi

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"
STORE = ROOT / "data" / "raw" / "gdelt_volume.csv"

# How long after an episode ends to follow the threshold. The baseline
# window is 90 days, so 120 covers the full contamination plus a month
# of recovery.
FOLLOW_DAYS = 120
# "Recovered" = the bar is back within this multiple of where it stood
# the day before the episode began.
RECOVERY_MULTIPLE = 2.0


def threshold_path(s: pd.Series) -> pd.DataFrame:
    """The detector's own arithmetic, reproduced exactly: trailing
    90-day mean and sd, both lagged one day, threshold = mu + 2 sd."""
    base = s.rolling(f"{bi.EPISODE_BASELINE_DAYS}D",
                     min_periods=bi.EPISODE_MIN_OBS)
    mu = base.mean().shift(1)
    sd = base.std().shift(1)
    return pd.DataFrame({"share": s, "mu": mu, "sd": sd,
                         "threshold": mu + bi.EPISODE_SIGMA * sd})


def analyse_channel(s: pd.Series, channel: str,
                    exclusions: list[dict[str, str]] | None = None
                    ) -> list[dict[str, Any]]:
    path = threshold_path(s)
    episodes = bi.detect_episodes(s, channel)
    out: list[dict[str, Any]] = []
    for ep in episodes:
        start = pd.Timestamp(ep["start"])
        end = pd.Timestamp(ep["end"])
        day_before = start - pd.Timedelta(days=1)
        if day_before not in path.index:
            if exclusions is not None:
                exclusions.append({
                    "channel": channel,
                    "episode_start": ep["start"],
                    "episode_end": ep["end"],
                    "reason": "day before episode absent from share store",
                })
            continue
        pre = path.loc[day_before, "threshold"]
        if not (pre > 0):
            if exclusions is not None:
                exclusions.append({
                    "channel": channel,
                    "episode_start": ep["start"],
                    "episode_end": ep["end"],
                    "reason": "pre-episode threshold unavailable or non-positive",
                })
            continue

        # The peak is searched from the episode's START, not from its
        # end. Searching only afterwards would make
        # "the bar peaked after the episode ended" true by construction
        # -- a tautology dressed as a finding, which is worse than no
        # finding at all.
        span = path.loc[start:end + pd.Timedelta(days=FOLLOW_DAYS)]
        after = path.loc[end:end + pd.Timedelta(days=FOLLOW_DAYS)].iloc[1:]
        if after.empty or span.empty:
            if exclusions is not None:
                exclusions.append({
                    "channel": channel,
                    "episode_start": ep["start"],
                    "episode_end": ep["end"],
                    "reason": "insufficient post-episode follow-up window",
                })
            continue

        peak = float(span["threshold"].max())
        peak_day = span["threshold"].idxmax()

        # Days the OLD bar would have flagged and the LIVE bar did not.
        # This is the blind spot expressed as a count of real days with
        # real coverage on them, not as a caveat.
        suppressed = after[(after["share"] > pre)
                           & (after["share"] <= after["threshold"])]

        recovered = after[after["threshold"] <= pre * RECOVERY_MULTIPLE]
        days_to_recover = (int((recovered.index[0] - end).days)
                           if not recovered.empty else None)

        out.append({
            "channel": channel,
            "episode_start": ep["start"],
            "episode_end": ep["end"],
            "peak_share_in_episode": round(float(ep["peak_value"]), 6),
            "threshold_before": round(float(pre), 6),
            "threshold_peak_after": round(peak, 6),
            "threshold_peak_multiple": round(peak / pre, 1),
            "threshold_peak_day": peak_day.date().isoformat(),
            "peak_bar_is_after_episode_ended": bool(peak_day > end),
            "n_days_suppressed": int(len(suppressed)),
            "suppressed_days": [d.date().isoformat()
                                for d in suppressed.index],
            "max_suppressed_share": (round(float(suppressed["share"].max()), 6)
                                     if not suppressed.empty else None),
            "max_suppressed_multiple_of_old_bar": (
                round(float(suppressed["share"].max() / pre), 1)
                if not suppressed.empty else None),
            "days_until_bar_within_2x": days_to_recover,
        })
    return out


def main() -> None:
    v = pd.read_csv(STORE, parse_dates=["date"]).set_index("date")
    rows: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    for ch in v.columns:
        rows.extend(analyse_channel(v[ch].dropna(), ch, exclusions))

    rows.sort(key=lambda r: (r["channel"], r["episode_start"]))
    multiples = [r["threshold_peak_multiple"] for r in rows]
    late_peak = sum(1 for r in rows if r["peak_bar_is_after_episode_ended"])
    recoveries = [r["days_until_bar_within_2x"] for r in rows
                  if r["days_until_bar_within_2x"] is not None]

    # Episode follow-windows overlap heavily, so SUMMING per-episode
    # suppressed days counts the same calendar day many times over and
    # would have reported a number larger than the series itself. The
    # honest total is the union of distinct channel-days.
    unique_suppressed: dict[str, set[str]] = {}
    for r in rows:
        unique_suppressed.setdefault(r["channel"], set()).update(
            r["suppressed_days"])
    suppressed_unique = {ch: len(d) for ch, d in unique_suppressed.items()}
    suppressed_total = sum(suppressed_unique.values())

    # The blind spot scales with episode size: a one-day blip barely
    # moves the bar, a Sindoor moves it 28-fold. Reporting only the
    # median would hide exactly the cases that matter, and reporting
    # only the max would overstate the typical one. Both, plus the
    # large-episode subset, or the summary lies in one direction or the
    # other.
    big = sorted(rows, key=lambda r: -r["peak_share_in_episode"])[:10]

    payload: dict[str, Any] = {
        "_meta": {
            "what": (
                "How blind the episode detector goes after it fires. A "
                "crisis enters the trailing window its own future "
                "threshold is computed from, so the bar rises for 90 "
                "days and a second event has to rival the first to be "
                "seen."),
            "rule": (
                f"Spike day = share > trailing "
                f"{bi.EPISODE_BASELINE_DAYS}-day mean + "
                f"{bi.EPISODE_SIGMA} sd, baseline lagged one day. "
                "Registered in advance and unchanged."),
            "n_days_suppressed_meaning": (
                "Days after an episode whose share exceeded the "
                "threshold that applied the day BEFORE that episode "
                "began, but not the live threshold. These are days a "
                "pre-crisis detector would have flagged and this one did "
                "not. They are the blind spot counted in days."),
            "why_the_rule_is_not_changed": (
                "Every obvious fix is worse. Excluding spike days from "
                "the baseline makes the analyst decide what a spike is "
                "before measuring spikes. A fixed threshold abandons the "
                "per-channel adaptivity that makes five channels "
                "comparable. A longer window delays first detection, "
                "which is what the detector exists for. The registered "
                "rule stands; its cost is now measured instead of "
                "inferred."),
            "worked_example": (
                "pakistan_west, Pahalgam/Sindoor: threshold 0.0244 on "
                "2025-04-21, 0.6912 on 2025-07-20 -- 28.4x, peaking "
                "after the crisis ended. On 2025-05-20 the share was "
                "0.1340, five and a half times the pre-crisis bar, and "
                "the detector stayed silent."),
            "the_effect_scales_with_episode_size": (
                "Most detected episodes are small and barely move the "
                "bar; the median multiple is close to 1. The damage is "
                "in the tail, and it is the tail that matters: the "
                "largest episodes raise their channel's threshold by "
                "more than an order of magnitude, so the detector is "
                "least able to see a second event precisely when the "
                "first one was most serious. Read "
                "largest_episodes_by_peak_share, not the median."),
            "n_episodes_analysed": len(rows),
            "n_episodes_excluded": len(exclusions),
            "excluded_episodes": exclusions,
            "n_episodes_whose_bar_peaked_after_they_ended": late_peak,
            "max_threshold_multiple": max(multiples) if multiples else None,
            "median_threshold_multiple": (
                round(float(pd.Series(multiples).median()), 1)
                if multiples else None),
            "total_suppressed_channel_days": suppressed_total,
            "suppressed_channel_days_by_channel": suppressed_unique,
            "suppressed_days_are_deduplicated": (
                "Episode follow-windows overlap, so this is the count of "
                "DISTINCT channel-days, not the sum of per-episode "
                "counts, which would multiply-count the same day."),
            "median_days_until_bar_within_2x": (
                int(pd.Series(recoveries).median()) if recoveries else None),
            "follow_days": FOLLOW_DAYS,
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "largest_episodes_by_peak_share": big,
        "episodes": rows,
    }
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / "detector_blindness.json").write_text(
        json.dumps(payload, indent=1), encoding="utf-8")

    m: dict[str, Any] = payload["_meta"]
    print(f"[blind-spot] {m['n_episodes_analysed']} episodes; bar peaks "
          f"AFTER the episode in {m['n_episodes_whose_bar_peaked_after_they_ended']} "
          f"of them")
    print(f"[blind-spot] threshold rises up to {m['max_threshold_multiple']}x "
          f"(median {m['median_threshold_multiple']}x); "
          f"{m['total_suppressed_channel_days']} distinct suppressed "
          "channel-days; "
          f"median {m['median_days_until_bar_within_2x']} days for the bar "
          "to come back within 2x")


if __name__ == "__main__":
    main()
