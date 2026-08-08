"""Ask IGRM, v0: every registered question, pre-answered and published.

The evidence-locked assistant (src/evidence_assistant.py, design/
evidence_locked_assistant.md) answers a registered question space with
deterministic text whose every value is re-verified against source
bytes at render time. Its design doc forbids a public endpoint until
ten launch conditions hold. This module is the v0 that needs none of
them: the full registered question set is answered AT BUILD TIME on the
committed payloads, and the answers -- with their evidence ledgers and
their refusals -- are published as one static payload a page can
render. No model, no backend, no key, no user input ever touches the
renderer. The reader gets the ask-anything surface; the trust boundary
stays exactly where a downloaded JSON's is.

Refusals are part of the product: the payload publishes what the
assistant declines to answer (forecasts, superiority, advice) with its
stable refusal codes, because a reader who sees the refusal behavior
can trust the answer behavior.

  python -m src.assistant_answers          write docs/data/assistant_answers.json
  python -m src.assistant_answers --check  build and verify, write nothing
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src import evidence_assistant as ea

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"

CHANNEL_LABELS = {
    "pakistan_west": "Pakistan",
    "china_east": "China",
    "gulf_energy": "Gulf energy",
    "us_trade": "US trade",
    "shipping": "shipping",
}

def _questions() -> list[str]:
    """The registered question space, enumerated. The planner is the
    authority on what each phrasing means; this list only has to cover
    every intent it supports, plus the refusals a reader should see."""
    qs: list[str] = []
    for label in CHANNEL_LABELS.values():
        qs.append(f"Why is the current {label} score here?")
        qs.append(f"Show {label} evidence")
    labels = list(CHANNEL_LABELS.values())
    for i, a in enumerate(labels):
        for b in labels[i + 1:]:
            qs.append(f"Compare {a} versus {b}")
    qs += [
        # Published refusals: the reader sees what the assistant will
        # not do, in its own stable words.
        "Will the index rise tomorrow?",
        "Should I hedge my portfolio against this?",
        "Is IGRM better than the GPR index?",
    ]
    return qs


def build() -> dict[str, Any]:
    answers: list[dict[str, Any]] = []
    n_answered = n_refused = 0
    for q in _questions():
        a = ea.answer_question(q)
        if a.status == "answered":
            n_answered += 1
        else:
            n_refused += 1
        answers.append({"question": q, **a.to_dict()})
    latest = json.loads((SITE_DATA / "latest.json").read_text(encoding="utf-8"))
    receipts = json.loads(
        (SITE_DATA / "receipts.json").read_text(encoding="utf-8"))
    state = {
        "score_date": latest["date"],
        "receipts_date": receipts["date"],
        "aligned": latest["date"] == receipts["date"],
    }

    if n_answered == 0:
        raise SystemExit(
            "[ask] every registered question refused; the committed "
            "payloads are missing or incoherent and publishing an "
            "all-refusal answer set would look like a product outage "
            "with no red anywhere")
    return {"answers": answers, "data_state": state,
            "n_answered": n_answered, "n_refused": n_refused}


def main() -> None:
    check = "--check" in sys.argv
    built = build()

    from src import stamp_meta
    payload = {
        "_meta": {
            **stamp_meta.universal_fields("assistant_answers.json"),
            "what": (
                "The evidence-locked assistant's registered question "
                "space, answered at build time on the committed payloads "
                "and published with each answer's full evidence ledger. "
                "Every value in every sentence was re-verified against "
                "its source bytes (hash, pointer, type, unit, date) by "
                "src/evidence_assistant.py before publication; a "
                "verification failure publishes as a stable refusal, "
                "never as prose. No language model wrote or can write "
                "any of this text."),
            "refusals_are_the_product_too": (
                "Questions the assistant declines -- forecasts, advice, "
                "superiority -- are published with their refusal codes, "
                "because the refusal behavior is the reason to trust "
                "the answer behavior."),
            "data_state": {
                **built["data_state"],
                "why_it_matters": (
                    "A current-score question joins today's score to the "
                    "receipt headlines for the same completed news day. "
                    "When those two dates differ the assistant refuses "
                    "rather than join across days -- the exact error that "
                    "withdrew the machine-written brief. The nightly lane "
                    "realigns them; no answer is edited to paper over the "
                    "gap."),
            },
            "n_questions": built["n_answered"] + built["n_refused"],
            "n_answered": built["n_answered"],
            "n_refused": built["n_refused"],
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "answers": built["answers"],
    }
    if not check:
        (SITE_DATA / "assistant_answers.json").write_text(
            json.dumps(payload, indent=1), encoding="utf-8")
    print(f"[ask] {built['n_answered']} answered, {built['n_refused']} "
          f"refused of {len(built['answers'])} registered questions"
          + (" (check only)" if check else ""))


if __name__ == "__main__":
    main()
