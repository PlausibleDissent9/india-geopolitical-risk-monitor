"""Assemble an unsigned canonical release manifest over emitted objects.

The release is the manifest a founder signs and the compiler consumes. It
does NOT require events: canonical-release.schema.json sets every
per-type count minimum to zero and asks only that the objects array be
non-empty. A release of evidence items and entities alone is therefore
valid, and honest -- it says the graph contains what it contains.

This module stops one step short of a release: it writes the manifest
with release_signer_id and release_signature_path left for the ceremony,
because signing is the founder's and because a manifest that filled those
in itself would be asserting an authority it does not have.

    python -m src.release_assembler --check
    python -m src.release_assembler --write DIR
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, NoReturn

from src import (
    canonical_objects,
    entity_emitter,
    evidence_emitter,
    universe_emitter,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0.0"
OBJECT_TYPES = ("evidence_item", "entity", "event", "exposure_edge", "universe_release")
REGISTRIES = {
    "schema_registry_sha256": "governance/canonical_schema_registry.json",
    "method_registry_sha256": "governance/canonical_method_registry.json",
    "rights_registry_sha256": "governance/source_rights_registry.json",
    "rights_signers_sha256": "governance/rights_signers.json",
    "release_signers_sha256": "governance/release_signers.json",
}


class ReleaseAssemblerError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise ReleaseAssemblerError(code, detail)


def _digest(relative: str) -> str:
    path = ROOT / relative
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        _fail("release_registry_unreadable", relative)


def _rights_snapshot(source_ids: list[str]) -> list[dict[str, Any]]:
    registry = json.loads(
        (ROOT / REGISTRIES["rights_registry_sha256"]).read_text(encoding="utf-8")
    )
    rows = {r["source_id"]: r for r in registry.get("sources", [])}
    snapshot = []
    for source_id in source_ids:
        row = rows.get(source_id)
        if row is None or row.get("decision_state") != "approved":
            _fail("release_source_not_approved", source_id)
        snapshot.append({
            "source_id": source_id,
            "decision_id": row["decision_id"],
            "decision_artifact_sha256": row["decision_artifact_sha256"],
            "signer_id": row["signer_id"],
            "independence_group": row["independence_group"],
            "authority_class": row["authority_class"],
        })
    return snapshot


def build_manifest(object_dir: str = "canonical") -> dict[str, Any]:
    """One unsigned manifest over every emitted object, sealed but unsigned."""
    evidence = evidence_emitter.build_records()
    entities = entity_emitter.build_records()
    universe = universe_emitter.build_record()
    emitted: list[tuple[str, dict[str, Any]]] = (
        [("evidence_item", r) for r in evidence]
        + [("entity", r) for r in entities]
        # The universe release states the graph's own boundaries, so a
        # reader learns what was in scope from the release rather than
        # inferring it from what happens to be present.
        + [("universe_release", universe)]
    )
    if not emitted:
        # objects has minItems 1; an empty release would be a claim that the
        # graph exists while containing nothing.
        _fail("release_has_no_objects")

    objects: list[dict[str, Any]] = []
    counts = dict.fromkeys(OBJECT_TYPES, 0)
    for object_type, record in emitted:
        identity = record[{
            "evidence_item": "evidence_id",
            "entity": "entity_id",
            "universe_release": "universe_release_id",
        }[object_type]]
        raw = (json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False)
               + "\n").encode("utf-8")
        objects.append({
            "object_type": object_type,
            "object_id": identity,
            "path": f"{object_dir}/{object_type}/{identity}.json",
            # The digest of the file as this assembler writes it, so a
            # verifier reading the committed bytes lands on the same value.
            "file_sha256": hashlib.sha256(raw).hexdigest(),
            "record_sha256": record["record_sha256"],
        })
        counts[object_type] += 1
    objects.sort(key=lambda o: (o["object_type"], o["object_id"]))

    observed = {r["observed_at"] for r in evidence}
    if len(observed) != 1:
        _fail("release_observation_instant_ambiguous", str(sorted(observed)))
    generated_at = observed.pop()

    manifest: dict[str, Any] = {
        "object_type": "canonical_release",
        "schema_version": SCHEMA_VERSION,
        "release_id": "rel:igrm.receipt_identity."
                      + hashlib.sha256(
                          "".join(o["record_sha256"] for o in objects).encode()
                      ).hexdigest()[:24],
        "generated_at": generated_at,
        "effective_date": generated_at[:10],
        **{key: _digest(rel) for key, rel in REGISTRIES.items()},
        # Left for the ceremony. Filling these in here would assert an
        # authority this process does not hold, and canonical_objects
        # refuses an unenrolled signer anyway.
        "release_signer_id": None,
        "release_signature_path": None,
        # One row per source, copied from the signed registry rather than
        # summarised: the release must carry the exact decision, artifact
        # digest, signer and independence group that authorised each source,
        # so a reader can check the rights without trusting this manifest.
        "rights_snapshot": _rights_snapshot(
            sorted({r["source_id"] for r in evidence})
        ),
        "objects": objects,
        "counts": counts,
    }
    return canonical_objects.seal_record(manifest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--write", type=Path)
    args = parser.parse_args(argv)
    try:
        manifest = build_manifest()
    except (ReleaseAssemblerError, entity_emitter.EntityEmitterError,
            evidence_emitter.EvidenceEmitterError) as exc:
        print(json.dumps({"refusal": exc.code, "detail": exc.detail}), file=sys.stderr)
        return 1
    if args.check:
        print(json.dumps({
            "release_id": manifest["release_id"],
            "counts": manifest["counts"],
            "signed": manifest["release_signer_id"] is not None,
        }))
        return 0
    args.write.mkdir(parents=True, exist_ok=True)
    (args.write / "canonical_release.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    for object_type, records, key in (
        ("evidence_item", evidence_emitter.build_records(), "evidence_id"),
        ("entity", entity_emitter.build_records(), "entity_id"),
    ):
        directory = args.write / object_type
        directory.mkdir(parents=True, exist_ok=True)
        for record in records:
            (directory / f"{record[key]}.json").write_text(
                json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    print(json.dumps({"written": str(args.write), "objects": len(manifest["objects"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
