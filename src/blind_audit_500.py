"""Build and score the frozen 500-article independent-coder audit.

The draw contains 100 items per IGRM channel:

* 75 production document instances sampled uniformly from the exact matched
  document-key frame, estimating the precision of the quantity the index
  actually counts;
* 25 normalized-headline clusters sampled independently from the full cluster
  universe, estimating descriptive story-level precision without letting
  syndication dominate. The two strata may overlap and are never pooled.

The coder sheet reveals the target channel because the registered rubric is
channel-specific. It never reveals the query group, matched phrase, machine
label, source tier, IGRM score, sampling stratum, or any prior human label.

    python -m src.blind_audit_500 --build
    python -m src.blind_audit_500 --score coder_1.csv [coder_2.csv]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.fetch_ngrams import group_specs
from src.receipts_ngrams import channel_doc_keys

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "validation" / "blind_audit_500"
SHEET = PACKAGE / "coder_sheet.csv"
CODER_SHEETS = [PACKAGE / "coder_sheet_c1.csv", PACKAGE / "coder_sheet_c2.csv"]
PILOT = PACKAGE / "pilot_sheet.csv"
KEY = PACKAGE / "sample_key.json"
REGISTRATION = PACKAGE / "registration.json"

SOURCE_FILES = {
    "data/raw/receipt_days/2026-07-27.json": (
        "402a2d6697033dbcf56bf2794ba83fd54f9336da1b40aec1e4ba53dfd18bf3d1"
    ),
    "data/raw/receipt_days/2026-07-28.json": (
        "d3a0603c1c3378e539d41fde66b396970177aea9c8968614269a88bad5c15b98"
    ),
    "data/raw/receipt_days/2026-07-29.json": (
        "cd4405f0f857a4acf612cd1a6554ea539ea28b648f64bb8a4a7d0d72655d0340"
    ),
    "data/raw/receipt_days/2026-07-30.json": (
        "ca8bdf23269e661d9930b28e5568519f1ef36ed975bbc23861686eaa9ff60993"
    ),
    "data/raw/receipt_days/2026-07-31.json": (
        "247ac7ccc6fa55485cfb7cd12d5f698ac7023da82f1f82df018aaf507cfd4ab5"
    ),
    "data/raw/receipt_days/2026-08-01.json": (
        "ef3c5a2a6a67da83734729c04712e4eb974b67eef612faca72f0987b45bde62a"
    ),
    "data/raw/receipt_days/2026-08-02.json": (
        "2bf959eee8330b911b380ae1bd86acf66e0f187b2f1b8d1c24196ff2a6bda203"
    ),
    "data/raw/receipt_days/2026-08-03.json": (
        "631d1a994a951a80b0cf8fe7d0afe42ffb7063081aca7f6006676cc2fb7c188b"
    ),
    "data/raw/receipt_days/2026-08-04.json": (
        "5121c82e703af51a33562271f09fc15f94b55a412dbfd6ab6358e96605607fb2"
    ),
    "data/raw/receipt_days/2026-08-05.json": (
        "e78aeb3bc47b1980b6f05577a87487c72cd53fb1eaa055d28ddb26bd747abd55"
    ),
    "data/raw/receipt_days/2026-08-06.json": (
        "a62ea4343598e3f25efcdf7275a703d5d212bf80bb5705329e96357f4e4d61a8"
    ),
}
PILOT_SOURCE_FILES = {
    "data/raw/receipt_days/2026-08-05-extended.json": (
        "71a681b3e98357b627e73c2de43d390acbe51b469292174a3e7afe2731bf1536"
    ),
    "data/raw/receipt_days/2026-08-06-extended.json": (
        "5145b919d51d2dc30c15a355d37092d60ef3f4a1181b92b4692ae29411226257"
    ),
}
RUBRIC = ROOT / "auditor" / "RUBRIC.md"
RUBRIC_SHA256 = "2f285c9ffbc96d43946dbf9b53cd9fa688c2353be2c05e9df02ab5be8db38d17"
DICTIONARIES = ROOT / "dictionaries.json"
DICTIONARIES_SHA256 = "4f5d3333cad6d7b708c3b7d855f5fcc636b0ef2243f56f8e58def9f754d99b40"
PRODUCTION_MATCHER_FILES = {
    "src/fetch_ngrams.py": "cb9cded6d957f8e31a70c0bd9a7edd99c2ace3e621fdf141da80877e57fd871d",
    "src/receipts_ngrams.py": "9c77cf9b90a226e94a18acece1ddfaefe2a064bbdb6d143e2a236b43b9f61d45",
}

CHANNELS = ["pakistan_west", "china_east", "gulf_energy", "us_trade", "shipping"]
ARTICLE_N = 75
STORY_N = 25
PILOT_N = 4
SEED = "igrm-blind-audit-500-v2-2026-08-07"
FIRM = {"ON", "OFF"}
ALLOWED = FIRM | {"ABSTAIN"}
CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}

SHEET_FIELDS = [
    "audit_id",
    "channel",
    "article_date",
    "title",
    "domain",
    "url",
    "coder_label",
    "coder_confidence",
    "coder_note",
]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _verify(path: Path, expected: str, label: str) -> None:
    observed = _sha256(path.read_bytes())
    if observed != expected:
        raise SystemExit(f"[blind-audit] {label} changed: expected {expected}, got {observed}")


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _date(raw: str) -> str:
    compact = raw.replace("-", "")[:8]
    return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _universe(
    source_files: dict[str, str] = SOURCE_FILES,
) -> dict[str, list[dict[str, str]]]:
    _verify(RUBRIC, RUBRIC_SHA256, "rubric")
    _verify(DICTIONARIES, DICTIONARIES_SHA256, "dictionaries")
    for relpath, expected in PRODUCTION_MATCHER_FILES.items():
        _verify(ROOT / relpath, expected, relpath)
    specs = group_specs()
    rows: dict[str, dict[str, dict[str, str]]] = {channel: {} for channel in CHANNELS}
    for relpath, expected in source_files.items():
        path = ROOT / relpath
        _verify(path, expected, relpath)
        payload = json.loads(path.read_text(encoding="utf-8"))
        metadata = payload["meta"]
        corpus = {
            **payload,
            "india": set(payload.get("india") or []),
            "matched": {
                group: set(keys) for group, keys in payload["matched"].items()
            },
        }
        for channel in CHANNELS:
            # This is the exact production numerator: union the channel's
            # phrase groups, then apply the India anchor per document when the
            # frozen specification requires it. Sampling raw phrase matches
            # would audit a different population.
            for key in channel_doc_keys(channel, specs, corpus):
                record = metadata.get(key) or {}
                url = str(record.get("url") or "").strip()
                title = str(record.get("title") or "").strip()
                raw_date = str(record.get("date") or "").strip()
                if not url or not title or len(raw_date.replace("-", "")) < 8:
                    continue
                # Production counts matched document keys, not unique URLs.
                # Preserve every exact counted instance: the same URL may
                # legitimately occur under more than one source document key.
                frame_id = f"{relpath}|{key}"
                rows[channel].setdefault(
                    frame_id,
                    {
                        "frame_id": frame_id,
                        "channel": channel,
                        "article_date": _date(raw_date),
                        "title": title,
                        "domain": _domain(url),
                        "url": url,
                        "source_path": relpath,
                        "source_document_key": key,
                        "source_record_sha256": _sha256(
                            json.dumps(
                                {
                                    "date": _date(raw_date),
                                    "title": title,
                                    "url": url,
                                },
                                sort_keys=True,
                                separators=(",", ":"),
                            ).encode()
                        ),
                        "evidence_identity_sha256": _sha256(
                            json.dumps(
                                {"title": title, "url": url},
                                sort_keys=True,
                                separators=(",", ":"),
                            ).encode()
                        ),
                        "normalized_title": _title_key(title),
                    },
                )
    return {
        channel: sorted(items.values(), key=lambda row: row["frame_id"])
        for channel, items in rows.items()
    }


def build() -> tuple[
    list[dict[str, str]], list[dict[str, str]], dict[str, int], list[dict[str, str]]
]:
    universe = _universe()
    pilot_universe = _universe(PILOT_SOURCE_FILES)
    sheet_rows: list[dict[str, str]] = []
    key_rows: list[dict[str, str]] = []
    pilot_rows: list[dict[str, str]] = []
    counts: dict[str, int] = {}

    for channel in CHANNELS:
        pool = universe[channel]
        if len(pool) < ARTICLE_N:
            raise SystemExit(
                f"[blind-audit] {channel} has only {len(pool)} production document instances"
            )
        counts[channel] = len(pool)
        article_rng = random.Random(f"{SEED}|{channel}|article")
        article_rows = article_rng.sample(pool, ARTICLE_N)
        by_story: dict[str, list[dict[str, str]]] = {}
        for row in pool:
            title_key = row["normalized_title"]
            if not title_key:
                continue
            by_story.setdefault(title_key, []).append(row)
        if len(by_story) < STORY_N:
            raise SystemExit(f"[blind-audit] {channel} has only {len(by_story)} stories")
        story_rng = random.Random(f"{SEED}|{channel}|story")
        story_keys = story_rng.sample(sorted(by_story), STORY_N)
        # Representative selection is deterministic and independent of the
        # article draw. The two independently sampled strata may therefore
        # overlap, which is disclosed and never pooled.
        story_rows = [
            sorted(by_story[key], key=lambda row: row["frame_id"])[0]
            for key in story_keys
        ]

        for stratum, selected in (
            ("article_instance", article_rows),
            ("story_cluster", story_rows),
        ):
            for row in selected:
                audit_id = "A" + _sha256(
                    f"{SEED}|{channel}|{stratum}|{row['frame_id']}".encode()
                )[:15].upper()
                sheet_rows.append(
                    {
                        "audit_id": audit_id,
                        "channel": channel,
                        "article_date": row["article_date"],
                        "title": row["title"],
                        "domain": row["domain"],
                        "url": row["url"],
                        "coder_label": "",
                        "coder_confidence": "",
                        "coder_note": "",
                    }
                )
                key_rows.append(
                    {
                        "audit_id": audit_id,
                        "channel": channel,
                        "stratum": stratum,
                        "source_path": row["source_path"],
                        "source_document_key": row["source_document_key"],
                        "source_record_sha256": row["source_record_sha256"],
                        "evidence_identity_sha256": row[
                            "evidence_identity_sha256"
                        ],
                        "normalized_title_sha256": _sha256(row["normalized_title"].encode()),
                    }
                )

        used_urls = {row["url"] for row in article_rows + story_rows}
        used_titles = {row["normalized_title"] for row in article_rows + story_rows}
        pilot_pool = [
            row
            for row in pilot_universe[channel]
            if row["url"] not in used_urls and row["normalized_title"] not in used_titles
        ]
        if len(pilot_pool) < PILOT_N:
            raise SystemExit(f"[blind-audit] {channel} has only {len(pilot_pool)} pilot items")
        pilot_rng = random.Random(f"{SEED}|{channel}|pilot")
        for row in pilot_rng.sample(pilot_pool, PILOT_N):
            pilot_id = "P" + _sha256(
                f"{SEED}|{channel}|pilot|{row['frame_id']}".encode()
            )[:15].upper()
            pilot_rows.append(
                {
                    "audit_id": pilot_id,
                    "channel": channel,
                    "article_date": row["article_date"],
                    "title": row["title"],
                    "domain": row["domain"],
                    "url": row["url"],
                    "coder_label": "",
                    "coder_confidence": "",
                    "coder_note": "",
                }
            )

    order_rng = random.Random(f"{SEED}|sheet-order")
    order_rng.shuffle(sheet_rows)
    order = {row["audit_id"]: index for index, row in enumerate(sheet_rows)}
    key_rows.sort(key=lambda row: order[row["audit_id"]])
    pilot_rng = random.Random(f"{SEED}|pilot-order")
    pilot_rng.shuffle(pilot_rows)
    return sheet_rows, key_rows, counts, pilot_rows


def write_package() -> None:
    sheet_rows, key_rows, counts, pilot_rows = build()
    PACKAGE.mkdir(parents=True, exist_ok=True)
    with SHEET.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SHEET_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(sheet_rows)
    for coder_index, coder_path in enumerate(CODER_SHEETS, start=1):
        coder_rows = list(sheet_rows)
        random.Random(f"{SEED}|coder-{coder_index}-order").shuffle(coder_rows)
        with coder_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=SHEET_FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(coder_rows)
    with PILOT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SHEET_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(pilot_rows)
    KEY.write_text(
        json.dumps(
            {
                "_meta": {
                    "what": "Sampling-stratum key for the frozen blind 500-article audit; contains no labels.",
                    "seed": SEED,
                    "production_document_instances_per_channel": ARTICLE_N,
                    "story_clusters_per_channel": STORY_N,
                    "matched_document_instance_frame_by_channel": counts,
                    "unique_evidence_items_in_draw": len(
                        {row["evidence_identity_sha256"] for row in key_rows}
                    ),
                    "repeated_evidence_rows_in_draw": len(key_rows)
                    - len({row["evidence_identity_sha256"] for row in key_rows}),
                },
                "items": key_rows,
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"[blind-audit] wrote {len(sheet_rows)} scored items and "
        f"{len(pilot_rows)} unscored pilot items: {SHEET.relative_to(ROOT)}"
    )


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_coder(path: Path, canonical_rows: dict[str, dict[str, str]]) -> dict[str, str]:
    rows = _read_csv_rows(path)
    if len(rows) != len(canonical_rows):
        raise SystemExit(
            f"[blind-audit] {path}: expected {len(canonical_rows)} rows, got {len(rows)}"
        )
    labels: dict[str, str] = {}
    for row in rows:
        audit_id = (row.get("audit_id") or "").strip()
        label = (row.get("coder_label") or "").strip().upper()
        confidence = (row.get("coder_confidence") or "").strip().upper()
        if not audit_id:
            raise SystemExit(f"[blind-audit] {path}: row without audit_id")
        if audit_id in labels:
            raise SystemExit(f"[blind-audit] {path}: duplicate audit_id {audit_id}")
        if audit_id not in canonical_rows:
            raise SystemExit(f"[blind-audit] {path}: unknown audit_id {audit_id}")
        canonical = canonical_rows[audit_id]
        for field in SHEET_FIELDS[:6]:
            if (row.get(field) or "") != canonical[field]:
                raise SystemExit(f"[blind-audit] {path}: {audit_id} changed locked field {field}")
        if label not in ALLOWED:
            raise SystemExit(
                f"[blind-audit] {path}: {audit_id} has invalid/unfilled label {label!r}"
            )
        if confidence not in CONFIDENCE:
            raise SystemExit(
                f"[blind-audit] {path}: {audit_id} has invalid/unfilled confidence {confidence!r}"
            )
        labels[audit_id] = label
    return labels


def _wilson(on: int, n: int, z: float = 1.959963984540054) -> list[float] | None:
    if n == 0:
        return None
    p = on / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denominator
    return [round(centre - half, 3), round(centre + half, 3)]


def _cohens_kappa(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    n = len(pairs)
    observed = sum(left == right for left, right in pairs) / n
    left_on = sum(left == "ON" for left, _ in pairs) / n
    right_on = sum(right == "ON" for _, right in pairs) / n
    expected = left_on * right_on + (1 - left_on) * (1 - right_on)
    if expected >= 1:
        return None
    return round((observed - expected) / (1 - expected), 3)


def _gwet_ac1(pairs: list[tuple[str, str]]) -> float | None:
    """Return binary, unweighted Gwet's AC1 on firm-label pairs."""
    if not pairs:
        return None
    n = len(pairs)
    observed = sum(left == right for left, right in pairs) / n
    pooled_on = (
        sum(left == "ON" for left, _ in pairs) + sum(right == "ON" for _, right in pairs)
    ) / (2 * n)
    chance = 2 * pooled_on * (1 - pooled_on)
    if chance >= 1:
        return None
    return round((observed - chance) / (1 - chance), 3)


def _inter_coder_summary(
    pairs: list[tuple[str, str]], repeat_conflicts: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    repeat_conflicts = repeat_conflicts or []
    raw = round(sum(left == right for left, right in pairs) / len(pairs), 3) if pairs else None
    label_counts = {
        "coder_1_on": sum(left == "ON" for left, _ in pairs),
        "coder_1_off": sum(left == "OFF" for left, _ in pairs),
        "coder_2_on": sum(right == "ON" for _, right in pairs),
        "coder_2_off": sum(right == "OFF" for _, right in pairs),
    }
    pooled_labels = {label for pair in pairs for label in pair}
    constant_labels = len(pooled_labels) == 1
    evaluable = len(pairs) >= 400 and not constant_labels
    ac1 = _gwet_ac1(pairs)
    passed = (
        evaluable
        and not repeat_conflicts
        and raw is not None
        and raw >= 0.90
        and ac1 is not None
        and ac1 >= 0.70
    )
    return {
        "n_firm_overlap": len(pairs),
        "firm_overlap_label_counts": label_counts,
        "raw_agreement": raw,
        "gwet_ac1": ac1,
        "cohens_kappa_descriptive": _cohens_kappa(pairs),
        "kappa_note": "Published descriptively; not gated because kappa is prevalence-sensitive.",
        "reliability_evaluable": evaluable,
        "constant_labels": constant_labels,
        "within_coder_repeat_conflicts": repeat_conflicts,
        "n_within_coder_repeat_conflicts": len(repeat_conflicts),
        "reliability_evaluable_rule": (
            "At least 400 firm-overlap rows and a non-constant pooled firm-label set. "
            "An exactly all-ON or all-OFF overlap is NOT IDENTIFIABLE, not a failure."
        ),
        "reliability_gate": (
            "PASS"
            if passed
            else (
                "FAIL"
                if evaluable and not repeat_conflicts
                else (
                    "INCONCLUSIVE_REPEAT_CONFLICT"
                    if repeat_conflicts
                    else (
                        "NOT_IDENTIFIABLE_CONSTANT_LABELS"
                        if constant_labels
                        else "INCONCLUSIVE"
                    )
                )
            )
        ),
        "reliability_pass_rule": (
            "At least 400 unique-evidence firm overlaps, no contradictory "
            "within-coder repeat labels, raw agreement >= 0.90 and Gwet's AC1 >= 0.70."
        ),
        "disagreements_are_not_adjudicated_in_primary": True,
    }


def _coder_summary(labels: dict[str, str], key_rows: list[dict[str, str]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for channel in CHANNELS:
        for stratum in ("article_instance", "story_cluster"):
            ids = [
                row["audit_id"]
                for row in key_rows
                if row["channel"] == channel and row["stratum"] == stratum
            ]
            values = [labels[audit_id] for audit_id in ids]
            firm = [value for value in values if value in FIRM]
            on = sum(value == "ON" for value in firm)
            interval = _wilson(on, len(firm))
            gate: str | None = None
            if stratum == "article_instance":
                if len(firm) < 60:
                    gate = "INCONCLUSIVE"
                elif interval is not None and interval[0] >= 0.80:
                    gate = "PASS"
                else:
                    gate = "FAIL"
            rows.append(
                {
                    "channel": channel,
                    "stratum": stratum,
                    "n_drawn": len(values),
                    "n_firm": len(firm),
                    "n_abstain": sum(value == "ABSTAIN" for value in values),
                    "precision": round(on / len(firm), 3) if firm else None,
                    "wilson_95_ci": interval,
                    "registered_precision_gate": gate,
                }
            )
    article_values = [row["precision"] for row in rows if row["stratum"] == "article_instance"]
    article_values = [value for value in article_values if value is not None]
    return {
        "cells": rows,
        "equal_channel_macro_article_precision": (
            round(sum(article_values) / len(article_values), 3) if article_values else None
        ),
        "macro_note": "Equal-channel summary of five separately sampled channel precisions; not volume-weighted overall precision.",
    }


def score(coder_paths: list[Path]) -> dict[str, Any]:
    if len(coder_paths) not in {1, 2}:
        raise SystemExit("[blind-audit] score exactly one or two independent coder files")
    registration = json.loads(REGISTRATION.read_text(encoding="utf-8"))
    sample = registration["sample"]
    _verify(SHEET, sample["coder_sheet_sha256"], "coder sheet")
    _verify(KEY, sample["sample_key_sha256"], "sample key")
    key_rows = json.loads(KEY.read_text(encoding="utf-8"))["items"]
    expected_ids = {row["audit_id"] for row in key_rows}
    with SHEET.open(encoding="utf-8") as handle:
        canonical_rows = {row["audit_id"]: row for row in csv.DictReader(handle)}
    coders = [_read_coder(path, canonical_rows) for path in coder_paths]
    submission_rows = [_read_csv_rows(path) for path in coder_paths]
    for path, labels in zip(coder_paths, coders):
        if set(labels) != expected_ids:
            raise SystemExit(
                f"[blind-audit] {path}: expected {len(expected_ids)} ids, got {len(labels)}"
            )
    payload: dict[str, Any] = {
        "_meta": {
            "what": "Scoring output for the registered blind 500-article precision audit.",
            "registration": "validation/blind_audit_500/registration.json",
            "registration_sha256": _sha256(REGISTRATION.read_bytes()),
            "coders": len(coders),
            "coder_inputs": [
                {
                    "coder": index + 1,
                    "sha256": _sha256(path.read_bytes()),
                    "confidence_counts": {
                        level: sum(
                            (row.get("coder_confidence") or "").strip().upper() == level
                            for row in rows
                        )
                        for level in sorted(CONFIDENCE)
                    },
                    "n_nonempty_notes": sum(
                        bool((row.get("coder_note") or "").strip())
                        for row in rows
                    ),
                }
                for index, (path, rows) in enumerate(zip(coder_paths, submission_rows))
            ],
            "recall_estimated": False,
            "claim_limit": "Matched-item precision only. The design does not estimate population recall or validate the full historical series.",
        },
        "coder_results": [
            {"coder": index + 1, **_coder_summary(labels, key_rows)}
            for index, labels in enumerate(coders)
        ],
    }
    if len(coders) == 2:
        # Precision intentionally weights production document instances. The
        # reliability gate does not: identical title+URL evidence is evaluated
        # once so repeated production keys or cross-stratum reuse cannot
        # manufacture a larger agreement sample.
        by_evidence: dict[str, list[str]] = {}
        for row in key_rows:
            by_evidence.setdefault(row["evidence_identity_sha256"], []).append(
                row["audit_id"]
            )
        repeat_conflicts: list[dict[str, Any]] = []
        for coder_index, labels in enumerate(coders, start=1):
            for evidence_id, audit_ids in sorted(by_evidence.items()):
                firm = {labels[audit_id] for audit_id in audit_ids if labels[audit_id] in FIRM}
                if len(firm) > 1:
                    repeat_conflicts.append(
                        {
                            "coder": coder_index,
                            "evidence_identity_sha256": evidence_id,
                            "audit_ids": sorted(audit_ids),
                            "firm_labels": sorted(firm),
                        }
                    )
        pairs = [
            (coders[0][sorted(audit_ids)[0]], coders[1][sorted(audit_ids)[0]])
            for audit_ids in by_evidence.values()
            if coders[0][sorted(audit_ids)[0]] in FIRM
            and coders[1][sorted(audit_ids)[0]] in FIRM
        ]
        payload["inter_coder"] = _inter_coder_summary(pairs, repeat_conflicts)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--score", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.build:
        write_package()
        return
    if args.score:
        payload = score(args.score)
        if args.output:
            args.output.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        else:
            print(json.dumps(payload, indent=1))
        return
    parser.error("choose --build or --score")


if __name__ == "__main__":
    main()
