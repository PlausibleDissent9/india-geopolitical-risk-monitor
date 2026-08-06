"""
V17: the replication wedge. Caldara & Iacoviello's GPR is the
standard geopolitical-risk series the literature cites; GPRC_IND is
its India country index (monthly, newspaper-based, different corpus,
different construction). If IGRM measures something real, the two
should co-move at the monthly horizon DESPITE sharing no pipeline --
and where they diverge, the divergence is publishable analysis, not
embarrassment.

Discipline: GPR data is fetched at runtime and never committed or
redistributed (cite-don't-republish, the Yahoo rule); only aggregates
publish, with attribution. No IGRM series changes; this is a
comparison layer.

  python -m src.gpr_comparison   writes docs/data/gpr_comparison.json
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from src import build_index

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"
GPR_URL = "https://www.matteoiacoviello.com/gpr_files/data_gpr_export.xls"
ATTRIBUTION = ("Caldara, Dario and Matteo Iacoviello (2022), 'Measuring "
               "Geopolitical Risk', American Economic Review. Data from "
               "matteoiacoviello.com, used with attribution, not "
               "redistributed.")


def fetch_gpr() -> pd.Series:
    r = requests.get(GPR_URL, timeout=90,
                     headers={"User-Agent": "IGRM research (igrm.in)"})
    r.raise_for_status()
    df = pd.read_excel(io.BytesIO(r.content))
    s = df.set_index("month")["GPRC_IND"].dropna()
    s.index = pd.to_datetime(s.index)
    return s


def igrm_monthly() -> pd.DataFrame:
    v = pd.read_csv(ROOT / "data" / "raw" / "gdelt_volume.csv",
                    parse_dates=["date"]).set_index("date").sort_index()
    scores = build_index.build_scores(v)
    return scores.resample("MS").mean()


def compare(gpr: pd.Series, monthly: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in monthly.columns:
        joint = pd.concat([monthly[col], gpr], axis=1,
                          keys=["igrm", "gpr"]).dropna()
        joint = joint[joint.index >= "2017-01-01"]
        if len(joint) < 24:
            continue
        r_level = float(joint["igrm"].corr(joint["gpr"]))
        d = joint.diff().dropna()
        r_change = float(d["igrm"].corr(d["gpr"]))
        out[col] = {"months": int(len(joint)),
                    "r_levels": round(r_level, 3),
                    "r_monthly_changes": round(r_change, 3)}
    return out


def main() -> None:
    gpr = fetch_gpr()
    monthly = igrm_monthly()
    results = compare(gpr, monthly)
    payload = {
        "_meta": {
            "what": ("V17 replication wedge: monthly-mean IGRM percentile "
                     "scores vs Caldara-Iacoviello's GPRC_IND (a "
                     "different corpus and construction entirely), "
                     "2017-present -- correlation in levels and in "
                     "monthly changes, per channel and composite. "
                     "Co-movement despite zero shared pipeline is "
                     "external validation; divergence is analysis. "
                     "Nothing in any IGRM series depends on GPR."),
            "attribution": ATTRIBUTION,
            "gpr_through": gpr.index.max().date().isoformat(),
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "series": results,
    }
    (SITE_DATA / "gpr_comparison.json").write_text(json.dumps(payload),
                                                   encoding="utf-8")
    for k, v in results.items():
        print(f"[gpr] {k:14s} r_levels {v['r_levels']:+.3f}  "
              f"r_changes {v['r_monthly_changes']:+.3f}  n={v['months']}")


if __name__ == "__main__":
    main()
