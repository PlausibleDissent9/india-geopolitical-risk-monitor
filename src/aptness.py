"""
Machine aptness pre-filter (founder order 2026-08-06: "a child could
eliminate the rainfall stories; let the machine do the heavy lifting").

Labels every published receipts article ON / OFF / ABSTAIN against the
REGISTERED rubric (auditor/RUBRIC.md) using claude-haiku-4-5 -- the
model named in the approved budget line. Honesty constraints, all
load-bearing:

  - Scores are never touched. This is a display-layer filter.
  - The page collapses OFF articles with a visible count and a toggle;
    nothing is silently deleted.
  - The machine's error rate is MEASURED against the founder's own
    rulings (audit_queue.csv human_label) and published with the
    payload. The founder's taps are the audit of the machine.
  - Fail-closed: without ANTHROPIC_API_KEY this module prints a skip
    line and writes nothing; the site simply shows unfiltered receipts
    rather than stale or guessed labels.
  - Evidence is headline + domain only (the rubric's own rule); the
    model is told to ABSTAIN when that is not enough.

  python -m src.aptness      labels docs/data/receipts.json articles
Writes docs/data/aptness.json.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"
RUBRIC = ROOT / "auditor" / "RUBRIC.md"
QUEUE = ROOT / "data" / "raw" / "audit_queue.csv"

MODEL = "claude-haiku-4-5"
RUBRIC_VERSION = "1.0.0"

SCHEMA = {
    "type": "object",
    "properties": {
        "labels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "label": {"type": "string",
                              "enum": ["ON", "OFF", "ABSTAIN"]},
                },
                "required": ["index", "label"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["labels"],
    "additionalProperties": False,
}


def label_channel(client: Any, channel: str, rubric: str,
                  articles: list[dict]) -> dict[int, str]:
    """One request per channel: number the headlines, get back an
    index->label array under a strict schema."""
    lines = [f"{i}. [{a.get('domain', '')}] {a.get('title', '')}"
             for i, a in enumerate(articles)]
    prompt = (
        f"{rubric}\n\n"
        f"Channel under audit: {channel}\n\n"
        "Label EVERY numbered article below ON, OFF, or ABSTAIN under "
        "the rubric's definition for this channel. The evidence is the "
        "headline and source domain only -- exactly as the rubric "
        "requires; ABSTAIN when that is not enough to rule. Return one "
        "label per index, covering all indices.\n\n" + "\n".join(lines)
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    if response.stop_reason == "refusal":
        print(f"[aptness] {channel}: model refused; leaving unlabeled")
        return {}
    text = next(b.text for b in response.content if b.type == "text")
    out: dict[int, str] = {}
    for row in json.loads(text)["labels"]:
        i = int(row["index"])
        if 0 <= i < len(articles):
            out[i] = row["label"]
    return out


def founder_agreement(labels_by_url: dict[str, str]) -> dict[str, Any]:
    """Machine vs founder on the URLs both have ruled on. The founder's
    rulings are the gold standard; this number is the machine's audit."""
    if not QUEUE.exists():
        return {"n_overlap": 0, "rate": None}
    with QUEUE.open(encoding="utf-8") as f:
        founder = {r["url"]: (r.get("human_label") or "").strip().upper()
                   for r in csv.DictReader(f)
                   if (r.get("human_label") or "").strip().upper() in ("ON", "OFF")}
    overlap = [(u, lab) for u, lab in labels_by_url.items()
               if u in founder and lab in ("ON", "OFF")]
    agree = sum(1 for u, lab in overlap if founder[u] == lab)
    return {"n_overlap": len(overlap),
            "rate": round(agree / len(overlap), 3) if overlap else None}


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[aptness] no ANTHROPIC_API_KEY; skipping (fail-closed, "
              "site shows unfiltered receipts)")
        return
    import anthropic

    receipts_path = SITE_DATA / "receipts.json"
    if not receipts_path.exists():
        sys.exit("[aptness] no receipts payload to label")
    receipts = json.loads(receipts_path.read_text(encoding="utf-8"))
    rubric = RUBRIC.read_text(encoding="utf-8")
    client = anthropic.Anthropic()

    labels: dict[str, dict[str, str]] = {}
    counts = {"ON": 0, "OFF": 0, "ABSTAIN": 0}
    for ch, block in (receipts.get("channels") or {}).items():
        articles = block.get("articles") or []
        if not articles:
            continue
        try:
            by_index = label_channel(client, ch, rubric, articles)
        except Exception as e:  # noqa: BLE001 -- one channel never loses the rest
            print(f"[aptness] {ch} failed: {e}")
            continue
        ch_labels = {}
        for i, a in enumerate(articles):
            lab = by_index.get(i, "ABSTAIN")  # unlabeled = never hidden
            ch_labels[a["url"]] = lab
            counts[lab] = counts.get(lab, 0) + 1
        labels[ch] = ch_labels
        print(f"[aptness] {ch}: {len(ch_labels)} labeled")

    flat = {u: lab for ch_labels in labels.values()
            for u, lab in ch_labels.items()}
    payload = {
        "_meta": {
            "what": ("Machine aptness labels for every published receipts "
                     "article, under the registered rubric "
                     "(auditor/RUBRIC.md), from headline + domain only. "
                     "Display-layer only: OFF articles are collapsed with "
                     "a visible count, never deleted, and no score is "
                     "touched. The founder's own rulings audit the "
                     "machine; the agreement rate publishes here."),
            "model": MODEL,
            "rubric_version": RUBRIC_VERSION,
            "date": receipts.get("date"),
            "counts": counts,
            "founder_agreement": founder_agreement(flat),
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "channels": labels,
    }
    (SITE_DATA / "aptness.json").write_text(
        json.dumps(payload), encoding="utf-8")
    print(f"[aptness] wrote aptness.json: {counts}, agreement "
          f"{payload['_meta']['founder_agreement']}")


if __name__ == "__main__":
    main()
