"""Build the evidence-bounded IGRM World State Matrix.

The matrix is a coverage product, not a world score.  It enumerates every
registered map member against every country-level Atlas layer and makes an
unavailable cell visible until a real, rights-cleared public observation exists.
Only the already-published India-partner event context is populated in v1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, NoReturn, cast

from src import evolution_engine

ROOT = Path(__file__).resolve().parents[1]
WORLD_PATH = ROOT / "docs" / "geo" / "world.json"
RELATIONS_PATH = ROOT / "docs" / "data" / "map_relations.json"
LAYERS_PATH = ROOT / "governance" / "global_atlas_layers.json"
OUTPUT_PATH = ROOT / "docs" / "data" / "world_state.json"

OBSERVED = "observed"
MEMBER_UNAVAILABLE = "unavailable_member_not_observed"
LAYER_UNAVAILABLE = "unavailable_layer_not_published"


class WorldStateError(ValueError):
    """Stable refusal raised when the matrix cannot be built truthfully."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise WorldStateError(code)


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _fail("json_duplicate_key")
        value[key] = item
    return value


def _read(path: Path, code: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw,
            object_pairs_hook=_object,
            parse_constant=lambda _: _fail("json_non_finite"),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorldStateError(code) from exc
    if not isinstance(value, dict):
        _fail(code)
    return cast(dict[str, Any], value), hashlib.sha256(raw).hexdigest()


def _number(value: object, code: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(code)
    if not math.isfinite(value):
        _fail(code)
    return value


def _day(value: object, code: str) -> str:
    if not isinstance(value, str):
        _fail(code)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _fail(code)
    if parsed.isoformat() != value:
        _fail(code)
    return value


def _partner_observation(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "name",
        "n",
        "conflict_share",
        "goldstein_mean",
        "recent_n",
        "recent_conflict_share",
    }:
        _fail("partner_observation_shape_invalid")
    if not isinstance(value["name"], str) or not value["name"].strip():
        _fail("partner_name_invalid")
    n = _number(value["n"], "partner_measure_invalid")
    recent_n = _number(value["recent_n"], "partner_measure_invalid")
    conflict = _number(value["conflict_share"], "partner_measure_invalid")
    raw_recent_conflict = value["recent_conflict_share"]
    recent_conflict = (
        None
        if raw_recent_conflict is None
        else _number(raw_recent_conflict, "partner_measure_invalid")
    )
    goldstein = _number(value["goldstein_mean"], "partner_measure_invalid")
    if (
        not isinstance(n, int)
        or not isinstance(recent_n, int)
        or n < 0
        or recent_n < 0
        or not 0 <= conflict <= 1
        or (recent_conflict is not None and not 0 <= recent_conflict <= 1)
        or (recent_n == 0 and recent_conflict is not None)
        or (recent_conflict is None and recent_n != 0)
    ):
        _fail("partner_measure_invalid")
    return {
        "source_partner_name": value["name"],
        "event_count_all_time": n,
        "conflict_share_all_time": conflict,
        "goldstein_mean_all_time": goldstein,
        "event_count_recent_window": recent_n,
        "conflict_share_recent_window": recent_conflict,
    }


def build() -> dict[str, Any]:
    """Return the exact global denominator and currently supportable cells."""

    # Validate the immutable engine/layer contracts without reading generated
    # catalogs or reports.  The matrix must remain rebuildable when its prior
    # public output is absent.
    evolution_engine.validate_static_contracts()
    world, world_sha = _read(WORLD_PATH, "world_geometry_unreadable")
    relations, _ = _read(RELATIONS_PATH, "map_relations_unreadable")
    layers, layers_sha = _read(LAYERS_PATH, "layer_registry_unreadable")

    countries = world.get("countries")
    partners = relations.get("partners")
    layer_rows = layers.get("layers")
    if not isinstance(countries, dict) or not countries:
        _fail("world_members_invalid")
    if not isinstance(partners, dict) or not partners:
        _fail("partner_members_invalid")
    if not isinstance(layer_rows, list) or not layer_rows:
        _fail("layer_rows_invalid")
    if not set(partners).issubset(countries):
        _fail("partner_outside_world_denominator")
    if relations.get("_meta", {}).get("partial") is not False:
        _fail("partner_payload_partial")
    relation_meta = relations.get("_meta")
    if not isinstance(relation_meta, dict):
        _fail("partner_metadata_invalid")
    observation_vintage = _day(
        relation_meta.get("generated"), "partner_observation_vintage_invalid"
    )
    contract_effective = _day(
        layers.get("effective"), "layer_registry_effective_invalid"
    )

    country_layers = [
        cast(dict[str, Any], row)
        for row in layer_rows
        if isinstance(row, dict) and row.get("country_level") is True
    ]
    if len(country_layers) != 14:
        _fail("country_layer_denominator_invalid")
    layer_ids = [cast(str, row["layer_id"]) for row in country_layers]
    if len(layer_ids) != len(set(layer_ids)):
        _fail("country_layer_id_duplicate")
    published = [
        row for row in country_layers if str(row["current_state"]).startswith("published_")
    ]
    if [row["layer_id"] for row in published] != ["india_partner_event_context"]:
        _fail("published_country_layer_set_invalid")

    observations = {
        member_id: _partner_observation(value)
        for member_id, value in sorted(partners.items())
    }
    members: list[dict[str, Any]] = []
    for member_id, geometry in sorted(countries.items()):
        if (
            not isinstance(member_id, str)
            or not isinstance(geometry, dict)
            or not isinstance(geometry.get("name"), str)
        ):
            _fail("world_member_invalid")
        states: dict[str, str] = {}
        for row in country_layers:
            layer_id = cast(str, row["layer_id"])
            if layer_id == "india_partner_event_context":
                states[layer_id] = (
                    OBSERVED if member_id in observations else MEMBER_UNAVAILABLE
                )
            else:
                states[layer_id] = LAYER_UNAVAILABLE
        members.append(
            {
                "area_id": member_id,
                "name": geometry["name"],
                "layer_states": states,
            }
        )

    layer_index: list[dict[str, Any]] = []
    for row in country_layers:
        layer_id = cast(str, row["layer_id"])
        observed_count = len(observations) if layer_id == "india_partner_event_context" else 0
        layer_index.append(
            {
                "layer_id": layer_id,
                "label": row["label"],
                "family": row["family"],
                "kind": row["kind"],
                "construct": row["construct"],
                "registry_state": row["current_state"],
                "index_state": row["index_state"],
                "observed_members": observed_count,
                "unavailable_members": len(countries) - observed_count,
                "denominator_members": len(countries),
                "coverage_share": round(observed_count / len(countries), 6),
                "source_payload": row["source_payload"],
                "missingness_rule": row["missingness_rule"],
                "prohibited_interpretation": row["prohibited_interpretation"],
                "safety_rule": row["safety_rule"],
            }
        )

    state_projection = [
        [member["area_id"], member["layer_states"]] for member in members
    ]
    return {
        "_meta": {
            "schema_version": "1.0.0",
            "date": observation_vintage,
            "generated": f"{observation_vintage}T00:00:00Z",
            "contract_effective": contract_effective,
            "partial": False,
            "partial_definition": (
                "False means every registered geometry-layer cell is represented. It does "
                "not mean every cell carries an observation."
            ),
            "license": "CC BY 4.0",
            "citation": (
                "Krishna, Ishan (2026). IGRM World State Matrix. "
                "https://igrm.in/data/world_state.json"
            ),
            "codebook": "https://igrm.in/codebook.html",
            "source": "https://igrm.in/data/world_state.json",
            "what": (
                "Complete-country/area Atlas coverage matrix. Every registered geometry "
                "appears for every country-level layer; unavailable cells remain explicit. "
                "This is not a world risk score or a claim of complete measurement."
            ),
            "observation_vintage": observation_vintage,
            "input_sha256": {
                "world_geometry": world_sha,
                "map_relations_observation_set": evolution_engine.canonical_sha256(
                    {
                        "generated": relations["_meta"]["generated"],
                        "recent_window_days": relations["_meta"].get(
                            "recent_window_days"
                        ),
                        "partners": partners,
                    }
                ),
                "global_layer_registry": layers_sha,
            },
            "matrix_state_sha256": evolution_engine.canonical_sha256(state_projection),
        },
        "denominator": {
            "geometry_members": len(countries),
            "country_level_layers": len(country_layers),
            "cells": len(countries) * len(country_layers),
            "geometry_policy": layers["universe"],
            "single_world_score": "prohibited",
            "status_vocabulary": {
                OBSERVED: "A real value is present in the named published source payload.",
                MEMBER_UNAVAILABLE: (
                    "The layer is published, but no observation exists for this member."
                ),
                LAYER_UNAVAILABLE: (
                    "The layer is not yet a published observation layer for any member."
                ),
            },
        },
        "layers": layer_index,
        "members": members,
        "observations": {"india_partner_event_context": observations},
        "non_country_layers": [
            {
                "layer_id": row["layer_id"],
                "label": row["label"],
                "current_state": row["current_state"],
                "source_payload": row["source_payload"],
                "coverage_note": row["missingness_rule"],
            }
            for row in layer_rows
            if isinstance(row, dict) and row.get("country_level") is False
        ],
    }


def _encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode(
        "utf-8"
    )


def write(path: Path = OUTPUT_PATH) -> None:
    content = _encoded(build())
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def check(path: Path = OUTPUT_PATH) -> None:
    try:
        current = path.read_bytes()
    except OSError as exc:
        raise WorldStateError("world_state_report_missing") from exc
    if current != _encoded(build()):
        _fail("world_state_report_stale")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        write()


if __name__ == "__main__":
    main()
