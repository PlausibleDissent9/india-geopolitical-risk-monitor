"""Emit canonical evidence_item records from the published receipt identity.

The canonical graph is evidence-first by construction: an entity may not
even declare an identifier without citing an evidence item, an event needs
evidence_links, an exposure edge needs evidence_ids. So the first emitter
has to produce evidence, and it has to produce it from something IGRM
already holds signed rights for rather than from something convenient.

docs/data/receipt_identity.json is that source. Its articles are exactly
title, url and domain -- no body, no snippet -- published under the
gdelt_doc_api decision whose permitted uses include publish_extract, and
already public. Emitting them as evidence items adds no new rights
exposure: it re-describes bytes the site already serves.

DENY BY DEFAULT. This module reads the rights registry at emit time and
refuses unless the source row is approved and actually permits the use it
is about to claim. It never widens a right, never infers one, and never
emits from an unavailable channel. A channel the lane refused stays
refused here: an unavailable channel has no articles, and inventing an
evidence item for it would manufacture evidence, which is the one thing
this graph exists to prevent.

    python -m src.evidence_emitter --check     # emit and validate, write nothing
    python -m src.evidence_emitter --write DIR # emit sealed records to DIR
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, NoReturn

from src import canonical_objects

ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = ROOT / "docs/data/receipt_identity.json"
RIGHTS_PATH = ROOT / "governance/source_rights_registry.json"
SOURCE_ID = "gdelt_doc_api"
REQUIRED_USE = "publish_extract"
SCHEMA_VERSION = "1.0.0"
EMITTER_ID = "sys:igrm.evidence.emitter.receipt_identity.v1"
METHOD_ID = "mth:receipt_identity.article_extract"
METHOD_VERSION = "1.0.0"


class EvidenceEmitterError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise EvidenceEmitterError(code, detail)


def _approved_row() -> dict[str, Any]:
    """The rights row, or a refusal. Read at emit time, never cached."""
    try:
        registry = json.loads(RIGHTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _fail("evidence_rights_registry_unreadable")
    rows = [r for r in registry.get("sources", []) if r.get("source_id") == SOURCE_ID]
    if len(rows) != 1:
        _fail("evidence_rights_row_not_unique", SOURCE_ID)
    row = rows[0]
    if row.get("decision_state") != "approved":
        _fail("evidence_source_not_approved", str(row.get("decision_state")))
    if REQUIRED_USE not in (row.get("permitted_uses") or []):
        # The use is claimed on every record emitted; if the decision does
        # not grant it, no record may claim it.
        _fail("evidence_use_not_permitted", REQUIRED_USE)
    return row


def _payload() -> dict[str, Any]:
    try:
        return json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _fail("evidence_receipt_payload_unreadable")


def _method_block(run_id: str) -> dict[str, Any]:
    """Bind every record to the exact bytes of the code that produced it.

    implementation_sha256 is this module's own digest. If the emitter
    changes, records made by the old one remain attributable to it, and a
    reader can tell two records apart by the code that wrote them rather
    than by trusting a version string somebody remembered to bump.
    """
    return {
        "method_id": METHOD_ID,
        "version": METHOD_VERSION,
        "implementation_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "run_id": run_id,
    }


def _evidence_id(url: str) -> str:
    return "evd:receipt." + hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def build_records() -> list[dict[str, Any]]:
    """One sealed evidence_item per published article. Refusals stay refused."""
    row = _approved_row()
    payload = _payload()
    target = payload.get("target_date")
    generated_at = payload.get("generated_at")
    if not isinstance(target, str) or not isinstance(generated_at, str):
        _fail("evidence_receipt_payload_invalid")

    records: list[dict[str, Any]] = []
    for channel, block in sorted(payload.get("channels", {}).items()):
        if block.get("state") != "available":
            continue  # an unavailable channel has no evidence, and gets none
        for article in block.get("articles", []):
            url = article.get("url")
            title = article.get("title")
            domain = article.get("domain")
            if not (isinstance(url, str) and isinstance(title, str)
                    and isinstance(domain, str)):
                _fail("evidence_article_shape_invalid", channel)
            record: dict[str, Any] = {
                "object_type": "evidence_item",
                "schema_version": SCHEMA_VERSION,
                "evidence_id": _evidence_id(url),
                "lifecycle": {"revision": 1, "state": "active",
                              "supersedes_id": None, "superseded_by": None,
                              "correction_id": None},
                "source_id": SOURCE_ID,
                "source_record_id": url,
                "retrieval_id": f"ret:receipt_identity.{target}.{channel}",
                "evidence_type": "news_article",
                "title": title,
                "publisher_entity_id": None,
                "authors": [],
                "language": "en",
                "published_at": None,
                "observed_at": generated_at,
                # The measured UTC day the receipt lane targeted, as an
                # instant: the schema wants a datetime here, and midnight
                # UTC of the target day is the honest reading of "the day
                # this evidence describes".
                "effective_start": f"{target}T00:00:00Z",
                "effective_end": None,
                "retrieved_at": generated_at,
                "geography_entity_ids": [],
                "public_url": url,
                "artifact_path": None,
                # No body is held, so the content digest is over the exact
                # identity triple the lane publishes -- never over prose we
                # do not have and must not imply we have.
                "content_sha256": hashlib.sha256(
                    json.dumps({"title": title, "url": url, "domain": domain},
                               sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
                "artifact_sha256": None,
                # NOT public_extract. The schema requires anything claiming
                # full_bytes or public_extract to carry an artifact_path and
                # artifact_sha256, because those claim we HOLD the content.
                # This lane holds no article body at all -- only the
                # title/url/domain triple -- so hash_metadata_only is the
                # true statement. The schema refused the overclaim.
                "content_availability": "hash_metadata_only",
                "rights_use": REQUIRED_USE,
                "rights_decision_id": row.get("decision_id"),
                "privacy_class": "public",
                "verification_status": "single_source",
                "extraction_method": "provider_api",
                "provenance": {
                    "created_at": generated_at,
                    "created_by": EMITTER_ID,
                    "reviewed_by": [],
                    "adjudication_status": "unreviewed",
                    "source_ids": [SOURCE_ID],
                    "evidence_ids": [],
                    "method": _method_block(
                        f"run:receipt_identity.{target}"
                    ),
                },
            }
            records.append(canonical_objects.seal_record(record))
    records.sort(key=lambda r: r["evidence_id"])
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--write", type=Path)
    args = parser.parse_args(argv)
    try:
        records = build_records()
    except EvidenceEmitterError as exc:
        print(json.dumps({"refusal": exc.code, "detail": exc.detail}), file=sys.stderr)
        return 1
    if args.check:
        print(json.dumps({"emitted": len(records),
                          "evidence_ids": [r["evidence_id"] for r in records[:3]]}))
        return 0
    args.write.mkdir(parents=True, exist_ok=True)
    for record in records:
        (args.write / f"{record['evidence_id']}.json").write_text(
            json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps({"written": len(records), "directory": str(args.write)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
