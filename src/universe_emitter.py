"""Emit the universe_release that states this graph's own boundaries.

A universe release is the object that says what is in scope and why, and
what is out. It exists here while events do not because its inclusion
rule is MECHANICAL -- a domain either appeared in an available channel or
it did not -- whereas classifying a headline into an event class needs a
registered coding rule nobody has written.

The rule, its implementation digest and its documentation are all named
in the record, so a reader can check the membership rather than trust it.
The prose lives in governance/universes/publisher_observation_universe.md
and states the denominator this universe supports and the three things it
does not.

    python -m src.universe_emitter --check
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, NoReturn

from src import canonical_objects, entity_emitter, evidence_emitter

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0.0"
UNIVERSE_ID = "uni:igrm.publisher.receipt_observation"
RULE_ID = "rule:publisher.observed_in_available_channel"
RULE_VERSION = "1.0.0"
IMPLEMENTATION = "src/entity_emitter.py"
DOCUMENTATION = "governance/universes/publisher_observation_universe.md"
FRAME = "docs/data/receipt_identity.json"
EMITTER_ID = "sys:igrm.universe.emitter.publisher.v1"
METHOD_ID = "mth:publisher.universe_release"


class UniverseEmitterError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise UniverseEmitterError(code, detail)


def _sha(relative: str) -> str:
    try:
        return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    except OSError:
        _fail("universe_artifact_unreadable", relative)


def build_record() -> dict[str, Any]:
    entities = entity_emitter.build_records()
    evidence = evidence_emitter.build_records()
    if not entities:
        # total_eligible has minimum 1: a universe with nothing eligible is
        # not an empty universe, it is a broken one.
        _fail("universe_has_no_eligible_members")
    payload = json.loads((ROOT / FRAME).read_text(encoding="utf-8"))
    reference_date = payload["target_date"]

    members = [
        {
            "entity_id": entity["entity_id"],
            "status": "included",
            # Every member states WHY it is a member, so membership can be
            # audited one row at a time instead of taken on trust.
            "reason_code": "observed_in_available_channel",
            "assessed_on": reference_date,
        }
        for entity in entities
    ]
    members.sort(key=lambda m: m["entity_id"])

    # Everything eligible was included: the rule has no rejection branch,
    # because a domain that fails it never becomes an entity at all. Saying
    # so explicitly is more honest than implying a filter that does not run.
    counts = {
        "total_eligible": len(members),
        "included": len(members),
        "excluded": 0,
        "unmappable": 0,
        "stale": 0,
    }

    unavailable = sorted(
        name for name, block in payload.get("channels", {}).items()
        if block.get("state") != "available"
    )
    record: dict[str, Any] = {
        "object_type": "universe_release",
        "schema_version": SCHEMA_VERSION,
        "universe_release_id": f"unv:publisher.receipt_observation.{reference_date}",
        "lifecycle": {"revision": 1, "state": "active", "supersedes_id": None,
                      "superseded_by": None, "correction_id": None},
        "universe_id": UNIVERSE_ID,
        "version": RULE_VERSION,
        "name": "Publishers observed by the receipt-identity lane",
        "entity_type": "organization",
        "reference_date": reference_date,
        # The denominator is stated in the object, not left to a reader to
        # infer from the member count. It names the channels that were
        # unavailable, because a three-fifths view must say so.
        "denominator_definition": (
            "Domains observed in available receipt-identity channels on "
            f"{reference_date}. Channels unavailable on that date and "
            f"therefore contributing no members: {', '.join(unavailable) or 'none'}. "
            "This supports no claim about share of Indian press, share of "
            "coverage of any topic, or publishers that were not sampled."
        ),
        "inclusion_rule": {
            "rule_id": RULE_ID,
            "version": RULE_VERSION,
            "implementation_path": IMPLEMENTATION,
            "implementation_sha256": _sha(IMPLEMENTATION),
            "documentation_path": DOCUMENTATION,
        },
        "frame_artifact": {
            "path": FRAME,
            "sha256": _sha(FRAME),
            "format": "igrm_universe_frame_v1",
        },
        "source_evidence_ids": sorted(r["evidence_id"] for r in evidence),
        "members": members,
        "counts": counts,
        "provenance": {
            "created_at": payload["generated_at"],
            "created_by": EMITTER_ID,
            "reviewed_by": [],
            "adjudication_status": "unreviewed",
            "source_ids": [evidence_emitter.SOURCE_ID],
            "evidence_ids": sorted(r["evidence_id"] for r in evidence),
            "method": {
                "method_id": METHOD_ID,
                "version": RULE_VERSION,
                "implementation_sha256": hashlib.sha256(
                    Path(__file__).read_bytes()
                ).hexdigest(),
                "run_id": f"run:publisher_universe.{reference_date}",
            },
        },
    }
    return canonical_objects.seal_record(record)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args(argv)
    try:
        record = build_record()
    except (UniverseEmitterError, entity_emitter.EntityEmitterError,
            evidence_emitter.EvidenceEmitterError) as exc:
        print(json.dumps({"refusal": exc.code, "detail": exc.detail}), file=sys.stderr)
        return 1
    print(json.dumps({"universe_release_id": record["universe_release_id"],
                      "counts": record["counts"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
