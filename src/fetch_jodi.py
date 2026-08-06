"""
S3: official energy statistics beside gulf_energy. JODI (the Joint
Organisations Data Initiative, the IEA/OPEC/eurostat-backed official
oil-data exchange) publishes per-country monthly series as open
annual CSVs -- verified live from their own download page, no key.

India's monthly crude-oil imports (thousand barrels/day) publish as
context beside the gulf_energy channel: when the channel runs hot,
the reader can see what physical imports were doing. Context only;
enters no score. Cite-don't-redistribute: a trailing window of one
country's one series, with attribution, not the database.

  python -m src.fetch_jodi     writes docs/data/energy_context.json
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"
BASE = ("https://www.jodidata.org/_resources/files/downloads/oil-data/"
        "annual-csv/primary/")
ATTRIBUTION = ("JODI-Oil World Database (Joint Organisations Data "
               "Initiative), jodidata.org; free use with citation. Values "
               "are as-reported by national administrations.")
KEEP_MONTHS = 48


def fetch_india_crude_imports() -> dict[str, float]:
    year = datetime.now(timezone.utc).year
    out: dict[str, float] = {}
    for y in range(year - 4, year + 1):
        name = f"primaryyear{y}.csv" if y == year else f"{y}.csv"
        r = requests.get(BASE + name, timeout=60,
                         headers={"User-Agent": "IGRM research (igrm.in)"})
        if r.status_code != 200:
            print(f"[jodi] {name}: HTTP {r.status_code}; skipped")
            continue
        n = 0
        for row in csv.DictReader(io.StringIO(r.text)):
            if (row.get("REF_AREA") == "IN"
                    and row.get("ENERGY_PRODUCT") == "CRUDEOIL"
                    and row.get("FLOW_BREAKDOWN") == "TOTIMPSB"
                    and row.get("UNIT_MEASURE") == "KBD"):
                val = (row.get("OBS_VALUE") or "").strip()
                if val and val != "-":
                    out[row["TIME_PERIOD"]] = float(val)
                    n += 1
        print(f"[jodi] {name}: {n} India crude-import months")
    return out


def main() -> None:
    series = fetch_india_crude_imports()
    if not series:
        raise SystemExit("[jodi] no data parsed; refusing to publish empty")
    months = sorted(series)[-KEEP_MONTHS:]
    payload = {
        "_meta": {
            "what": ("India's monthly crude-oil imports (thousand barrels "
                     "per day, as reported to JODI) -- official energy "
                     "statistics as context beside the gulf_energy "
                     "channel. Context only; enters no score. Reporting "
                     "lags one-to-three months and recent values revise; "
                     "the latest month shown is the latest reported, not "
                     "the latest that occurred."),
            "attribution": ATTRIBUTION,
            "unit": "thousand barrels per day",
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "months": months,
        "crude_imports_kbd": [series[m] for m in months],
        "latest": {"month": months[-1], "value": series[months[-1]]},
    }
    (SITE_DATA / "energy_context.json").write_text(json.dumps(payload),
                                                   encoding="utf-8")
    print(f"[jodi] wrote energy_context.json: {len(months)} months, "
          f"latest {months[-1]} = {series[months[-1]]} kb/d")


if __name__ == "__main__":
    main()
