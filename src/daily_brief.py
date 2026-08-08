"""Withdrawn machine-written daily-brief experiment.

The public lane was disabled on 2026-08-08 after generated prose stated
numbers absent from its input context and repurposed display-selected receipt
statistics as substantive evidence. The prediction-word deny-list below is
preserved as instrument history; it was never a factual-grounding check.

``main()`` has no generation branch: it cannot import a model client, make a
network call, or write a payload. Context and prompt helpers remain only for
auditing the failed design and for a future evidence-locked redesign.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"
PROMPT_PATH = ROOT / "prompts" / "daily_brief.md"

CHANNELS = ["pakistan_west", "china_east", "gulf_energy", "us_trade", "shipping"]
MODEL = "claude-opus-5"
MAX_TOKENS = 2000
PUBLICATION_ENABLED = False

# Measurement language only: a brief that predicts is not published.
# The deny-list is deliberately blunt; a false positive costs one
# day's brief, a false negative costs the project's positioning.
BANNED = re.compile(
    r"\b(will (rise|fall|increase|decrease|escalate|worsen|improve)|"
    r"predicts?|forecasts?|is likely to|expect(s|ed)? to)\b",
    re.IGNORECASE,
)

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "composite": {"type": "string"},
        "channels": {
            "type": "object",
            "properties": {ch: {"type": "string"} for ch in CHANNELS},
            "required": CHANNELS,
            "additionalProperties": False,
        },
    },
    "required": ["composite", "channels"],
    "additionalProperties": False,
}


def load_prompt() -> tuple[str, str]:
    """The registered prompt and its version. The system prompt is the
    section after the '## System prompt' heading; the header above it
    is registration metadata, not model input."""
    text = PROMPT_PATH.read_text(encoding="utf-8")
    version_match = re.search(r"^version:\s*(\S+)", text, re.MULTILINE)
    version = version_match.group(1) if version_match else "unknown"
    _, _, body = text.partition("## System prompt served to the model")
    return body.strip(), version


def build_context() -> dict[str, Any]:
    """Reconstruct the failed design's compact input for auditing.

    Receipt evidence is included only when its news date equals the score
    date. The live experiment lacked that gate and could pair one day's scores
    with another day's displayed receipts.
    """
    def read(name: str) -> dict[str, Any]:
        p = SITE_DATA / name
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    latest = read("latest.json")
    receipts = read("receipts.json")
    latest_date = latest.get("date")
    receipts_date = receipts.get("date")
    receipts_aligned = bool(latest_date and latest_date == receipts_date)
    evidence: dict[str, Any] = {}
    if receipts_aligned:
        for ch, v in (receipts.get("channels") or {}).items():
            arts = v.get("articles", [])
            evidence[ch] = {
                "n_title_key_representatives_shown": len(arts),
                "n_distinct_urls_in_pool": v.get("n_pool_urls"),
                "n_corpus_title_keys": v.get("n_corpus_title_keys"),
                "n_scored_sample_urls": v.get("n_matched_in_corpus"),
                "pool_tier12_share": v.get("pool_tier12_share"),
                "top_headlines": [a.get("title") for a in arts[:5]],
            }
    return {
        "date": latest_date,
        "composite": latest.get("composite"),
        "channels": latest.get("channels"),
        "receipts": evidence,
        "receipts_date": receipts_date,
        "receipts_aligned_to_scores": receipts_aligned,
    }


def lint(brief: str | None) -> str | None:
    """None for any brief that crosses into prediction; the payload
    carries the gap honestly instead of a softened rewrite."""
    if brief is None or BANNED.search(brief):
        return None
    return brief


def main() -> None:
    print("[daily_brief] withdrawn_factual_grounding_failure: no model "
          "call and no payload write")


if __name__ == "__main__":
    main()
