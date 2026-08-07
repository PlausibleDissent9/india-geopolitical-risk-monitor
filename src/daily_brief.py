"""
Machine-written daily briefs (FICCI round 2; approved by the author in
chat 2026-08-04, NOTES_FOR_ISHAN.md 0.10 option b): one API call per
day turns the site's own published payloads into a short brief per
channel plus a composite line, labeled machine-written on the site and
never presented as the author's voice.

Fail-closed by design: no ANTHROPIC_API_KEY means no call and no
payload (the site simply shows no brief); a model refusal skips the
day; a brief that fails the measurement-language lint is dropped for
that channel, never softened. The prompt is a registered instrument
(prompts/daily_brief.md, versioned, append-only changelog).

Cost, measured at registration: one call of roughly 4K input and 1.5K
output tokens on claude-opus-5 is about $0.06 per day.

Run by CI daily after receipts, or manually: python -m src.daily_brief
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"
PROMPT_PATH = ROOT / "prompts" / "daily_brief.md"

CHANNELS = ["pakistan_west", "china_east", "gulf_energy", "us_trade", "shipping"]
MODEL = "claude-opus-5"
MAX_TOKENS = 2000

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
    """Compact evidence bundle from payloads the site already
    publishes; nothing here is fetched fresh, so the brief can never
    know more than the site it summarizes."""
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
    evidence: dict[str, Any] = {}
    for ch, v in (receipts.get("channels") or {}).items():
        arts = v.get("articles", [])
        evidence[ch] = {
            "n_articles": len(arts),
            "tier12_share": v.get("spike_quality_tier12_share"),
            "top_headlines": [a.get("title") for a in arts[:5]],
        }
    return {
        "date": latest.get("date"),
        "composite": latest.get("composite"),
        "channels": latest.get("channels"),
        "receipts": evidence,
        "receipts_date": receipts.get("date"),
    }


def lint(brief: str | None) -> str | None:
    """None for any brief that crosses into prediction; the payload
    carries the gap honestly instead of a softened rewrite."""
    if brief is None or BANNED.search(brief):
        return None
    return brief


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[daily_brief] ANTHROPIC_API_KEY not set; no brief today "
              "(fail-closed by design)")
        return

    # Imported here so tests and keyless environments never need it.
    import anthropic

    system_prompt, prompt_version = load_prompt()
    context = build_context()
    if not context.get("date"):
        print("[daily_brief] latest.json missing or dateless; skipping")
        return

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": json.dumps(context, sort_keys=True)}],
    )
    if response.stop_reason == "refusal":
        # Fail closed: no brief beats a rerouted one nobody reviewed.
        print("[daily_brief] model refused; no brief today")
        return
    text = next(b.text for b in response.content if b.type == "text")
    briefs = json.loads(text)

    channels = {ch: lint(briefs.get("channels", {}).get(ch)) for ch in CHANNELS}
    dropped = sorted(ch for ch, v in channels.items() if v is None)
    payload = {
        "_meta": {
            "what": (
                "Machine-written daily brief per channel plus a composite "
                "line, generated from the payloads this site already "
                "publishes. Written by a language model, not the author; "
                "measurement language enforced by prompt and lint."
            ),
            "voice": f"machine-written ({MODEL}); never the author's voice",
            "model": MODEL,
            "prompt_version": prompt_version,
            "lint_dropped": dropped,
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "date": context["date"],
        "composite": lint(briefs.get("composite")),
        "channels": channels,
    }
    out = SITE_DATA / "daily_brief.json"
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"[daily_brief] wrote {out.name} for {context['date']} "
          f"({len(CHANNELS) - len(dropped)}/{len(CHANNELS)} channels; "
          f"lint dropped: {dropped or 'none'})")


if __name__ == "__main__":
    main()
