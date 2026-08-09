"""
Per-chokepoint press salience and the salience-vs-transits comparison.

The four sub-dictionaries live in dictionaries.json v1.1.0 under
shipping.chokepoints and exist only for this comparison; they never
enter the composite. Transit counts come from IMF PortWatch
(data/raw/portwatch_chokepoints.csv, maintained by fetch_portwatch).

Store: data/raw/chokepoint_salience.csv   date x chokepoint, GDELT share
Site:  docs/data/chokepoints.json         weekly percentiles + stats

  python -m src.chokepoints --update     14-day tail merge, then publish
  python -m src.chokepoints --backfill   full 2019-present fetch
  python -m src.chokepoints --publish    recompute site JSON only

Start floor is 2019-01-01, the PortWatch coverage floor: fetching the
2017-2018 salience tail would spend GDELT requests on a range the
comparison can never use.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from . import fetch_gdelt
from .publication_guard import (
    PublicationGuardError,
    _validate_rights_registry,
    _validate_signers,
)

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "raw" / "chokepoint_salience.csv"
PORTWATCH = ROOT / "data" / "raw" / "portwatch_chokepoints.csv"
SITE_JSON = ROOT / "docs" / "data" / "chokepoints.json"
RIGHTS_REGISTRY = ROOT / "governance" / "source_rights_registry.json"
RIGHTS_SIGNERS = ROOT / "governance" / "rights_signers.json"

START = date(2019, 1, 1)
EXPECTED_CHOKEPOINTS = ("hormuz", "bab_el_mandeb", "suez", "malacca")
TRANSFORM_VERSION = "weekly-percentile-v1.2.0"
WEEK_RULE = (
    "Monday-labelled W-MON weekly means; absent joint weeks are omitted, "
    "never interpolated"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rights_decision(source_id: str) -> dict[str, object]:
    """Copy a cryptographically checked state without laundering review as approval."""
    registry = json.loads(RIGHTS_REGISTRY.read_text(encoding="utf-8"))
    signers = json.loads(RIGHTS_SIGNERS.read_text(encoding="utf-8"))
    try:
        checked = _validate_rights_registry(
            registry, ROOT, _validate_signers(signers)
        )
    except PublicationGuardError as exc:
        raise SystemExit(
            f"[chokepoints] invalid rights registry: {exc.code}"
        ) from exc
    row = checked.get(source_id)
    if row is None:
        raise SystemExit(f"[chokepoints] missing unique rights row: {source_id}")
    state = row.get("decision_state")
    if state not in {"review_required", "approved"}:
        raise SystemExit(
            f"[chokepoints] source rights state blocks publication: "
            f"{source_id}={state}"
        )
    return {
        "source_id": source_id,
        "provider": row.get("provider"),
        "decision_state": state,
        "decision_id": row.get("decision_id"),
        "signer_id": row.get("signer_id"),
        "decision_artifact_sha256": row.get("decision_artifact_sha256"),
        "reviewed_on": row.get("reviewed_on"),
        "terms_url": row.get("terms_url"),
    }


def _subdicts() -> dict:
    with open(ROOT / "dictionaries.json", encoding="utf-8") as f:
        return json.load(f)["shipping"]["chokepoints"]


def _load_store() -> pd.DataFrame | None:
    if not STORE.exists():
        return None
    df = pd.read_csv(STORE, parse_dates=["date"])
    df["date"] = df["date"].dt.date
    return df.set_index("date").sort_index()


def update(backfill: bool = False) -> pd.DataFrame:
    subs = _subdicts()
    existing = _load_store()
    today = date.today()
    start = START if (backfill or existing is None) else today - timedelta(days=14)
    cols = {}
    for name, spec in subs.items():
        print(f"[chokepoints] {name}: {start} -> {today}")
        cols[name] = fetch_gdelt.fetch_channel(spec["terms"], start, today)
    fetched = pd.DataFrame(cols)
    if existing is not None and not backfill:
        merged = fetched.combine_first(existing)
    else:
        merged = fetched
    merged = merged.sort_index()
    STORE.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(STORE, index_label="date")
    return merged


def _pct(s: pd.Series) -> pd.Series:
    return (s.rank(pct=True) * 100).round(1)


def publish() -> None:
    sal = _load_store()
    if sal is None:
        raise SystemExit("[chokepoints] no salience store; run --backfill first")
    pw = pd.read_csv(PORTWATCH, parse_dates=["date"])
    tra = pw.pivot(index="date", columns="chokepoint", values="n_total")
    sal.index = pd.to_datetime(sal.index)

    # Weekly means: daily transit counts are noisy (weekday convoy
    # patterns in Suez especially) and the comparison is about regimes,
    # not days. Percentiles are of each series' own full 2019-present
    # weekly history, disclosed on the page.
    sal_w = sal.resample("W-MON").mean()
    tra_w = tra.resample("W-MON").mean()
    # Drop the trailing partial week of transits: PortWatch lags a few
    # days and a 1-2 day "week" reads as a fake collapse.
    tra_w = tra_w[tra_w.index <= pw["date"].max() - pd.Timedelta(days=2)]

    subs = _subdicts()
    out: dict = {"_meta": {}, "chokepoints": {}}
    for name, spec in subs.items():
        if name not in sal_w.columns or name not in tra_w.columns:
            continue
        joint = pd.DataFrame({
            "sal": sal_w[name], "tra": tra_w[name],
        }).dropna()
        if len(joint) < 26:
            continue
        sal_p = _pct(joint["sal"])
        tra_p = _pct(joint["tra"])
        # Spearman as Pearson on ranks: identical by definition and it
        # keeps scipy out of the dependency set.
        rho = joint["sal"].rank().corr(joint["tra"].rank())
        out["chokepoints"][name] = {
            "label": spec["label"],
            "weeks": [d.date().isoformat() for d in joint.index],
            "salience_pct": sal_p.tolist(),
            "transits_pct": tra_p.tolist(),
            "spearman_weekly": round(float(rho), 2),
            "latest_gap": round(float(sal_p.iloc[-1] - tra_p.iloc[-1]), 1),
            "n_weeks": int(len(joint)),
            "n_joint_weeks": int(len(joint)),
            "missing_joint_weeks": int(
                ((joint.index[-1] - joint.index[0]).days // 7 + 1) - len(joint)
            ),
        }
    if set(out["chokepoints"]) != set(EXPECTED_CHOKEPOINTS):
        raise SystemExit(
            "[chokepoints] refusing partial publication: expected all four waterways"
        )
    cutoffs = {row["weeks"][-1] for row in out["chokepoints"].values()}
    if len(cutoffs) != 1:
        raise SystemExit(
            "[chokepoints] refusing mixed-cutoff publication: waterways do not align"
        )
    cutoff = cutoffs.pop()
    out["_meta"] = {
        "what": ("Weekly press salience per chokepoint sub-dictionary against "
                 "IMF PortWatch transit calls, each as a percentile of its own "
                 "2019-present weekly history. This is a descriptive comparison, "
                 "not a disruption, causal, probability, or exposure estimate."),
        "manifest_version": "1.0.0",
        "partial": False,
        "generated": date.today().isoformat(),
        "knowledge_cutoff": cutoff,
        "week_rule": WEEK_RULE,
        "transform_version": TRANSFORM_VERSION,
        "transform": {
            "implementation": "src/chokepoints.py",
            "implementation_sha256": _sha256(Path(__file__)),
            "dictionary": "dictionaries.json shipping.chokepoints",
            "dictionary_sha256": _sha256(ROOT / "dictionaries.json"),
        },
        "salience_source": ("GDELT DOC API timelinevol, dictionaries.json "
                            "shipping.chokepoints"),
        "transits_source": ("IMF PortWatch (portwatch.imf.org), n_total daily "
                            "transit calls, weekly mean"),
        "source_vintages": {
            "salience": {
                "input": "data/raw/chokepoint_salience.csv",
                "input_sha256": _sha256(STORE),
                "max_observed_date": sal.index.max().date().isoformat(),
                "rights": _rights_decision("gdelt_doc_api"),
            },
            "transits": {
                "input": "data/raw/portwatch_chokepoints.csv",
                "input_sha256": _sha256(PORTWATCH),
                "max_observed_date": pw["date"].max().date().isoformat(),
                "rights": _rights_decision("imf_portwatch"),
            },
        },
        "rights_registry_sha256": _sha256(RIGHTS_REGISTRY),
        "license": ("CC BY 4.0 for IGRM-authored derived percentiles and "
                    "metadata; upstream provider terms govern source data"),
    }
    SITE_JSON.parent.mkdir(parents=True, exist_ok=True)
    SITE_JSON.write_text(json.dumps(out), encoding="utf-8")
    kept = {k: (v["spearman_weekly"], v["latest_gap"])
            for k, v in out["chokepoints"].items()}
    print(f"[chokepoints] wrote {SITE_JSON.name}: "
          f"{ {k: f'rho={a} gap={b}' for k, (a, b) in kept.items()} }")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args()
    if args.update or args.backfill:
        update(backfill=args.backfill)
        publish()
    elif args.publish:
        publish()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
