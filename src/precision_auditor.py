"""
Standing adversarial precision auditor (practitioner item 10), the
data half. The judging half is performed by the nightly agent run
applying auditor/RUBRIC.md and recording labels; this module never
guesses labels itself.

  --sample    draw today's audit sample from the receipts payload into
              data/raw/audit_queue.csv (label column empty, ABSTAIN
              allowed, rubric version stamped)
  --publish   compute per-channel precision from labeled rows and the
              author-agreement statistic when author labels exist,
              write docs/data/precision.json; the series is marked
              UNCALIBRATED until author labels reach n>=100

Author labels arrive as rows in data/raw/audit_labels_author.csv
(url,label) from the Why-card tap flow; machine labels fill the
machine_label column of the queue. Precision uses machine labels only
after calibration; before it, published numbers carry the
uncalibrated flag and the site says so.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
QUEUE = RAW / "audit_queue.csv"
AUTHOR = RAW / "audit_labels_author.csv"
OUT = ROOT / "docs" / "data" / "precision.json"
RUBRIC_VERSION = "1.0.0"
PER_CHANNEL = 8
CALIBRATION_N = 100
SEED_SALT = 20260803

FIELDS = ["date", "channel", "url", "title", "domain",
          "machine_label", "rubric_version", "human_label"]


def sample() -> None:
    receipts_path = ROOT / "docs" / "data" / "receipts.json"
    if not receipts_path.exists():
        print("[auditor] no receipts payload; nothing to sample")
        return
    receipts = json.loads(receipts_path.read_text(encoding="utf-8"))
    day = receipts.get("date", date.today().isoformat())
    existing: set[tuple[str, str]] = set()
    rows: list[dict] = []
    if QUEUE.exists():
        with QUEUE.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
            existing = {(r["date"], r["url"]) for r in rows}
    added = 0
    for ch, c in (receipts.get("channels") or {}).items():
        arts = c.get("articles") or []
        rng = random.Random(f"{SEED_SALT}:{day}:{ch}")
        picks = rng.sample(arts, min(PER_CHANNEL, len(arts)))
        for a in picks:
            if (day, a["url"]) in existing:
                continue
            rows.append({"date": day, "channel": ch, "url": a["url"],
                         "title": (a.get("title") or "")[:300],
                         "domain": a.get("domain", ""),
                         "machine_label": "", "rubric_version": RUBRIC_VERSION,
                         "human_label": ""})
            added += 1
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    with QUEUE.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"[auditor] sampled +{added} for {day}; queue {len(rows)} rows")


def publish() -> None:
    rows = []
    if QUEUE.exists():
        with QUEUE.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    labeled = [r for r in rows if r["machine_label"] in ("ON", "OFF")]
    abstained = [r for r in rows if r["machine_label"] == "ABSTAIN"]

    author: dict[str, str] = {}
    if AUTHOR.exists():
        with AUTHOR.open(encoding="utf-8") as f:
            author = {r["url"]: r["label"].strip().upper()
                      for r in csv.DictReader(f) if r.get("label")}
    # The founder's live-review rulings land in the queue's human_label
    # column (the in-chat flow, 2026-08-05, after the portal tap flow
    # broke); they are author labels in every sense and count toward
    # calibration. Firm rulings only: an abstention calibrates nothing,
    # so it is counted separately and never inflates n.
    author_abstained = 0
    for r in rows:
        h = (r.get("human_label") or "").strip().upper()
        if h in ("ON", "OFF"):
            author.setdefault(r["url"], h)
        elif h == "ABSTAIN":
            author_abstained += 1
    overlap = [r for r in labeled if r["url"] in author]
    agree = sum(1 for r in overlap if r["machine_label"] == author[r["url"]])
    n_author = len(author)
    calibrated = n_author >= CALIBRATION_N

    channels: dict[str, dict] = {}
    for r in labeled:
        d = channels.setdefault(r["channel"], {"on": 0, "n": 0})
        d["n"] += 1
        d["on"] += int(r["machine_label"] == "ON")
    per_channel = {
        ch: {"n_labeled": d["n"],
             "precision": round(d["on"] / d["n"], 3) if d["n"] else None}
        for ch, d in channels.items()}

    payload = {
        "_meta": {
            "what": ("Standing precision audit: machine labels applied under "
                     "the versioned rubric (auditor/RUBRIC.md), published as "
                     "found, never tuned to a target. UNCALIBRATED until the "
                     "author's independent labels reach the registration "
                     "threshold; the agreement statistic publishes with its "
                     "n. Abstentions are counted, not guessed."),
            "rubric_version": RUBRIC_VERSION,
            "generated": date.today().isoformat(),
        },
        "calibrated": calibrated,
        "author_labels_n": n_author,
        "author_abstained_n": author_abstained,
        "calibration_threshold": CALIBRATION_N,
        "agreement": {"n_overlap": len(overlap),
                      "rate": round(agree / len(overlap), 3) if overlap else None},
        "abstained": len(abstained),
        "channels": per_channel,
    }
    OUT.write_text(json.dumps(payload), encoding="utf-8")
    print(f"[auditor] published: calibrated={calibrated} "
          f"author_n={n_author} channels={per_channel}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--publish", action="store_true")
    a = ap.parse_args()
    if a.sample:
        sample()
    if a.publish:
        publish()
    if not (a.sample or a.publish):
        ap.print_help()


if __name__ == "__main__":
    main()
