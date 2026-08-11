"""RBI Weekly Statistical Supplement: foreign exchange reserves, sessionless.

Source, verified end-to-end on 2026-08-11 (analysis/s_track_verification.md):

    GET https://rbi.org.in/Scripts/BS_viewWssExtract.aspx?SelectedDate=M/DD/YYYY

renders Table 2 "Foreign Exchange Reserves" INLINE as HTML -- a public page,
no session, no file download. Cross-validated against the DBIE gateway to the
million (Total Reserves US$ 692,866 Mn, week as on 2026-07-31) before this
module existed; no fetcher ships on a guessed endpoint.

Emits data/raw/rbi_wss_reserves.csv: one row per (as_on_date, item), values in
US$ million exactly as published. Append-or-replace per as_on_date, sorted,
deterministic. Refusal-first: a page without the table, the as-on date, or the
Total Reserves row raises rather than writing anything partial.

Citation: Reserve Bank of India, Weekly Statistical Supplement, edition date
as fetched. Public data; cite the edition.

  python -m src.fetch_rbi_wss --date 8/07/2026
  python -m src.fetch_rbi_wss --latest 4      # last N Friday editions
"""
from __future__ import annotations

import argparse
import csv
import re
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "rbi_wss_reserves.csv"
BASE = "https://rbi.org.in/Scripts/BS_viewWssExtract.aspx"
_UA = {"User-Agent": "Mozilla/5.0 (IGRM research fetcher; igrm.in)"}

# The rows Table 2 carries, in published order. Names are matched on the
# published labels; anything else in the table is ignored, never guessed at.
ITEMS = (
    "1 Total Reserves",
    "1.1 Foreign Currency Assets",
    "1.2 Gold",
    "1.3 SDRs",
    "1.4 Reserve Position in the IMF",
)


class WssParseError(ValueError):
    """The page did not carry what the published table promises."""


def fetch_edition(edition: str) -> str:
    req = urllib.request.Request(f"{BASE}?SelectedDate={edition}", headers=_UA)
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")


def parse_reserves(html: str) -> tuple[str, dict[str, int]]:
    """Return (as_on ISO date, {item: US$ Mn}) from an edition page.

    Layout, as verified: after the "Foreign Exchange Reserves" heading comes
    "As on <Mon>. <D>, <YYYY>", then per item eight numeric cells --
    (Rs Cr, US$ Mn) for level, then three variation pairs. We take cell #2,
    the US$ Mn LEVEL, and ignore variations entirely.
    """
    i = html.find("Foreign Exchange Reserves")
    if i < 0:
        raise WssParseError("no Foreign Exchange Reserves table on page")
    text = re.sub(r"<[^>]+>", "|", html[i:i + 20000])
    text = re.sub(r"&nbsp;?|\s+", " ", text)

    m = re.search(r"As on ([A-Za-z]{3})\.? (\d{1,2}), (\d{4})", text)
    if not m:
        raise WssParseError("no 'As on' date near the reserves table")
    as_on = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}",
                              "%b %d %Y").date().isoformat()

    out: dict[str, int] = {}
    for item in ITEMS:
        mi = re.search(re.escape(item) + r"[^0-9-]*([0-9,]+)[^0-9-]+([0-9,]+)",
                       text)
        if not mi:
            raise WssParseError(f"row missing: {item}")
        out[item] = int(mi.group(2).replace(",", ""))
    if out["1 Total Reserves"] <= 0:
        raise WssParseError("non-positive total reserves")
    return as_on, out


def write_rows(as_on: str, values: dict[str, int]) -> None:
    rows: dict[tuple[str, str], str] = {}
    if OUT.exists():
        with OUT.open() as f:
            for row in csv.DictReader(f):
                rows[(row["as_on_date"], row["item"])] = row["usd_mn"]
    for item, v in values.items():
        rows[(as_on, item)] = str(v)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["as_on_date", "item", "usd_mn"])
        for (d, item) in sorted(rows):
            w.writerow([d, item, rows[(d, item)]])


def fridays(n: int) -> list[str]:
    """The last n WSS edition dates (Fridays), newest first, M/DD/YYYY."""
    d = date.today()
    d -= timedelta(days=(d.weekday() - 4) % 7)
    return [f"{x.month}/{x.day:02d}/{x.year}"
            for x in (d - timedelta(weeks=k) for k in range(n))]


def main() -> None:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--date", help="edition date M/DD/YYYY")
    g.add_argument("--latest", type=int, help="last N Friday editions")
    args = p.parse_args()
    editions = [args.date] if args.date else fridays(args.latest)
    banked = 0
    for ed in editions:
        try:
            as_on, values = parse_reserves(fetch_edition(ed))
        except WssParseError as exc:
            # An edition can legitimately not exist yet (holiday shift);
            # say so and continue -- but a run that banks NOTHING fails loud.
            print(f"[rbi-wss] {ed}: {exc}")
            continue
        write_rows(as_on, values)
        banked += 1
        print(f"[rbi-wss] {ed}: as_on {as_on}, total US$ {values['1 Total Reserves']:,} Mn")
    if not banked:
        raise SystemExit("[rbi-wss] no edition parsed; refusing quiet success")


if __name__ == "__main__":
    main()
