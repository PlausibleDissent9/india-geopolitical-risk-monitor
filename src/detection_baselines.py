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


def main() -> None:
    check = "--check" in sys.argv
    b = compute()

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
    }
    if not check:
        SITE_DATA.mkdir(parents=True, exist_ok=True)
        (SITE_DATA / "detection_baselines.json").write_text(
            json.dumps(payload, indent=1), encoding="utf-8")
    print(f"[baselines] events={b['n_events']} registered={b['registered_criterion_hits']} "
          f"strict-start={b['strict_start_hits']} naive-any-channel={b['naive_any_channel_hits']} "
          f"chance={b['chance_expected_hits']}")


if __name__ == "__main__":
    main()
