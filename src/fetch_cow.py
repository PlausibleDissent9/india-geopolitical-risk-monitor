"""
S12: Correlates of War MIDs beside the M1 historical proxy. The MID
5.0 dataset (militarized interstate disputes, 1816-2014) is the
political-science standard for coded interstate conflict; aggregating
India's dispute-years against Pakistan and China gives the M1 study
an independent ground-truth context series -- events coded by
historians, not newspapers, so agreement across the two is meaningful
and divergence is analyzable.

Static dataset (ends 2014): fetched once, only India-relevant
aggregates publish (counts, not the dataset -- cite, don't
redistribute). Context beside the historical proxy; enters no score.

  python -m src.fetch_cow     writes docs/data/cow_mids.json
"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"
URL = ("https://correlatesofwar.org/wp-content/uploads/"
       "MID-5-Data-and-Supporting-Materials.zip")
ATTRIBUTION = ("Palmer, Glenn, et al. (2022). The MID5 Dataset, 2011-2014. "
               "Correlates of War Project, correlatesofwar.org. Used with "
               "attribution; only India-relevant aggregates published.")
IND, PAK, CHN = "750", "770", "710"


def load_participants() -> list[dict]:
    r = requests.get(URL, timeout=120,
                     headers={"User-Agent": "IGRM research (igrm.in)"})
    r.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    name = next(n for n in zf.namelist()
                if "MIDB" in n and n.lower().endswith(".csv"))
    with zf.open(name) as f:
        return list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8",
                                                    errors="replace")))


def india_dispute_years(rows: list[dict]) -> dict[str, Counter]:
    """Per opponent, count of distinct disputes by start year, from the
    participant-level file: a dispute counts for a dyad when both sides
    appear under the same dispute number."""
    by_disp: dict[str, set[str]] = {}
    year_of: dict[str, str] = {}
    for r in rows:
        dn = r.get("dispnum") or r.get("DispNum") or r.get("dispnum3", "")
        cc = str(r.get("ccode") or r.get("ccode1") or "")
        yr = str(r.get("styear") or r.get("StYear") or "")
        if not dn or not cc:
            continue
        by_disp.setdefault(dn, set()).add(cc)
        if cc == IND and yr:
            year_of[dn] = yr
    out: dict[str, Counter[str]] = {"pakistan": Counter(), "china": Counter()}
    for dn, codes in by_disp.items():
        if IND not in codes or dn not in year_of:
            continue
        if PAK in codes:
            out["pakistan"][year_of[dn]] += 1
        if CHN in codes:
            out["china"][year_of[dn]] += 1
    return out


def main() -> None:
    rows = load_participants()
    counts = india_dispute_years(rows)
    payload = {
        "_meta": {
            "what": ("Correlates of War MID 5.0 aggregates (S12): distinct "
                     "militarized interstate disputes involving India by "
                     "start year and opponent, 1816-2014 -- historian-coded "
                     "conflict as independent context beside the M1 "
                     "historical attention proxy (research/history.html). "
                     "Static dataset, fetched once; only aggregates "
                     "publish. Context only; enters no score."),
            "attribution": ATTRIBUTION,
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "disputes_by_start_year": {
            k: dict(sorted(v.items())) for k, v in counts.items()},
        "totals": {k: sum(v.values()) for k, v in counts.items()},
    }
    (SITE_DATA / "cow_mids.json").write_text(json.dumps(payload),
                                             encoding="utf-8")
    print(f"[cow] wrote cow_mids.json: totals {payload['totals']}")


if __name__ == "__main__":
    main()
