"""
igrm: client for the India Geopolitical Risk Monitor open datasets.

Every function returns a pandas DataFrame fetched from the published
site payloads. The instrument measures press salience (attention),
never risk; associations, never causation. Full methodology:
https://plausibledissent9.github.io/india-geopolitical-risk-monitor/methodology.html

    import igrm
    df = igrm.history()          # daily channel + composite percentiles
    ev = igrm.events()           # daily India event counts (GDELT Events)
    sg = igrm.stress_gauge()     # the fused gauge and its components
    cp = igrm.chokepoints()      # weekly corridor salience vs transits
    cm = igrm.comparators()      # four-country comparator percentiles
"""
from __future__ import annotations

import io

import pandas as pd
import requests

__version__ = "0.1.0"

BASE = "https://plausibledissent9.github.io/india-geopolitical-risk-monitor/"
CITATION = ("Krishna, Ishan (2026). India Geopolitical Risk Monitor. "
            + BASE)
_HEADERS = {"User-Agent": f"igrm-python/{__version__}"}


def _get_json(name: str) -> dict:
    r = requests.get(BASE + "data/" + name, headers=_HEADERS, timeout=60)
    r.raise_for_status()
    return r.json()


def _get_csv(name: str) -> pd.DataFrame:
    r = requests.get(BASE + "data/" + name, headers=_HEADERS, timeout=60)
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text), parse_dates=["date"])


def history() -> pd.DataFrame:
    """Daily per-channel and composite percentile scores since 2017."""
    return _get_csv("history.csv").set_index("date")


RAW = ("https://raw.githubusercontent.com/PlausibleDissent9/"
       "india-geopolitical-risk-monitor/main/data/raw/")


def events() -> pd.DataFrame:
    """Daily India event counts from the GDELT Events stream: totals,
    verbal/material conflict, protest, Goldstein mean, with the global
    row count as denominator. 20 upstream-unpublished days are absent
    by construction and listed in the codebook."""
    r = requests.get(RAW + "events_daily.csv", headers=_HEADERS, timeout=120)
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text), parse_dates=["date"]).set_index("date")


def stress_gauge() -> pd.DataFrame:
    """365-day gauge history plus today's components; see methodology
    section 9 for the pre-registered weights and the published
    hit-rate, reported as found."""
    j = _get_json("stress_gauge.json")
    h = j["history_365d"]
    df = pd.DataFrame({"date": pd.to_datetime(h["dates"]), "gauge": h["gauge"]})
    return df.set_index("date")


def chokepoints() -> dict[str, pd.DataFrame]:
    """Weekly per-corridor press salience and transit percentiles."""
    j = _get_json("chokepoints.json")
    out = {}
    for k, c in j["chokepoints"].items():
        out[k] = pd.DataFrame({
            "week": pd.to_datetime(c["weeks"]),
            "salience_pct": c["salience_pct"],
            "transits_pct": c["transits_pct"],
        }).set_index("week")
    return out


def comparators() -> dict[str, pd.DataFrame]:
    """Weekly comparator-country percentiles from the shared-vocabulary
    instrument (comparators.json registration)."""
    j = _get_json("comparators.json")
    out = {}
    for k, c in j["countries"].items():
        out[k] = pd.DataFrame({
            "week": pd.to_datetime(c["weeks"]), "pct": c["pct"],
        }).set_index("week")
    return out
