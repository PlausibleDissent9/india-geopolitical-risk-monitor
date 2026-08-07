"""
How much of a channel's loudness is republication? (referee finding
#23, 2026-08-07)

The index counts ARTICLES. So a single wire story picked up by two
hundred outlets moves a channel exactly as far as two hundred newsrooms
independently deciding that something mattered. Those are different
events in the world and the index cannot tell them apart. Every reading
of every channel carries this ambiguity and until now the project had
never quantified it.

It turns out the pipeline was measuring it all along and throwing the
measurement away. `receipts_ngrams.assemble_channel` builds a pool
keyed by URL (distinct articles), then collapses it by normalized title
(distinct STORIES), and published only the second number. The ratio of
the two is the syndication multiplier, computed over the day's full
scanned corpus rather than estimated from a side sample:

    multiplier = distinct articles / distinct stories

1.0 means every article is its own story. 3.5 means the average story
appears three and a half times, so roughly 71% of that channel's
article count is republication.

WHAT THIS DOES NOT DO
---------------------
It does not correct the index and nothing here feeds a score. There is
no defensible way to "deflate" a channel by its multiplier: republication
is not noise, it is how attention actually propagates, and an editor
choosing to run the wire copy is a real editorial decision. What the
number does is let a reader ask the right question of a spike -- more
newsrooms, or more copies? -- and answer it from published data.

THE ESTIMATOR IS BIASED DOWNWARD AT SMALL SAMPLES
-------------------------------------------------
Duplicate pairs are found only when both copies land in the sample, so
the observed multiplier falls toward 1.0 as the sampled fraction falls.
This is not a theoretical worry; it is measured. Same channel, same day
(pakistan_west, 2026-08-05):

    28,575 docs sampled  ->  multiplier 1.923
   119,349 docs sampled  ->  multiplier 3.478

The smaller sample understates republication by 45%. Only full-day
extended scans therefore enter the published history, and the sampled
depth travels with every row so that a reader can check comparability
instead of trusting that it holds.

  python -m src.syndication [YYYY-MM-DD]     measure a day, publish
  python -m src.syndication --rebuild        recompute all cached days
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from src import receipts_ngrams as rn

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"
HISTORY = ROOT / "data" / "raw" / "syndication.csv"
FIELDS = ["date", "channel", "n_articles", "n_stories", "n_domains",
          "multiplier", "n_docs_sampled"]

# Below this the estimator's downward bias is severe enough that a row
# would mislead more than it informs. The extended lane routinely scans
# 100k+; the sampled lane lands near 28k, which measurably understates.
MIN_DOCS_FOR_HISTORY = 60_000


def measure(day: date, extended: bool = True) -> dict[str, Any] | None:
    """Per-channel syndication for one day, or None when the day's
    corpus is not available. Never fetches when the corpus is cached --
    this reads the same scan the receipts lane already paid for."""
    with open(ROOT / "source_tiers.json", encoding="utf-8") as f:
        tiers: dict[str, int] = json.load(f)["tiers"]
    with open(ROOT / "dictionaries.json", encoding="utf-8") as f:
        dictionaries = json.load(f)

    specs = rn.group_specs()
    corpus = rn.collect_corpus(day, specs, extended=extended)
    if corpus is None:
        return None

    out: dict[str, Any] = {"date": day.isoformat(),
                           "n_docs_sampled": corpus["n_docs_sampled"],
                           "extended": extended, "channels": {}}
    for ch in rn.CHANNELS:
        keys = rn.channel_doc_keys(ch, specs, corpus)
        # supplement=None on purpose: the artlist supplement is a
        # deliberately biased draw (it exists to restore tier-1 wire
        # ORIGINALS the sample missed), so including it would inflate
        # exactly the quantity being measured.
        blk = rn.assemble_channel(ch, dictionaries[ch], keys, corpus,
                                  tiers, None)
        out["channels"][ch] = {
            "n_articles": blk["n_pool_urls"],
            "n_stories": blk["n_pool_unique"],
            "n_domains": blk["n_pool_domains"],
            "multiplier": blk["syndication_multiplier"],
        }
    return out


def _history_rows() -> list[dict[str, str]]:
    if not HISTORY.exists():
        return []
    with HISTORY.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def record(m: dict[str, Any]) -> int:
    """Append one day's channels to the history, refusing depths where
    the estimator is known to understate. Returns rows written."""
    if m["n_docs_sampled"] < MIN_DOCS_FOR_HISTORY:
        print(f"[syndication] {m['date']}: only {m['n_docs_sampled']:,} docs "
              f"sampled (< {MIN_DOCS_FOR_HISTORY:,}); measured but NOT "
              "recorded -- the multiplier is biased low at this depth")
        return 0
    rows = _history_rows()
    have = {(r["date"], r["channel"]) for r in rows}
    added = []
    for ch, v in m["channels"].items():
        if (m["date"], ch) in have:
            continue
        added.append({"date": m["date"], "channel": ch,
                      "n_articles": v["n_articles"],
                      "n_stories": v["n_stories"],
                      "n_domains": v["n_domains"],
                      "multiplier": v["multiplier"],
                      "n_docs_sampled": m["n_docs_sampled"]})
    if not added:
        return 0
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    write_header = not HISTORY.exists()
    with HISTORY.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            w.writeheader()
        w.writerows(added)
    return len(added)


def publish() -> dict[str, Any]:
    rows = _history_rows()
    per_channel: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        per_channel.setdefault(r["channel"], []).append({
            "date": r["date"],
            "n_articles": int(r["n_articles"]),
            "n_stories": int(r["n_stories"]),
            "n_domains": int(r["n_domains"]),
            "multiplier": float(r["multiplier"]),
            "n_docs_sampled": int(r["n_docs_sampled"]),
        })
    summary = {}
    for ch, series in per_channel.items():
        series.sort(key=lambda x: x["date"])
        vals = [s["multiplier"] for s in series]
        summary[ch] = {
            "latest": series[-1],
            "n_days": len(series),
            # No mean until there are days to average. A one-day "mean"
            # dressed as a summary statistic is how a single observation
            # gets cited as an established rate.
            "mean": (round(sum(vals) / len(vals), 3)
                     if len(vals) >= 3 else None),
            "min": min(vals) if len(vals) >= 3 else None,
            "max": max(vals) if len(vals) >= 3 else None,
        }

    days = sorted({r["date"] for r in rows})
    payload = {
        "_meta": {
            "what": (
                "Articles per distinct story, per channel, per day, over "
                "the day's full scanned corpus. The index counts "
                "articles, so a wire story republished by 200 outlets "
                "moves a channel as far as 200 newsrooms independently "
                "reacting; this is the measurement of how often that "
                "happens."),
            "definition": (
                "multiplier = distinct article URLs matching the channel "
                "/ distinct normalized headlines among them. 1.0 = every "
                "article is its own story."),
            "does_not_correct_the_index": (
                "Nothing here feeds a score. Republication is not noise "
                "-- an editor running wire copy is a real editorial "
                "decision -- so there is no defensible deflation. The "
                "number exists so a reader can ask of any spike whether "
                "it was more newsrooms or more copies, and answer it "
                "from published data."),
            "known_bias": (
                "Downward at small samples: a duplicate is only visible "
                "when both copies land in the scan. Measured on "
                "pakistan_west 2026-08-05, 28,575 docs gives 1.923 and "
                "119,349 docs gives 3.478 -- the smaller sample "
                "understates by 45%. Only scans of at least "
                f"{MIN_DOCS_FOR_HISTORY:,} documents enter this history, "
                "and n_docs_sampled travels with every row so "
                "comparability can be checked rather than assumed."),
            "n_days": len(days),
            "first_day": days[0] if days else None,
            "last_day": days[-1] if days else None,
            "min_docs_for_history": MIN_DOCS_FOR_HISTORY,
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "channels": summary,
        "series": per_channel,
    }
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / "syndication.json").write_text(
        json.dumps(payload, indent=1), encoding="utf-8")
    return payload


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        days = [date.fromisoformat(a) for a in args]
    else:
        latest = json.loads(
            (SITE_DATA / "latest.json").read_text(encoding="utf-8"))
        days = [date.fromisoformat(latest["date"])]

    for day in days:
        m = measure(day, extended=True)
        if m is None:
            print(f"[syndication] {day}: no extended corpus cached; skipped")
            continue
        for ch, v in m["channels"].items():
            print(f"[syndication] {day} {ch:15s} "
                  f"{v['n_articles']:6d} articles -> {v['n_stories']:6d} "
                  f"stories across {v['n_domains']:5d} domains  "
                  f"x{v['multiplier']}")
        n = record(m)
        print(f"[syndication] {day}: {n} rows recorded")

    p = publish()
    print(f"[syndication] published {p['_meta']['n_days']} day(s) "
          f"covering {p['_meta']['first_day']}..{p['_meta']['last_day']}")


if __name__ == "__main__":
    main()
