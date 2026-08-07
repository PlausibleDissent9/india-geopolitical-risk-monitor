"""Base rates for the headline validation numbers (referee findings 3-4).

The registered hit rate says 24 of 29. The simulated referee report
(analysis/referee_report_2026-08-07.md) showed that number is not
interpretable alone:

  * a random-date generator scores ~6.8/29 under the same +/-3-day,
    any-episode-day criterion, because 524 episodes blanket a fifth to a
    quarter of all channel-days;
  * requiring the episode START within +/-3 days gives 19/29;
  * the placebo's 45.2% overlap sits against a ~35.6% chance rate --
    the real excess is ~10 points, not 45.

None of that was published beside the headline. The registered statistic
is untouched here -- this module publishes the context that makes it
honest, computed from the published files a stranger has (episodes.csv,
validation_episodes.json, history.csv), never from private state.

  python -m src.detection_baselines          write docs/data/detection_baselines.json
  python -m src.detection_baselines --check  inspect without writing
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
EPISODES = SITE_DATA / "episodes.csv"
EVENTS = ROOT / "validation" / "validation_episodes.json"
VALIDATION = SITE_DATA / "validation.json"
WINDOW = 3  # the registered +/-3-day window


def _episodes() -> list[dict[str, Any]]:
    with EPISODES.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["start_d"] = date.fromisoformat(r["start"])
        r["end_d"] = date.fromisoformat(r["end"])
    return rows


def _events() -> list[dict[str, Any]]:
    data = json.loads(EVENTS.read_text(encoding="utf-8"))
    rows = data["episodes"] if isinstance(data, dict) and "episodes" in data else data
    out = []
    for e in rows:
        day = e.get("date") or e.get("event_date")
        ch = e.get("channel")
        if day and ch:
            out.append({"name": e.get("name", "?"), "channel": ch,
                        "date": date.fromisoformat(day[:10])})
    return out


def _hit_any_day(ev: dict, eps: list[dict]) -> bool:
    """The registered (lenient) criterion: any day of any same-channel
    episode within the window."""
    for p in eps:
        if p["channel"] != ev["channel"]:
            continue
        if (p["start_d"] - timedelta(days=WINDOW) <= ev["date"]
                <= p["end_d"] + timedelta(days=WINDOW)):
            return True
    return False


def _hit_start(ev: dict, eps: list[dict]) -> bool:
    """The strict criterion: the episode START within the window."""
    return any(p["channel"] == ev["channel"]
               and abs((p["start_d"] - ev["date"]).days) <= WINDOW
               for p in eps)


def _hit_any_channel(ev: dict, eps: list[dict]) -> bool:
    """The naive detector: was there ANY episode in ANY channel nearby?
    If this scores close to the registered 24/29, the five-dictionary
    apparatus adds little over 'was it a big news week'."""
    return any(p["start_d"] - timedelta(days=WINDOW) <= ev["date"]
               <= p["end_d"] + timedelta(days=WINDOW) for p in eps)


def _chance_rate(events: list[dict], eps: list[dict]) -> float:
    """Expected hits for randomly-dated events, exactly: per channel, the
    fraction of eligible days lying within the window of any episode,
    summed over the real events' channels. Deterministic -- no simulation
    seed to argue about."""
    if not eps:
        return 0.0
    lo = min(p["start_d"] for p in eps)
    hi = max(p["end_d"] for p in eps)
    all_days = [lo + timedelta(days=i) for i in range((hi - lo).days + 1)]
    frac: dict[str, float] = {}
    for ch in {e["channel"] for e in events}:
        chan_eps = [p for p in eps if p["channel"] == ch]
        covered = sum(
            1 for d in all_days
            if any(p["start_d"] - timedelta(days=WINDOW) <= d
                   <= p["end_d"] + timedelta(days=WINDOW) for p in chan_eps))
        frac[ch] = covered / len(all_days)
    return sum(frac[e["channel"]] for e in events)


def compute() -> dict[str, Any]:
    eps = _episodes()
    events = _events()
    n = len(events)
    lenient = sum(_hit_any_day(e, eps) for e in events)
    strict = sum(_hit_start(e, eps) for e in events)
    naive = sum(_hit_any_channel(e, eps) for e in events)
    chance = _chance_rate(events, eps)

    misses_strict = [e["name"] for e in events
                     if _hit_any_day(e, eps) and not _hit_start(e, eps)]

    return {
        "n_events": n,
        "registered_criterion_hits": lenient,
        "strict_start_hits": strict,
        "criterion_sensitive_events": misses_strict,
        "naive_any_channel_hits": naive,
        "chance_expected_hits": round(chance, 1),
        "n_episodes": len(eps),
    }


def compute_placebo() -> dict[str, Any]:
    """Exact random-placement baseline for the observed placebo episodes.

    Preserve every placebo episode's inclusive duration, place that interval at
    every possible start date inside the placebo study window, and measure the
    fraction of placements overlapping any published geopolitical episode day.
    The reported chance rate is the mean of those episode-specific fractions.
    """
    validation = json.loads(VALIDATION.read_text(encoding="utf-8"))
    block = validation["placebo"]
    placebo_episodes = block["episodes"]
    if not placebo_episodes:
        raise RuntimeError("placebo baseline requires at least one episode")

    geopolitical = _episodes()
    geopolitical_days = {
        day
        for episode in geopolitical
        for day in (
            episode["start_d"] + timedelta(days=i)
            for i in range((episode["end_d"] - episode["start_d"]).days + 1)
        )
    }
    study_start = min(date.fromisoformat(row["start"]) for row in placebo_episodes)
    study_end = max(date.fromisoformat(row["end"]) for row in placebo_episodes)
    study_days = (study_end - study_start).days + 1

    chance_by_episode: list[float] = []
    for row in placebo_episodes:
        duration = (
            date.fromisoformat(row["end"]) - date.fromisoformat(row["start"])
        ).days + 1
        n_starts = study_days - duration + 1
        if n_starts <= 0:
            raise RuntimeError("placebo episode exceeds its study window")
        overlaps = 0
        for offset in range(n_starts):
            start = study_start + timedelta(days=offset)
            if any(
                start + timedelta(days=i) in geopolitical_days
                for i in range(duration)
            ):
                overlaps += 1
        chance_by_episode.append(overlaps / n_starts)

    n_placebo = int(block["n_placebo_episodes"])
    n_overlapping = int(block["n_overlapping"])
    if n_placebo != len(placebo_episodes):
        raise RuntimeError("placebo episode count disagrees with its episode rows")
    observed = n_overlapping / n_placebo
    chance = sum(chance_by_episode) / len(chance_by_episode)
    geopolitical_day_share = sum(
        study_start + timedelta(days=i) in geopolitical_days
        for i in range(study_days)
    ) / study_days
    return {
        "study_start": study_start.isoformat(),
        "study_end": study_end.isoformat(),
        "n_study_days": study_days,
        "n_placebo_episodes": n_placebo,
        "observed_overlaps": n_overlapping,
        "observed_overlap_fraction": round(observed, 4),
        "geopolitical_episode_day_fraction": round(geopolitical_day_share, 4),
        "random_placement_expected_overlaps": round(n_placebo * chance, 1),
        "random_placement_overlap_fraction": round(chance, 4),
        "excess_over_random_fraction": round(observed - chance, 4),
        "method": (
            "For each observed placebo episode, preserve its inclusive duration; "
            "enumerate every possible interval start inside the placebo study "
            "window; measure overlap with any published geopolitical episode "
            "day; average the resulting episode-specific probabilities."
        ),
        "registered_null": False,
    }


def composite7_battery() -> dict[str, Any]:
    """Referee finding 16: the 7-day headline's detection quality rests
    on two hand-picked anecdotes (Pahalgam at 99.5 is the famous one).
    This runs the full 29-event battery on composite7 itself.

    The detection rule is the REGISTERED one, not an invention for this
    module: T2's convention from the signed alerts design (composite
    above its trailing 90th percentile, 730-day window, minimum trailing
    observations as named in src.alerts). Applied descriptively over the
    whole published history; the band-survival clause is omitted because
    published sampling bands do not span the full history, and that
    omission is stated in the payload rather than hidden.

    The composite has no channel dimension, so this is inherently the
    any-channel reading -- the honest comparison row is the chance rate
    beside it, computed the same deterministic way as everywhere else in
    this module."""
    from src.alerts import MIN_TRAILING_OBS, PCTL_THRESHOLD, PCTL_WINDOW_DAYS

    history = json.loads((SITE_DATA / "history.json").read_text(encoding="utf-8"))
    days = [date.fromisoformat(d) for d in history["dates"]]
    comp7 = history["composite7"]

    elevated: set[date] = set()
    eligible: list[date] = []
    j = 0  # window start index; advances monotonically with i
    for i, (d, v) in enumerate(zip(days, comp7)):
        if v is None:
            continue
        window_start = d - timedelta(days=PCTL_WINDOW_DAYS)
        while days[j] < window_start:
            j += 1
        trailing = [c for c in comp7[j:i] if c is not None]
        if len(trailing) < MIN_TRAILING_OBS:
            continue
        eligible.append(d)
        threshold = sorted(trailing)[int(PCTL_THRESHOLD * (len(trailing) - 1))]
        if v > threshold:
            elevated.add(d)

    runs = 0
    prev: date | None = None
    for d in sorted(elevated):
        if prev is None or (d - prev).days > 1:
            runs += 1
        prev = d

    def _near(d: date) -> bool:
        return any(d + timedelta(days=k) in elevated
                   for k in range(-WINDOW, WINDOW + 1))

    events = _events()
    evaluable = [e for e in events
                 if eligible[0] <= e["date"] <= eligible[-1]]
    hits = [e for e in evaluable if _near(e["date"])]
    misses = [e["name"] for e in evaluable if not _near(e["date"])]
    covered = sum(_near(d) for d in eligible)
    chance = covered / len(eligible) * len(evaluable)

    return {
        "rule": (
            "the registered T2 convention applied descriptively: "
            f"composite7 above its trailing {int(PCTL_THRESHOLD*100)}th "
            f"percentile ({PCTL_WINDOW_DAYS}-day window, >= "
            f"{MIN_TRAILING_OBS} trailing observations). T2's alert-time "
            "band-survival clause is omitted because published sampling "
            "bands do not span the full history."),
        "n_days_evaluable": len(eligible),
        "first_evaluable_day": eligible[0].isoformat(),
        "n_days_elevated": len(elevated),
        "elevated_day_fraction": round(len(elevated) / len(eligible), 4),
        "n_elevated_runs": runs,
        "n_events": len(events),
        "n_events_evaluable": len(evaluable),
        "hits": len(hits),
        "chance_expected_hits": round(chance, 1),
        "events_missed": sorted(misses),
    }


def main() -> None:
    check = "--check" in sys.argv
    b = compute()
    placebo = compute_placebo()
    battery = composite7_battery()

    from src import stamp_meta
    payload = {
        "_meta": {
            **stamp_meta.universal_fields("detection_baselines.json"),
            "what": (
                "Base rates for the registered episode-detection hit rate "
                "and the placebo overlap. The registered statistics are "
                "unchanged; this publishes the denominators that make them "
                "interpretable, because a hit rate quoted without its "
                "chance rate is a number wearing a costume."),
            "prompted_by": (
                "a simulated hostile referee (analysis/referee_report_"
                "2026-08-07.md, findings 3-4), whose recomputations of the "
                "published statistics all reproduced and whose criticism "
                "was aimed at what was NOT published beside them"),
            "registered_criterion": (
                f"a detected same-channel episode day within +/-{WINDOW} "
                "days of the event (the lenient reading; the strict "
                "start-based reading is published here alongside)"),
            "how_to_read": (
                "The apparatus earns exactly the gap between the "
                "registered hits and the chance/naive rows. A registered "
                "rate far above chance but close to the naive any-channel "
                "detector means the CHANNEL ATTRIBUTION carries the value, "
                "not the detection itself."),
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "hit_rate_context": b,
        "placebo_context": placebo,
        "composite7_battery": battery,
    }
    if not check:
        SITE_DATA.mkdir(parents=True, exist_ok=True)
        (SITE_DATA / "detection_baselines.json").write_text(
            json.dumps(payload, indent=1), encoding="utf-8")
    print(f"[baselines] events={b['n_events']} registered={b['registered_criterion_hits']} "
          f"strict-start={b['strict_start_hits']} naive-any-channel={b['naive_any_channel_hits']} "
          f"chance={b['chance_expected_hits']}; placebo observed="
          f"{placebo['observed_overlap_fraction']:.1%} random="
          f"{placebo['random_placement_overlap_fraction']:.1%}; "
          f"composite7 battery={battery['hits']}/{battery['n_events_evaluable']} "
          f"chance={battery['chance_expected_hits']}")


if __name__ == "__main__":
    main()
