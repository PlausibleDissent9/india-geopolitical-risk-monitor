"""
S5: Media Cloud cross-validation (design registered ex-ante in
analysis/s5_media_cloud_design.md, 2026-08-06 -- before any account or
key existed, so the registration's priority is verifiable from git).

Replicates each channel's salience series on Media Cloud's independent
news archive using the registered dictionaries VERBATIM, transforms
through the identical percentile pipeline, and publishes weekly-mean
correlations against the IGRM series under the frozen interpretation
thresholds (>=0.6 replicates; 0.4-0.6 partial with caveat; <0.4 the
divergence itself publishes as the finding -- no post-hoc query
editing to chase agreement).

Fail-closed: without MEDIACLOUD_API_KEY this module prints a skip line
and writes nothing. First live run happens in CI once the founder adds
the key (NOTES 0.23); any client-API drift surfaces loudly there.

  python -m src.media_cloud     writes docs/data/media_cloud.json
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src import build_index

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"

WINDOW_START = date(2023, 1, 1)
THRESHOLDS = {"replicates": 0.6, "partial": 0.4}


def channel_queries() -> dict[str, str]:
    """Registered dictionaries verbatim, in Media Cloud boolean syntax:
    phrases OR'd, the india anchor AND-ed where registered."""
    dicts = json.loads((ROOT / "dictionaries.json").read_text(encoding="utf-8"))
    out = {}
    for ch, spec in dicts.items():
        if ch.startswith("_"):
            continue
        ored = " OR ".join(t if t.startswith('"') else f'"{t}"'
                           for t in spec["terms"])
        q = f"({ored})"
        if spec.get("anchor") == "india":
            q = f"{q} AND india"
        out[ch] = q
    return out


def fetch_series(api_key: str) -> pd.DataFrame:
    """Daily matching-share per channel from the Search API's
    count-over-time endpoint. ~12 requests total."""
    from mediacloud.api import SearchApi  # imported only with a key

    search = SearchApi(api_key)
    end = date.today()
    frames: dict[str, pd.Series] = {}
    totals: pd.Series | None = None
    for ch, q in channel_queries().items():
        rows = search.story_count_over_time(q, WINDOW_START, end)
        s = pd.Series({pd.Timestamp(r["date"]): r["count"] for r in rows})
        if totals is None:
            trows = search.story_count_over_time("*", WINDOW_START, end)
            totals = pd.Series({pd.Timestamp(r["date"]): r["count"]
                                for r in trows})
        frames[ch] = (s / totals.reindex(s.index)) * 100.0
        print(f"[media-cloud] {ch}: {int(s.sum()):,} matching stories")
    return pd.DataFrame(frames).sort_index()


def compare(mc_shares: pd.DataFrame) -> dict[str, Any]:
    v = pd.read_csv(ROOT / "data" / "raw" / "gdelt_volume.csv",
                    parse_dates=["date"]).set_index("date").sort_index()
    ours = build_index.build_scores(v)
    theirs = build_index.build_scores(mc_shares)
    out: dict[str, Any] = {}
    for ch in mc_shares.columns:
        a = ours[ch].resample("W-MON").mean()
        b = theirs[ch].resample("W-MON").mean()
        joint = pd.concat([a, b], axis=1, keys=["igrm", "mc"]).dropna()
        if len(joint) < 26:
            out[ch] = {"weeks": len(joint),
                       "note": "under 26 shared weeks; not scored"}
            continue
        r = float(joint["igrm"].corr(joint["mc"]))
        verdict = ("replicates" if r >= THRESHOLDS["replicates"]
                   else "partial" if r >= THRESHOLDS["partial"]
                   else "diverges")
        out[ch] = {"weeks": len(joint), "r_weekly_pctl": round(r, 3),
                   "verdict": verdict}
    return out


def main() -> None:
    key = os.environ.get("MEDIACLOUD_API_KEY")
    if not key:
        print("[media-cloud] no MEDIACLOUD_API_KEY; skipping (fail-closed; "
              "the registered design waits for the founder's key, "
              "NOTES 0.23)")
        return
    shares = fetch_series(key)
    results = compare(shares)
    payload = {
        "_meta": {
            "what": ("S5 cross-validation: each channel's registered "
                     "dictionary run VERBATIM on Media Cloud's "
                     "independent news archive, identical percentile "
                     "transform, weekly-mean correlation against the "
                     "IGRM series. Interpretation thresholds were "
                     "frozen before any data existed "
                     "(analysis/s5_media_cloud_design.md): r>=0.6 "
                     "replicates, 0.4-0.6 partial, <0.4 publishes as "
                     "the divergence finding. No query is ever tuned "
                     "to this corpus."),
            "window_start": WINDOW_START.isoformat(),
            "thresholds": THRESHOLDS,
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "channels": results,
    }
    (SITE_DATA / "media_cloud.json").write_text(json.dumps(payload),
                                                encoding="utf-8")
    print(f"[media-cloud] wrote media_cloud.json: "
          f"{ {ch: r.get('verdict') for ch, r in results.items()} }")


if __name__ == "__main__":
    main()
