"""
Publish the QUANTITY, not only the transform (referee finding, 2026-08-07).

The index published percentiles and kept raw shares in data/raw/ as an
input. That is backwards for a research instrument: a reader who
disagrees with the normalization could not recompute anything, and
three separate defects all trace to the same omission:

  * Ceiling saturation. Between 2025-04-23 and 2025-05-14 the
    pakistan_west percentile moved 2.2 points (97.8-100.0) while the
    underlying share moved 5.5-fold (0.214% to 1.173%). The intensity
    information existed and the transform destroyed it, exactly when
    the instrument mattered most.
  * Cross-channel incommensurability. Percentiles are within-channel
    ranks against different reference distributions; averaging them
    has no clean interpretation. Shares are genuinely commensurable --
    they are all fractions of the same daily corpus.
  * Cross-time incomparability. A 90 in 2019 and a 90 in 2026 are
    ranks against different two-year baselines. Shares carry the same
    meaning in every year.

Publishing shares does not fix the percentile series; it makes the
percentile series auditable and gives every downstream user the raw
material to build their own transform. The percentile remains the
headline because it answers "loud for this channel?", which a bare
share cannot.

  python -m src.publish_shares    writes docs/data/shares.csv + .json
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from src import provenance

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "raw" / "gdelt_volume.csv"
SITE_DATA = ROOT / "docs" / "data"
CHANNELS = ["pakistan_west", "china_east", "gulf_energy", "us_trade",
            "shipping"]


def rows() -> list[dict[str, str]]:
    with STORE.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    src = rows()
    if not src:
        raise SystemExit("[shares] empty store; refusing to publish")

    # The series is not one instrument (referee finding #10). Most days
    # are DOC API counts; a minority were measured by the Web NGrams
    # bridge and divided by an estimated splice ratio to reach the API's
    # scale. Publishing them in one column without saying which is which
    # invites every user to compute a mean across a seam they cannot
    # see, so the label ships in the data rather than in a footnote.
    source_by_day = provenance.by_day()

    out_csv = SITE_DATA / "shares.csv"
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date"] + CHANNELS + ["source"])
        for r in src:
            w.writerow([r["date"]] + [r.get(c, "") for c in CHANNELS]
                       + [source_by_day.get(r["date"], "")])

    # Gap disclosure travels WITH the data, not in a footnote: a
    # missing day is a hole in the denominator of anything a user
    # computes, and silence about it is how quiet errors propagate.
    have = {r["date"] for r in src}
    from datetime import date, timedelta
    start = date.fromisoformat(src[0]["date"])
    end = date.fromisoformat(src[-1]["date"])
    missing = []
    cur = start
    while cur <= end:
        if cur.isoformat() not in have:
            missing.append(cur.isoformat())
        cur += timedelta(days=1)

    payload = {
        "_meta": {
            "what": ("The QUANTITY the index is built from: each "
                     "channel's daily share of GDELT-monitored articles, "
                     "in percent of the day's monitored corpus. This is "
                     "the input to the published percentile series, and "
                     "it is published as a first-class artifact so any "
                     "reader can apply their own normalization rather "
                     "than accepting ours."),
            "units": "percent of the day's monitored article corpus",
            "why_this_matters": (
                "Percentiles saturate. Across 2025-04-23 to 2025-05-14 "
                "the pakistan_west percentile moved 2.2 points while "
                "this share moved 5.5-fold; the intensity information "
                "lives here, not in the rank. Shares are also "
                "commensurable across channels and across years, which "
                "percentiles are not: a rank is taken against each "
                "channel's own trailing two years."),
            "instrument_is_not_constant": provenance.summary(),
            "known_gaps": missing,
            "n_known_gaps": len(missing),
            "gap_note": (
                "Days absent from the store entirely, listed rather "
                "than interpolated; a user computing monthly means "
                "should know which months are short. CAUSE, TESTED "
                "2026-08-07: these are an upstream absence, not "
                "un-backfilled fetch failures. A refetch of "
                "2025-06-13..2025-07-03 returns 06-13, 06-14, 07-02 and "
                "07-03 -- the days bracketing the gap -- and nothing for "
                "the seventeen between, which are 17 of the 21 missing "
                "days. GDELT has no data there. The remaining four "
                "(2017-12-01, 2017-12-02, 2020-10-20, 2023-03-23) could "
                "not be tested: the probes were rate-limited into "
                "failure, so their cause is unverified rather than "
                "assumed to match."),
            "first_day": src[0]["date"],
            "last_day": src[-1]["date"],
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "csv": "shares.csv",
    }
    (SITE_DATA / "shares.json").write_text(json.dumps(payload),
                                           encoding="utf-8")
    print(f"[shares] wrote shares.csv ({len(src)} days, "
          f"{src[0]['date']} to {src[-1]['date']}) and shares.json "
          f"disclosing {len(missing)} known gaps")


if __name__ == "__main__":
    main()
