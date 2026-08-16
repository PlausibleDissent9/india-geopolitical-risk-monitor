"""Emit canonical entity records that cite real evidence.

The schema will not let an entity declare an identifier without a
non-empty evidence_ids, which is the rule that forced evidence to be
emitted first. This module is the other half: entities whose every
identifier points at evidence items that actually exist.

WHICH ENTITIES, AND WHY NOT INDIA
The obvious first entity is India. It is also the one this module must
NOT emit, because nothing in the evidence store supports it. Asserting
that India's ISO 3166 code is IND requires an evidence item recording
that fact, and IGRM holds no such item -- only news articles. Emitting
India anyway would mean citing an article about a border incident as
proof of a country code, which is the kind of plausible nonsense a
citation graph exists to make impossible.

What the evidence DOES support is publishers. Every emitted evidence item
carries a domain, observed by the receipt lane on a stated day. That
supports "a publisher operates at this domain" and nothing more, so these
entities are emitted as `provisional` with a dns identifier and no
claimed jurisdiction, parentage or geometry. A later source that
establishes legal identity can supersede them; the lifecycle field exists
for exactly that.

    python -m src.entity_emitter --check
    python -m src.entity_emitter --write DIR
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, NoReturn

from src import canonical_objects, evidence_emitter

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0.0"
EMITTER_ID = "sys:igrm.entity.emitter.publisher.v1"
METHOD_ID = "mth:publisher.domain_observation"
METHOD_VERSION = "1.0.0"
DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$")


class EntityEmitterError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise EntityEmitterError(code, detail)


def _method_block(run_id: str) -> dict[str, Any]:
    return {
        "method_id": METHOD_ID,
        "version": METHOD_VERSION,
        "implementation_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "run_id": run_id,
    }


def _entity_id(domain: str) -> str:
    return "ent:publisher." + hashlib.sha256(domain.encode()).hexdigest()[:32]


def build_records() -> list[dict[str, Any]]:
    """One provisional publisher entity per domain, citing its evidence."""
    payload = json.loads(
        (ROOT / "docs/data/receipt_identity.json").read_text(encoding="utf-8")
    )
    evidence = evidence_emitter.build_records()
    by_url = {record["source_record_id"]: record for record in evidence}

    # domain -> the evidence items that observed it
    observed: dict[str, list[str]] = defaultdict(list)
    earliest: dict[str, str] = {}
    for block in payload.get("channels", {}).values():
        if block.get("state") != "available":
            continue
        for article in block.get("articles", []):
            domain = str(article.get("domain", "")).lower()
            evidence_record = by_url.get(article.get("url"))
            if evidence_record is None:
                # Every article must have produced an evidence item. If one
                # did not, the two emitters disagree and neither result can
                # be trusted; refuse rather than emit a partial universe.
                _fail("entity_evidence_missing_for_article", str(article.get("url")))
            if not DOMAIN_RE.match(domain):
                _fail("entity_domain_invalid", domain)
            observed[domain].append(evidence_record["evidence_id"])
            day = evidence_record["effective_start"][:10]
            earliest[domain] = min(earliest.get(domain, day), day)

    if not observed:
        _fail("entity_no_evidenced_domains")

    records: list[dict[str, Any]] = []
    for domain in sorted(observed):
        evidence_ids = sorted(set(observed[domain]))
        record: dict[str, Any] = {
            "object_type": "entity",
            "schema_version": SCHEMA_VERSION,
            "entity_id": _entity_id(domain),
            "lifecycle": {"revision": 1, "state": "active",
                          "supersedes_id": None, "superseded_by": None,
                          "correction_id": None},
            "entity_type": "organization",
            "canonical_name": domain,
            "aliases": [],
            "identifiers": [{
                "scheme": "dns",
                "value": domain,
                # The first day evidence observed this domain. Not the day
                # the publisher was founded, which nothing here knows.
                "effective_start": earliest[domain],
                "effective_end": None,
                "evidence_ids": evidence_ids,
            }],
            "parent_entity_ids": [],
            # Deliberately empty. A domain does not establish jurisdiction,
            # and guessing one from a country-code suffix would be inference
            # dressed as a record.
            "jurisdiction_entity_ids": [],
            # The schema will not accept a null here: absence must be
            # STATED. A publisher observed only at a domain has no
            # location this evidence supports, so it says so explicitly.
            "geometry": {
                "artifact_path": None,
                "artifact_sha256": None,
                "geometry_type": "none",
                "precision": "not_applicable",
            },
            "effective_start": earliest[domain],
            "effective_end": None,
            # provisional, never authoritative: this says a publisher was
            # observed at a domain, not that its legal identity is settled.
            "identity_status": "provisional",
            "provenance": {
                "created_at": payload["generated_at"],
                "created_by": EMITTER_ID,
                "reviewed_by": [],
                "adjudication_status": "unreviewed",
                "source_ids": [evidence_emitter.SOURCE_ID],
                "evidence_ids": evidence_ids,
                "method": _method_block(
                    f"run:publisher_entities.{payload['target_date']}"
                ),
            },
        }
        records.append(canonical_objects.seal_record(record))
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--write", type=Path)
    args = parser.parse_args(argv)
    try:
        records = build_records()
    except (EntityEmitterError, evidence_emitter.EvidenceEmitterError) as exc:
        print(json.dumps({"refusal": exc.code, "detail": exc.detail}), file=sys.stderr)
        return 1
    if args.check:
        print(json.dumps({"emitted": len(records),
                          "names": [r["canonical_name"] for r in records]}))
        return 0
    args.write.mkdir(parents=True, exist_ok=True)
    for record in records:
        (args.write / f"{record['entity_id']}.json").write_text(
            json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps({"written": len(records), "directory": str(args.write)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
