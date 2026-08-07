"""The negative-results register: every unflattering number, one payload.

The project's best evidence of honesty is scattered across the source
payloads where only a determined reader assembles it (the register counts
them itself rather than naming a number that goes stale). This register
compiles the numbers that did NOT go the project's way, each read live
from its source payload -- never hand-typed, so an entry that stops being
true stops being published (the hand-typed-number failure, class of
2026-08-07; the 2026-08-08 prose audit caught this file itself carrying
three hand-typed constants, one of them wrong, under a docstring claiming
it never does).

Prompted by ideation item A4 and by the referee report's closing line:
the honesty must live where the reader is, not in JSON nobody opens.

  python -m src.negative_results          write docs/data/negative_results.json
  python -m src.negative_results --check  inspect without writing
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"


def _load(name: str) -> dict:
    return json.loads((SITE_DATA / name).read_text(encoding="utf-8"))


def compute() -> list[dict[str, Any]]:
    """Each entry: the claim, the live number, and where it lives. A
    KeyError here means a source payload changed shape -- fail loudly
    rather than publish a register with silently missing rows."""
    rows: list[dict[str, Any]] = []

    baselines = _load("detection_baselines.json")
    hb = baselines["hit_rate_context"]

    g = _load("stress_gauge.json")["validation"]
    rows.append({
        "finding": "Fusing four sources made detection worse, not better",
        "number": f"{g['n_detected']} of {g['n_episodes']} episodes detected "
                  f"(hit rate {g['hit_rate']}) vs "
                  f"{hb['registered_criterion_hits']} of {hb['n_events']} for "
                  "the corresponding-channel press criterion across five "
                  "channels",
        "source": "data/stress_gauge.json",
        "reading": "the pre-registered four-source gauge detects a fraction "
                   "of what the channel-level press detector does; adding "
                   "modalities did not improve this registered diagnostic"})

    v = _load("validation.json")
    p = v["placebo"]
    placebo_baseline = baselines["placebo_context"]
    rows.append({
        "finding": "Placebo channels overlap real episodes far above zero",
        "number": f"{p['n_overlapping']} of {p['n_placebo_episodes']} placebo "
                  f"episodes ({round(100*p['overlap_fraction'],1)}%) overlap "
                  "real ones; duration-preserving random placement expects "
                  f"{100*placebo_baseline['random_placement_overlap_fraction']:.1f}%",
        "source": "data/detection_baselines.json",
        "reading": "part of every channel's signal is general news volume, "
                   f"and the excess over chance is "
                   f"{100*placebo_baseline['excess_over_random_fraction']:.1f} "
                   "points, not the full observed rate"})

    b = baselines["hit_rate_context"]
    rows.append({
        "finding": "A naive any-channel detector nearly matches the "
                   "registered hit rate",
        "number": f"naive {b['naive_any_channel_hits']} of {b['n_events']} vs "
                  f"registered {b['registered_criterion_hits']} of "
                  f"{b['n_events']}; chance {b['chance_expected_hits']}",
        "source": "data/detection_baselines.json",
        "reading": "detection alone is cheap; the channel attribution is "
                   "what the apparatus actually contributes"})

    cb = baselines["composite7_battery"]
    rows.append({
        "finding": "The 7-day headline barely beats chance as a detector",
        "number": f"composite7 detects {cb['hits']} of "
                  f"{cb['n_events_evaluable']} evaluable events on the "
                  f"registered threshold rule; chance is "
                  f"{cb['chance_expected_hits']}",
        "source": "data/detection_baselines.json",
        "reading": "the headline is a summary statistic, not the detector; "
                   "detection lives in the per-channel series, and the two "
                   "famous headline anecdotes were anecdotes"})

    w = _load("wiki_hindi.json")
    n_lead = len(w["channels_where_english_leads_on_both"])
    rows.append({
        "finding": "The index tracks English-language attention, not "
                   "Indian-language attention",
        "number": f"English Wikipedia leads Hindi on {n_lead} of "
                  f"{len(w['channels'])} channels, in both levels and "
                  "changes, with no channel in the other direction",
        "source": "data/wiki_hindi.json",
        "reading": "the construct is Anglophone press salience of India; "
                   "the name understates the qualifier"})

    # Thresholds come from the registration's own constants, because this
    # row shipped saying "floor of 0.6" when the registered withholding
    # floor is 0.4 (0.6 is the 'tracks' threshold) -- a wrong number in
    # the honesty register, caught by the 2026-08-08 prose audit.
    from src.back_extension import OVERLAP_THRESHOLDS
    be = _load("back_extension.json")["overlap_audit"]
    withheld = sorted(ch for ch, a in be.items() if "DOES NOT" in a["verdict"])
    rows.append({
        "finding": f"{len(withheld)} of {len(be)} historical channels "
                   "failed their own pre-registered test and were withheld",
        "number": ", ".join(f"{ch} r={be[ch]['r']}" for ch in withheld)
                  + f" against the registered floors: below "
                    f"{OVERLAP_THRESHOLDS['tracks']} a series is not "
                    f"published clean, below {OVERLAP_THRESHOLDS['partial']} "
                    "not at all",
        "source": "data/back_extension.json",
        "reading": "the withholding rule is the contribution; publishing "
                   "them anyway would have retracted it"})

    mc = _load("sector_sensitivity.json")["_meta"]["multiple_comparisons"]
    # Derive the cell count from the payload's own text rather than
    # hand-typing 39 -- the register's one rule.
    assert "NO cell survived" in mc, (
        "sector_sensitivity's multiple-comparisons note changed; re-derive "
        "this entry rather than shipping a stale claim")
    rows.append({
        "finding": "No sector shows a return sensitivity that survives "
                   "multiple-comparison correction",
        "number": mc.split("--")[0].strip(),
        "source": "data/sector_sensitivity.json",
        "reading": "with this episode set, sector sensitivity to salience "
                   "episodes is indistinguishable from zero once the "
                   "search is paid for"})

    pr = _load("priced_risk.json")["lead_lag"]
    rows.append({
        "finding": "The largest lead-lag association places the market first",
        "number": pr["reading"],
        "source": "data/priced_risk.json",
        "reading": "this index is not an early-warning system for anything "
                   "priced; whatever it is for, it is not that"})

    prec = _load("precision.json")
    rows.append({
        "finding": "Machine-labelled on-topic shares are uncalibrated and "
                   "low on two channels",
        "number": f"author labels {prec['author_labels_n']} of "
                  f"{prec['calibration_threshold']}; machine agreement "
                  f"{prec['agreement']['rate']} on n={prec['agreement']['n_overlap']}",
        "source": "data/precision.json",
        "reading": "precision claims wait for the human calibration to "
                   "reach its registered threshold"})

    sp = _load("splice_sensitivity.json")["summary"]["trailing_7_day"]
    worst = max(sp.items(), key=lambda kv: kv[1]["maximum_absolute_shift"])
    rows.append({
        "finding": "The headline is sensitive to a calibration constant "
                   "on one channel",
        "number": f"{worst[0]} 7-day score moves up to "
                  f"{worst[1]['maximum_absolute_shift']} points across "
                  "defensible splice ratios",
        "source": "data/splice_sensitivity.json",
        "reading": "the primary series is frozen while the founder decides; "
                   "the sensitivity is published rather than absorbed"})

    return rows


def main() -> None:
    check = "--check" in sys.argv
    rows = compute()
    n_sources = len({r["source"] for r in rows})

    from src import stamp_meta
    payload = {
        "_meta": {
            **stamp_meta.universal_fields("negative_results.json"),
            "what": (
                "Every number that did not go this project's way, compiled "
                "from the payloads where each lives. Read live from those "
                "payloads at build time, never hand-typed, so a row that "
                "stops being true stops being published."),
            "why": (
                "Anyone can publish good numbers. The reason to believe "
                "the flattering ones is that the unflattering ones are "
                "computed by the same pipeline on the same schedule -- and "
                "this file is where they stand together instead of being "
                f"scattered across {n_sources} payloads."),
            "n_findings": len(rows),
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "findings": rows,
    }
    if not check:
        (SITE_DATA / "negative_results.json").write_text(
            json.dumps(payload, indent=1), encoding="utf-8")
    print(f"[negatives] {len(rows)} findings compiled"
          + (" (check only)" if check else ""))


if __name__ == "__main__":
    main()
