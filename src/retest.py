"""
V22 groundwork: test-retest reliability, the honest ceiling for a
single-coder instrument.

The standing limitation, stated everywhere on the site, is that every
construct judgment traces to one person. Multiple independent coders
with published inter-coder kappa is the classical fix and it needs
people this project does not have. What a single coder CAN publish,
and what psychometrics has always accepted from one rater, is
TEST-RETEST: the same rater labels the same items again, blind, after
enough time that recall is not doing the work, and the agreement
between the two passes publishes as a measured property of the
instrument's judgment.

This is not a substitute for inter-coder reliability and never
claims to be. It measures consistency, not correctness -- a perfectly
consistent coder can be consistently wrong, and that sentence ships
with the number.

Design, registered here before any retest sample is drawn:
  - Eligible items: rows in audit_queue.csv that carry a founder
    label at least RETEST_MIN_AGE_DAYS old (recall decay).
  - Sample: RETEST_N items drawn with a seed derived from the draw
    date, so the draw is reproducible and cannot be re-rolled for a
    friendlier set.
  - Blindness: the retest file carries date, channel, title, domain,
    url -- and NEVER the original label.
  - Scoring: raw agreement plus Cohen's kappa on the firm (ON/OFF)
    overlap; abstentions on either pass are reported, never counted
    as agreement.

  python -m src.retest --draw       write the blind retest sheet
  python -m src.retest --score      score a filled sheet, publish
"""
from __future__ import annotations

import csv
import json
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "data" / "raw" / "audit_queue.csv"
SHEET = ROOT / "data" / "raw" / "retest_sheet.csv"
SITE_DATA = ROOT / "docs" / "data"

RETEST_N = 40
RETEST_MIN_AGE_DAYS = 30
FIRM = ("ON", "OFF")


def _rows() -> list[dict[str, str]]:
    if not QUEUE.exists():
        return []
    with QUEUE.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def eligible(rows: list[dict[str, str]], today: date) -> list[dict[str, str]]:
    cutoff = (today - timedelta(days=RETEST_MIN_AGE_DAYS)).isoformat()
    out = []
    for r in rows:
        lab = (r.get("human_label") or "").strip().upper()
        if lab not in FIRM:
            continue
        if (r.get("date") or "") > cutoff:
            continue  # too recent: recall, not judgment
        out.append(r)
    return out


def draw(today: date | None = None) -> list[dict[str, str]]:
    """Reproducible blind sample. The seed is the draw date, so the
    same day always yields the same sheet and a re-roll is visible."""
    today = today or datetime.now(timezone.utc).date()
    pool = eligible(_rows(), today)
    rng = random.Random(f"igrm-retest-{today.isoformat()}")
    picked = rng.sample(pool, min(RETEST_N, len(pool)))
    return picked


def write_sheet(picked: list[dict[str, str]]) -> None:
    fields = ["date", "channel", "title", "domain", "url", "retest_label"]
    with SHEET.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in picked:
            w.writerow({k: r.get(k, "") for k in fields[:-1]}
                       | {"retest_label": ""})


def cohens_kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Kappa on firm ON/OFF pairs. None when a pass is constant --
    kappa is undefined there and a fabricated 0 or 1 would mislead."""
    n = len(pairs)
    if n == 0:
        return None
    agree = sum(1 for a, b in pairs if a == b) / n
    p_a_on = sum(1 for a, _ in pairs if a == "ON") / n
    p_b_on = sum(1 for _, b in pairs if b == "ON") / n
    expected = p_a_on * p_b_on + (1 - p_a_on) * (1 - p_b_on)
    if expected >= 1.0:
        return None
    return (agree - expected) / (1 - expected)


def score() -> dict[str, Any]:
    if not SHEET.exists():
        raise SystemExit("[retest] no sheet; run --draw first")
    with SHEET.open(encoding="utf-8") as f:
        sheet = {r["url"]: (r.get("retest_label") or "").strip().upper()
                 for r in csv.DictReader(f)}
    original = {r["url"]: (r.get("human_label") or "").strip().upper()
                for r in _rows()}
    pairs = [(original[u], lab) for u, lab in sheet.items()
             if u in original and lab in FIRM and original[u] in FIRM]
    abstained = sum(1 for lab in sheet.values() if lab == "ABSTAIN")
    unfilled = sum(1 for lab in sheet.values() if not lab)
    k = cohens_kappa(pairs)
    agree = (sum(1 for a, b in pairs if a == b) / len(pairs)) if pairs else None
    return {
        "n_sheet": len(sheet), "n_scored": len(pairs),
        "n_abstained_on_retest": abstained, "n_unfilled": unfilled,
        "raw_agreement": round(agree, 3) if agree is not None else None,
        "cohens_kappa": round(k, 3) if k is not None else None,
    }


def publish(result: dict[str, Any]) -> None:
    payload = {
        "_meta": {
            "what": ("Test-retest reliability of the founder's own "
                     "labelling: the same registered rubric applied a "
                     "second time, blind, to items labelled at least "
                     f"{RETEST_MIN_AGE_DAYS} days earlier. Raw agreement "
                     "and Cohen's kappa on firm ON/OFF pairs; "
                     "abstentions reported, never counted as agreement."),
            "honest_limit": ("This measures CONSISTENCY, not "
                             "correctness: a perfectly consistent coder "
                             "can be consistently wrong. It is not "
                             "inter-coder reliability and does not "
                             "substitute for it -- that requires a "
                             "second human judge, which this project "
                             "does not yet have, and the ceiling is "
                             "stated in the limitations rather than "
                             "papered over."),
            "sample_rule": (f"{RETEST_N} items, seeded by draw date so "
                            "the draw is reproducible and a re-roll is "
                            "visible in git."),
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        **result,
    }
    (SITE_DATA / "retest.json").write_text(json.dumps(payload),
                                           encoding="utf-8")
    print(f"[retest] wrote retest.json: {result}")


def main() -> None:
    if "--draw" in sys.argv:
        picked = draw()
        if not picked:
            print("[retest] no eligible items yet: labels must be "
                  f"{RETEST_MIN_AGE_DAYS}+ days old. The clock starts "
                  "with the founder's existing labels.")
            return
        write_sheet(picked)
        print(f"[retest] drew {len(picked)} blind items -> "
              f"{SHEET.relative_to(ROOT)} (fill retest_label with "
              "ON/OFF/ABSTAIN; the original labels are NOT in the file)")
    elif "--score" in sys.argv:
        publish(score())
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
