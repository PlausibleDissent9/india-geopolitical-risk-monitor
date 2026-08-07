"""Build and score the frozen 500-article independent-coder audit.

The draw contains 100 items per IGRM channel:

* 75 article instances sampled uniformly from matched URLs, estimating the
  precision of the article-weighted quantity the index actually counts;
* 25 normalized-headline clusters sampled uniformly, estimating descriptive
  story-level precision without letting syndication dominate.

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

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "validation" / "blind_audit_500"
SHEET = PACKAGE / "coder_sheet.csv"
PILOT = PACKAGE / "pilot_sheet.csv"
KEY = PACKAGE / "sample_key.json"
REGISTRATION = PACKAGE / "registration.json"

SOURCE_FILES = {
    "data/raw/receipt_days/2026-08-05-extended.json": (
        "71a681b3e98357b627e73c2de43d390acbe51b469292174a3e7afe2731bf1536"
    ),
    "data/raw/receipt_days/2026-08-06-extended.json": (
        "5145b919d51d2dc30c15a355d37092d60ef3f4a1181b92b4692ae29411226257"
    ),
}
RUBRIC = ROOT / "auditor" / "RUBRIC.md"
RUBRIC_SHA256 = "2f285c9ffbc96d43946dbf9b53cd9fa688c2353be2c05e9df02ab5be8db38d17"

CHANNELS = ["pakistan_west", "china_east", "gulf_energy", "us_trade", "shipping"]
ARTICLE_N = 75
STORY_N = 25
PILOT_N = 4
SEED = "igrm-blind-audit-500-v1-2026-08-07"
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


def _universe() -> dict[str, list[dict[str, str]]]:
    _verify(RUBRIC, RUBRIC_SHA256, "rubric")
    rows: dict[str, dict[str, dict[str, str]]] = {channel: {} for channel in CHANNELS}
    for relpath, expected in SOURCE_FILES.items():
        path = ROOT / relpath
        _verify(path, expected, relpath)
        payload = json.loads(path.read_text(encoding="utf-8"))
        metadata = payload["meta"]
        for group, keys in payload["matched"].items():
            channel = group.split("/", 1)[0]
            if channel not in rows:
                continue
            for key in keys:
                record = metadata.get(key) or {}
                url = str(record.get("url") or "").strip()
                title = str(record.get("title") or "").strip()
                raw_date = str(record.get("date") or "").strip()
                if not url or not title or len(raw_date.replace("-", "")) < 8:
                    continue
                # URL is the article-instance unit. If it appears in both
                # source days, retain the first chronological observation.
                rows[channel].setdefault(
                    url,
                    {
                        "channel": channel,
                        "article_date": _date(raw_date),
                        "title": title,
                        "domain": _domain(url),
                        "url": url,
                        "source_path": relpath,
                        "normalized_title": _title_key(title),
                    },
                )
    return {
        channel: sorted(items.values(), key=lambda row: row["url"])
        for channel, items in rows.items()
    }


def build() -> tuple[
    list[dict[str, str]], list[dict[str, str]], dict[str, int], list[dict[str, str]]
]:
    universe = _universe()
    sheet_rows: list[dict[str, str]] = []
    key_rows: list[dict[str, str]] = []
    pilot_rows: list[dict[str, str]] = []
    counts: dict[str, int] = {}

    for channel in CHANNELS:
        pool = universe[channel]
        if len(pool) < ARTICLE_N:
            raise SystemExit(f"[blind-audit] {channel} has only {len(pool)} article instances")
        counts[channel] = len(pool)
        article_rng = random.Random(f"{SEED}|{channel}|article")
        article_rows = article_rng.sample(pool, ARTICLE_N)
        represented_titles = {row["normalized_title"] for row in article_rows}

        by_story: dict[str, list[dict[str, str]]] = {}
        for row in pool:
            title_key = row["normalized_title"]
            if not title_key or title_key in represented_titles:
                continue
            by_story.setdefault(title_key, []).append(row)
        if len(by_story) < STORY_N:
            raise SystemExit(f"[blind-audit] {channel} has only {len(by_story)} unused stories")
        story_rng = random.Random(f"{SEED}|{channel}|story")
        story_keys = story_rng.sample(sorted(by_story), STORY_N)
        # One deterministic representative URL per sampled story cluster.
        story_rows = [sorted(by_story[key], key=lambda row: row["url"])[0] for key in story_keys]

        for stratum, selected in (
            ("article_instance", article_rows),
            ("story_cluster", story_rows),
        ):
            for row in selected:
                audit_id = (
                    "A" + _sha256(f"{SEED}|{channel}|{stratum}|{row['url']}".encode())[:15].upper()
                )
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
                        "normalized_title_sha256": _sha256(row["normalized_title"].encode()),
                    }
                )

        used_urls = {row["url"] for row in article_rows + story_rows}
        used_titles = {row["normalized_title"] for row in article_rows + story_rows}
        pilot_pool = [
            row
            for row in pool
            if row["url"] not in used_urls and row["normalized_title"] not in used_titles
        ]
        if len(pilot_pool) < PILOT_N:
            raise SystemExit(f"[blind-audit] {channel} has only {len(pilot_pool)} pilot items")
        pilot_rng = random.Random(f"{SEED}|{channel}|pilot")
        for row in pilot_rng.sample(pilot_pool, PILOT_N):
            pilot_id = "P" + _sha256(f"{SEED}|{channel}|pilot|{row['url']}".encode())[:15].upper()
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
                    "article_instances_per_channel": ARTICLE_N,
                    "story_clusters_per_channel": STORY_N,
                    "matched_url_universe_by_channel": counts,
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


def _read_coder(path: Path, canonical_rows: dict[str, dict[str, str]]) -> dict[str, str]:
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
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


def _inter_coder_summary(pairs: list[tuple[str, str]]) -> dict[str, Any]:
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
    passed = evaluable and raw is not None and raw >= 0.90 and ac1 is not None and ac1 >= 0.70
    return {
        "n_firm_overlap": len(pairs),
        "firm_overlap_label_counts": label_counts,
        "raw_agreement": raw,
        "gwet_ac1": ac1,
        "cohens_kappa_descriptive": _cohens_kappa(pairs),
        "kappa_note": "Published descriptively; not gated because kappa is prevalence-sensitive.",
        "reliability_evaluable": evaluable,
        "constant_labels": constant_labels,
        "reliability_evaluable_rule": (
            "At least 400 firm-overlap rows and a non-constant pooled firm-label set. "
            "An exactly all-ON or all-OFF overlap is NOT IDENTIFIABLE, not a failure."
        ),
        "reliability_gate": (
            "PASS"
            if passed
            else (
                "FAIL"
                if evaluable
                else ("NOT_IDENTIFIABLE_CONSTANT_LABELS" if constant_labels else "INCONCLUSIVE")
            )
        ),
        "reliability_pass_rule": "Raw agreement >= 0.90 and Gwet's AC1 >= 0.70.",
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
    for path, labels in zip(coder_paths, coders):
        if set(labels) != expected_ids:
            raise SystemExit(
                f"[blind-audit] {path}: expected {len(expected_ids)} ids, got {len(labels)}"
            )
    payload: dict[str, Any] = {
        "_meta": {
            "what": "Scoring output for the registered blind 500-article precision audit.",
            "registration": "validation/blind_audit_500/registration.json",
            "coders": len(coders),
            "recall_estimated": False,
            "claim_limit": "Matched-item precision only. The design does not estimate population recall or validate the full historical series.",
        },
        "coder_results": [
            {"coder": index + 1, **_coder_summary(labels, key_rows)}
            for index, labels in enumerate(coders)
        ],
    }
    if len(coders) == 2:
        pairs = [
            (coders[0][audit_id], coders[1][audit_id])
            for audit_id in sorted(expected_ids)
            if coders[0][audit_id] in FIRM and coders[1][audit_id] in FIRM
        ]
        payload["inter_coder"] = _inter_coder_summary(pairs)
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
