"""
V6 actors layer: who drove each coverage episode, from the dyad store.

For every detected episode (docs/data/episodes.json), the window
[start-1, end+1] is compared against the trailing 90-day baseline of
each partner's daily event rate; the published drivers are the
partners with the largest excess event counts, with their
cooperation-conflict split inside the window. Counts of press-recorded
events, association language throughout; zero new fetches, the V2 dyad
store already holds every row.

Output: docs/data/episode_actors.json keyed "channel|start".

  python -m src.episode_actors
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DYADS = ROOT / "data" / "raw" / "events_dyads.csv"
EPISODES = ROOT / "docs" / "data" / "episodes.json"
OUT = ROOT / "docs" / "data" / "episode_actors.json"

BASELINE_DAYS = 90
PAD_DAYS = 1
TOP_N = 8
MIN_WINDOW_EVENTS = 5

# Channel-relevant actor codes, fixed from the channels' own anchors and
# geography (the same structural logic as the dictionaries; registered
# here, changes via changelog). An episode's card shows these partners'
# activity FIRST, then other unusually active dyads as context: a
# Pakistan-channel spike is attributed to PAK/AFG activity, never to an
# unrelated dyad that happened to be busy the same week.
CHANNEL_PARTNERS = {
    "pakistan_west": ["PAK", "AFG"],
    "china_east": ["CHN", "BTN", "NPL"],
    "gulf_energy": ["IRN", "SAU", "ARE", "QAT", "KWT", "OMN", "BHR", "IRQ", "ISR"],
    "us_trade": ["USA"],
    "shipping": ["IRN", "YEM", "EGY", "SAU", "DJI", "SGP", "MYS", "IDN"],
}


def main() -> None:
    dy = pd.read_csv(DYADS, parse_dates=["date"])
    dy = dy[dy["partner"] != ""]
    eps = json.loads(EPISODES.read_text(encoding="utf-8"))
    eps = eps["episodes"] if isinstance(eps, dict) and "episodes" in eps else eps

    out: dict = {"_meta": {
        "what": ("Per-episode driver decomposition from the GDELT Events "
                 "dyad layer: partners whose India-pair event counts in the "
                 "episode window most exceed their trailing 90-day baseline "
                 "rate, with the window's cooperation-conflict split. Counts "
                 "of press-recorded events; association, not causation."),
        "generated": date.today().isoformat(),
        "baseline_days": BASELINE_DAYS, "window_pad_days": PAD_DAYS,
    }, "episodes": {}}

    for ep in eps:
        start = pd.Timestamp(ep["start"]) - pd.Timedelta(days=PAD_DAYS)
        end = pd.Timestamp(ep["end"]) + pd.Timedelta(days=PAD_DAYS)
        wdays = (end - start).days + 1
        win = dy[(dy["date"] >= start) & (dy["date"] <= end)]
        base = dy[(dy["date"] >= start - pd.Timedelta(days=BASELINE_DAYS))
                  & (dy["date"] < start)]
        if win.empty or base.empty:
            continue
        wsum = win.groupby("partner").agg(
            n=("n", "sum"), coop=("n_coop", "sum"), conf=("n_conflict", "sum"))
        brate = base.groupby("partner")["n"].sum() / BASELINE_DAYS
        expected = (brate * wdays).reindex(wsum.index).fillna(0.0)
        wsum["excess"] = wsum["n"] - expected
        wsum = wsum[wsum["n"] >= MIN_WINDOW_EVENTS]
        relevant = CHANNEL_PARTNERS.get(ep["channel"], [])
        own = wsum[wsum.index.isin(relevant)].sort_values("excess", ascending=False)
        rest = (wsum[~wsum.index.isin(relevant)]
                .sort_values("excess", ascending=False).head(TOP_N))

        def rows(df: pd.DataFrame) -> list[dict]:
            return [
                {"partner": p, "n": int(r["n"]), "excess": round(float(r["excess"]), 1),
                 "coop": int(r["coop"]), "conflict": int(r["conf"])}
                for p, r in df.iterrows()]

        key = f"{ep['channel']}|{ep['start']}"
        out["episodes"][key] = {
            "channel": ep["channel"], "start": ep["start"], "end": ep["end"],
            "channel_partners": rows(own),
            "other_active_dyads": rows(rest),
        }

    OUT.write_text(json.dumps(out), encoding="utf-8")
    print(f"[episode_actors] wrote {len(out['episodes'])} episode decompositions")


if __name__ == "__main__":
    main()
