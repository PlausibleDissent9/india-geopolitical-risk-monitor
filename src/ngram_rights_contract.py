"""Closed signed-decision contract for the prospective aggregate profile."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta

SOURCE_ID = "gdelt_web_ngrams_v5"
DECISION_SCHEMA_VERSION = "1.1.0"
PROFILE_ID = "igrm:gdelt-ngram-daily-aggregate:2.0.0"
TERMS_URL = "https://www.gdeltproject.org/about.html"
OFFICIAL_TERMS_CITATION = {
    "url": TERMS_URL,
    "publisher": "The GDELT Project",
    "review_scope": "about page dataset-use and redistribution terms",
}
HISTORICAL_RECOVERY_FIRST_TARGET = date(2026, 8, 9)
HISTORICAL_RECOVERY_LAST_TARGET = date(2026, 8, 31)
MAX_HISTORICAL_RECOVERY_TARGETS = 23


def historical_recovery_targets(reviewed_on: date) -> list[str]:
    """Return the exact bounded completed-day outage prefix signed at review."""

    last_completed = reviewed_on - timedelta(days=1)
    if last_completed < HISTORICAL_RECOVERY_FIRST_TARGET:
        return []
    if last_completed > HISTORICAL_RECOVERY_LAST_TARGET:
        raise ValueError("historical_recovery_review_after_cutoff")
    count = (last_completed - HISTORICAL_RECOVERY_FIRST_TARGET).days + 1
    if count > MAX_HISTORICAL_RECOVERY_TARGETS:
        raise ValueError("historical_recovery_target_limit_exceeded")
    return [
        (HISTORICAL_RECOVERY_FIRST_TARGET + timedelta(days=offset)).isoformat()
        for offset in range(count)
    ]


def historical_recovery_targets_sha256(targets: list[str]) -> str:
    """Digest the signed canonical recovery vector without range semantics."""

    return hashlib.sha256(
        json.dumps(targets, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

BASE_DECISION_FIELDS = frozenset(
    {
        "schema_version",
        "source_id",
        "name",
        "provider",
        "role",
        "authority_class",
        "independence_group",
        "decision_id",
        "decision_owner",
        "signer_id",
        "reviewed_on",
        "review_due",
        "access_url",
        "terms_url",
        "access_basis",
        "lineage_policy",
        "max_current_age_days",
        "permitted_uses",
        "statement",
    }
)
AGGREGATE_DECISION_FIELDS = BASE_DECISION_FIELDS | {
    "profile_id",
    "official_terms_citation",
    "historical_recovery_targets",
    "historical_recovery_targets_sha256",
}
