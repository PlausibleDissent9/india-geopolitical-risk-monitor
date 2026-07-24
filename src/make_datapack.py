"""
Weekly datapack: numbers and sources only, written to
notes-inbox/datapack_YYYY-Www.md. The weekly note itself is Ishan's
writing; this file is its evidence base. For each channel that moved more
than MOVER_THRESHOLD percentile points in the week, the dossier section
lists the top articles from the same channel query over the week's range
(GDELT artlist, relevance-sorted) -- no summarization, no synthesis.
Run by CI on Fridays, or manually: python -m src.make_datapack
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from . import fetch_gdelt

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"
INBOX = ROOT / "notes-inbox"

MOVER_THRESHOLD = 10.0  # percentile points over the week
MAX_ARTICLES = 15


def _dossier(channel: str, start: pd.Timestamp, end: pd.Timestamp) -> list[dict]:
    """Relevance-sorted articles for one channel over the week."""
    with open(ROOT / "dictionaries.json", encoding="utf-8") as f:
        d = json.load(f)
    spec = d[channel]
    pool: dict[str, dict] = {}
    for q in fetch_gdelt.build_queries(spec["terms"], spec.get("anchor")):
        for a in fetch_gdelt.fetch_articles(
            q, start.date(), end.date(), maxrecords=10
        ):
            if a["url"]:
                pool.setdefault(a["url"], a)
    return list(pool.values())[:MAX_ARTICLES]


def main() -> None:
    history = json.loads((SITE_DATA / "history.json").read_text(encoding="utf-8"))
    episodes = json.loads((SITE_DATA / "episodes.json").read_text(encoding="utf-8"))

    scores = pd.DataFrame(
        {ch: vals for ch, vals in history["channels"].items()},
        index=pd.to_datetime(history["dates"]),
    )
    scores["composite"] = history["composite"]
    labels = history["labels"]

    last = scores.dropna(how="all").index.max()
    week_ago = last - pd.Timedelta(days=7)
    cur = scores.loc[last]
    prev_idx = scores.index[scores.index <= week_ago]
    prev = scores.loc[prev_idx.max()] if len(prev_idx) else cur

    iso = date.today().isocalendar()
    week_tag = f"{iso.year}-W{iso.week:02d}"

    lines = [
        f"# IGRM datapack {week_tag}",
        f"Data through {last.date().isoformat()}. Numbers only -- the note is yours.",
        "",
        "## Scores (percentile, 0-100)",
        "",
        "| Channel | Now | 7d ago | Change |",
        "|---|---|---|---|",
    ]
    for ch in list(history["channels"]) + ["composite"]:
        name = labels.get(ch, "Composite")
        now, ago = cur[ch], prev[ch]
        chg = (now - ago) if pd.notna(now) and pd.notna(ago) else None
        lines.append(
            f"| {name} | {_f(now)} | {_f(ago)} | {_f(chg, signed=True)} |"
        )

    recent = [e for e in episodes
              if pd.Timestamp(e["end"]) >= last - pd.Timedelta(days=14)]
    lines += ["", "## Episodes in the last 14 days", ""]
    if recent:
        for e in recent:
            lines.append(
                f"- {e['label']}: {e['start']} to {e['end']} "
                f"(peak {e['peak_date']}, {e['n_spike_days']} spike days)"
            )
    else:
        lines.append("- none")

    top = scores[list(history["channels"])].loc[last].astype(float)
    lines += [
        "",
        "## One number",
        "",
        f"- Highest channel today: {labels.get(top.idxmax(), top.idxmax())} "
        f"at {_f(top.max())}",
    ]

    movers = [
        ch for ch in history["channels"]
        if pd.notna(cur[ch]) and pd.notna(prev[ch])
        and abs(cur[ch] - prev[ch]) > MOVER_THRESHOLD
    ]
    lines += ["", "## Sources: what drove the movers", ""]
    if movers:
        for ch in movers:
            lines.append(f"### {labels.get(ch, ch)} "
                         f"({_f(cur[ch] - prev[ch], signed=True)} pts)")
            lines.append("")
            try:
                arts = _dossier(ch, week_ago, last)
            except RuntimeError as e:
                arts = []
                lines.append(f"- article fetch failed: {e}")
            for a in arts:
                d8 = a["date"]
                nice = f"{d8[:4]}-{d8[4:6]}-{d8[6:8]}" if len(d8) == 8 else d8
                lines.append(f"- [{a['title']}]({a['url']}) "
                             f"-- {a['domain']}, {nice}")
            lines.append("")
    else:
        lines.append(f"- no channel moved more than {MOVER_THRESHOLD:.0f} "
                     "points this week")

    lines += ["", "## Your note", "", "<!-- ~250 words. Headline claim, "
              "mechanism (cite the sources above), what it does and doesn't "
              "imply, one number worth remembering. -->", ""]

    INBOX.mkdir(parents=True, exist_ok=True)
    out = INBOX / f"datapack_{week_tag}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[datapack] wrote {out}")


def _f(x, signed: bool = False) -> str:
    if x is None or pd.isna(x):
        return "--"
    return f"{x:+.1f}" if signed else f"{x:.1f}"


if __name__ == "__main__":
    main()
