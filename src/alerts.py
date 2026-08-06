"""
Alerts, Phase 0 (design/alerts_webhook.md, founder-signed 2026-08-06
"sign alerts"). Computes the three registered triggers from
already-published payloads AFTER the daily publish -- an alert can
never disagree with the site -- and appends to docs/data/alerts.json
(newest first, 90-day retention, stable ids, poll model; no push
delivery in this phase and no email tier at all).

Registered triggers (amendments are dated, append-only, in the signed
design doc):

  T1  band_separated_move: a channel's Wilson 95% band for the new day
      does not overlap the previous day's band.
  T2  composite_percentile_crossing: the composite crosses its
      trailing 90th percentile (730-day window, the instrument's own
      convention) in either direction, and both of today's band edges
      sit on the crossing's side of the threshold.
  T3  integrity_event: the latest scored morning missed its contract
      deadline (from reliability.json -- the instrument's failures
      alert the same channel its successes do). An audit failure
      blocks publication entirely, so it surfaces as the missed
      morning it causes; a dead pipeline cannot emit its own alert,
      and pretending otherwise would be theater.

Alert copy carries numbers and band arithmetic only -- `direction` is
the direction of the COMPLETED move. Nothing here forecasts.

  python -m src.alerts        writes docs/data/alerts.json
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"

RETENTION_DAYS = 90
PCTL_THRESHOLD = 0.90
PCTL_WINDOW_DAYS = 730


def _overlap(a: list[float], b: list[float]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def t1_band_separated(latest: dict, unc_days: dict,
                      history: dict) -> list[dict[str, Any]]:
    day = latest["date"]
    dates = history["dates"]
    if day not in dates:
        return []
    i = dates.index(day)
    if i == 0:
        return []
    prev_day = dates[i - 1]
    bands, prev_bands = unc_days.get(day), unc_days.get(prev_day)
    if not bands or not prev_bands:
        return []
    out = []
    for ch in (latest.get("channels") or {}):
        b, pb = bands.get(ch), prev_bands.get(ch)
        if not b or not pb or _overlap(b, pb):
            continue
        score = latest["channels"][ch]["score"]
        prev_score = history["channels"][ch][i - 1]
        out.append({
            "id": f"{day}-{ch}-T1",
            "date": day, "type": "band_separated_move", "channel": ch,
            "direction": "down" if b[1] < pb[0] else "up",
            "score": score, "band": b,
            "prev_score": prev_score, "prev_band": pb,
        })
    return out


def t2_composite_crossing(latest: dict, unc_days: dict,
                          history: dict) -> list[dict[str, Any]]:
    day = latest["date"]
    dates = history["dates"]
    comp = history["composite"]
    if day not in dates:
        return []
    i = dates.index(day)
    if i == 0 or comp[i] is None or comp[i - 1] is None:
        return []
    window_start = (date.fromisoformat(day)
                    - timedelta(days=PCTL_WINDOW_DAYS)).isoformat()
    trailing = [c for d, c in zip(dates[:i], comp[:i])
                if c is not None and d >= window_start]
    if len(trailing) < 180:
        return []
    threshold = sorted(trailing)[int(PCTL_THRESHOLD * (len(trailing) - 1))]
    today, prev = comp[i], comp[i - 1]
    crossed_up = prev <= threshold < today
    crossed_down = prev >= threshold > today
    if not (crossed_up or crossed_down):
        return []
    band = (unc_days.get(day) or {}).get("composite")
    if not band:
        return []
    survives = (band[0] > threshold) if crossed_up else (band[1] < threshold)
    if not survives:
        return []
    return [{
        "id": f"{day}-composite-T2",
        "date": day, "type": "composite_percentile_crossing",
        "channel": "composite",
        "direction": "up" if crossed_up else "down",
        "score": today, "band": band,
        "threshold_pctl90": round(threshold, 1), "prev_score": prev,
    }]


def t3_integrity(reliability: dict) -> list[dict[str, Any]]:
    days = reliability.get("days") or []
    scored = [d for d in days if d.get("contract")]
    if not scored:
        return []
    last = scored[-1]
    if last.get("on_time"):
        return []
    return [{
        "id": f"{last['day']}-contract-T3",
        "date": last["day"], "type": "integrity_event",
        "event": "morning_contract_miss",
        "published_ist": last.get("published_ist"),
        "deadline_ist": last.get("deadline_ist"),
    }]


def main() -> None:
    latest = json.loads((SITE_DATA / "latest.json").read_text(encoding="utf-8"))
    history = json.loads((SITE_DATA / "history.json").read_text(encoding="utf-8"))
    unc = json.loads((SITE_DATA / "uncertainty.json").read_text(encoding="utf-8"))
    reliability = json.loads(
        (SITE_DATA / "reliability.json").read_text(encoding="utf-8"))

    fresh = (t1_band_separated(latest, unc["days"], history)
             + t2_composite_crossing(latest, unc["days"], history)
             + t3_integrity(reliability))

    path = SITE_DATA / "alerts.json"
    existing: list[dict] = []
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8")).get("alerts", [])
    seen = {a["id"] for a in existing}
    merged = [a for a in fresh if a["id"] not in seen] + existing
    cutoff = (date.fromisoformat(latest["date"])
              - timedelta(days=RETENTION_DAYS)).isoformat()
    merged = [a for a in merged if a["date"] >= cutoff]

    payload = {
        "_meta": {
            "what": ("Registered alert events computed from published "
                     "payloads after each daily publish (design/"
                     "alerts_webhook.md, founder-signed 2026-08-06): "
                     "T1 band-separated channel moves, T2 composite "
                     "90th-percentile crossings that survive their "
                     "sampling band, T3 integrity events (the morning "
                     "contract's own misses). Poll model, newest first, "
                     "90-day retention, stable ids. Every field is a "
                     "number or the direction of a COMPLETED move; "
                     "nothing here is a forecast."),
            "triggers": {"T1": "band_separated_move",
                         "T2": "composite_percentile_crossing "
                               f"({int(PCTL_THRESHOLD*100)}th pctl, "
                               f"{PCTL_WINDOW_DAYS}d window)",
                         "T3": "integrity_event"},
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "alerts": merged,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    print(f"[alerts] {len(fresh)} fresh trigger(s), {len(merged)} retained "
          f"({[a['id'] for a in fresh] or 'none new'})")


if __name__ == "__main__":
    main()
