"""Build the evidence-bounded Global Event & Episode Ledger.

This is deliberately not an event-count inflation machine.  The current
upstream store contains daily aggregates, not retained GlobalEventID values or
raw row revision lineage.  The public artifact therefore keeps four different
objects separate:

* aggregate source rows;
* deduplicated source events (unavailable);
* canonical geopolitical events (unavailable until a signed release exists);
* detector-defined IGRM salience episodes.

The ledger is a deterministic first public vintage.  It exposes a complete
calendar partition and complete world-geometry denominator while refusing any
claim of a global event census, unique-event count, risk score or forecast.

Standalone::

    python -m src.event_ledger
    python -m src.event_ledger --check
"""

from __future__ import annotations

import argparse
import base64
import binascii
import csv
import hashlib
import json
import math
import os
import re
import struct
import subprocess
import tempfile
from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NoReturn, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from src import evolution_engine, publication_guard

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "governance" / "event_ledger_contract.json"
DAILY_PATH = ROOT / "data" / "raw" / "events_daily.csv"
DYADS_PATH = ROOT / "data" / "raw" / "events_dyads.csv"
STATES_PATH = ROOT / "data" / "raw" / "events_states.csv"
UNAVAILABLE_PATH = ROOT / "data" / "raw" / "events_unavailable_days.json"
WORLD_PATH = ROOT / "docs" / "geo" / "world.json"
RELATIONS_PATH = ROOT / "docs" / "data" / "map_relations.json"
EPISODES_PATH = ROOT / "docs" / "data" / "episodes.json"
LATEST_PATH = ROOT / "docs" / "data" / "latest.json"
OUTPUT_PATH = ROOT / "docs" / "data" / "event_ledger.json"
HTML_PATH = ROOT / "docs" / "ledger.html"
VINTAGE_DIR = ROOT / "docs" / "data" / "vintages" / "event-ledger"
RIGHTS_PATH = ROOT / "governance" / "source_rights_registry.json"
RIGHTS_SIGNERS_PATH = ROOT / "governance" / "rights_signers.json"

REQUIRED_PUBLIC_SOURCES = (
    "gdelt_events_v1",
    "gdelt_web_ngrams_v5",
    "igrm_public_payloads",
    "natural_earth",
)
REQUIRED_PUBLIC_USES = frozenset({"cite_metadata", "publish_derived_value"})
ALLOWED_RIGHTS_SIGNER_ROLES = frozenset(
    {"founder_rights_approver", "external_counsel_rights_approver"}
)
# Deliberately empty until a human-reviewed change pins both the signer ID and
# exact Ed25519 public key. Merely inserting a key into a mutable registry must
# never create publication authority.
TRUSTED_RIGHTS_SIGNERS: dict[str, str] = {}
ALLOWED_RELEASE_SIGNER_ROLES = frozenset(
    {"founder_release_approver", "external_release_approver"}
)
# This is a separate trust root from source-rights authorization.  A release
# signer attests the exact public vintage after all source decisions and
# transformations have been bound.  It remains empty until a human-reviewed
# commit pins an ID, role and exact Ed25519 public key.  The private key must
# never enter this repository or an agent session.
TRUSTED_RELEASE_SIGNERS: dict[str, dict[str, str]] = {}
REGISTERED_CONTRACT_SHA256 = "241b6bb99dff1a19b789612d01624af1c2e1a24f9fa93ee8d1783128f1f5f941"
VINTAGE_NAME = re.compile(r"^event-ledger-v([1-9][0-9]*)-([0-9a-f]{16})\.json$")
VINTAGE_RELATIVE = Path("docs/data/vintages/event-ledger")
MAX_RELEASE_CLOCK_SKEW = timedelta(minutes=5)
TYPED_CANONICAL_PROFILE = "igrm-typed-canonical-f64-v1"
MAX_SAFE_JSON_INTEGER = (1 << 53) - 1

DAILY_FIELDS = (
    "date",
    "n_global",
    "n_india",
    "n_verbal_conflict",
    "n_material_conflict",
    "n_protest",
    "goldstein_mean",
    "mentions_sum",
    "sources_sum",
    "articles_sum",
)
DYAD_FIELDS = (
    "date",
    "partner",
    "n",
    "n_coop",
    "n_conflict",
    "goldstein_mean",
    "mentions_sum",
    "sources_sum",
    "articles_sum",
)
STATE_FIELDS = ("date", "adm1", "n", "n_conflict", "n_protest")
CHANNELS = {
    "pakistan_west",
    "china_east",
    "gulf_energy",
    "us_trade",
    "shipping",
}
UNIT_IDS = (
    "aggregate_source_rows",
    "deduplicated_source_events",
    "canonical_geopolitical_events",
    "detected_salience_episodes",
)
TARGET_STATES = (
    "allegation",
    "official_position",
    "confirmed_action",
    "realized_disruption",
    "response",
    "recovery",
    "disputed",
    "superseded",
)


class EventLedgerError(ValueError):
    """Stable refusal raised when the ledger cannot be built truthfully."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise EventLedgerError(code, detail)


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _fail("json_duplicate_key", key)
        value[key] = item
    return value


def _read_json(path: Path, code: str) -> tuple[Any, str]:
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw,
            object_pairs_hook=_object,
            parse_constant=lambda _: _fail("json_non_finite"),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EventLedgerError(code, str(path)) from exc
    return value, hashlib.sha256(raw).hexdigest()


def _read_csv(path: Path, expected: tuple[str, ...], code: str) -> tuple[list[dict[str, str]], str]:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        reader = csv.DictReader(text.splitlines())
        if tuple(reader.fieldnames or ()) != expected:
            _fail(f"{code}_columns")
        rows = [dict(row) for row in reader]
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise EventLedgerError(code, str(path)) from exc
    if not rows:
        _fail(f"{code}_empty")
    return rows, hashlib.sha256(raw).hexdigest()


def _day(value: object, code: str) -> date:
    if not isinstance(value, str):
        _fail(code)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _fail(code)
    if parsed.isoformat() != value:
        _fail(code)
    return parsed


def _integer(value: object, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, str) or not value.isdigit():
        _fail(code)
    parsed = int(value)
    if parsed < 0:
        _fail(code)
    return parsed


def _optional_integer(value: object, code: str) -> int | None:
    return None if value == "" else _integer(value, code)


def _float(value: object, code: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        _fail(code)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        _fail(code)
    if not math.isfinite(parsed):
        _fail(code)
    return parsed


def _sha_projection(value: object) -> str:
    return evolution_engine.canonical_sha256(value)


def _typed_canonical_bytes(value: object) -> bytes:
    """Encode JSON data identically in Python and a browser.

    Ordinary JSON canonicalization is not a cross-runtime number contract:
    Python preserves ``1.0`` while JavaScript parses and serializes it as
    ``1``.  Release integrity therefore uses an explicit typed projection.
    Every number is a finite IEEE-754 binary64 value, integers outside the
    JavaScript safe range are refused, strings and object-key ordering operate
    on UTF-8 bytes, and negative zero remains distinguishable from positive
    zero.  The format is intentionally internal and versioned; signatures bind
    its resulting digest rather than relying on implementation-default JSON.
    """

    # One shared accumulator instead of a join per container: the joined
    # form re-copied every descendant's bytes once per ancestor level --
    # O(n * depth) copying -- and the registry test alone drove 76.6
    # million recursive calls through it (profiled 2026-08-10, 79% of
    # that test's runtime; the committed gate's ~37 minutes traced to
    # here through nine publishing lanes). The encoding this emits is
    # BYTE-IDENTICAL to the joined form -- the typed-canonical profile,
    # every sealed digest, and docs/typed-canonical.js are unaffected,
    # and tests/test_typed_canonical_bytes_reference.py holds this
    # implementation against a frozen copy of the original.
    out = bytearray()
    _typed_canonical_into(value, out)
    return bytes(out)


def _typed_canonical_into(value: object, out: bytearray) -> None:
    if value is None:
        out += b"n;"
        return
    if isinstance(value, bool):
        out += b"b1;" if value else b"b0;"
        return
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number) or (
            number.is_integer() and abs(number) > MAX_SAFE_JSON_INTEGER
        ):
            _fail("typed_canonical_number_invalid")
        out += b"d"
        out += struct.pack(">d", number).hex().encode("ascii")
        out += b";"
        return
    if isinstance(value, str):
        try:
            encoded = value.encode("utf-8")
        except UnicodeEncodeError:
            _fail("typed_canonical_string_invalid")
        out += b"s"
        out += str(len(encoded)).encode("ascii")
        out += b":"
        out += encoded.hex().encode("ascii")
        out += b";"
        return
    if isinstance(value, list):
        out += b"a"
        out += str(len(value)).encode("ascii")
        out += b":"
        for item in value:
            _typed_canonical_into(item, out)
        out += b";"
        return
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            _fail("typed_canonical_object_key_invalid")
        try:
            keys = sorted(value, key=lambda key: key.encode("utf-8"))
        except UnicodeEncodeError:
            _fail("typed_canonical_string_invalid")
        out += b"o"
        out += str(len(keys)).encode("ascii")
        out += b":"
        for key in keys:
            _typed_canonical_into(key, out)
            _typed_canonical_into(value[key], out)
        out += b";"
        return
    _fail("typed_canonical_type_invalid")


def _typed_canonical_sha256(value: object) -> str:
    # Hash the accumulator directly; the bytes() copy in
    # _typed_canonical_bytes exists for callers that keep the encoding.
    out = bytearray()
    _typed_canonical_into(value, out)
    return hashlib.sha256(out).hexdigest()


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise EventLedgerError("builder_unreadable", str(path)) from exc


def _git_blob(commit: str, path: str, expected_sha: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "show", f"{commit}:{path}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise EventLedgerError("candidate_baseline_unavailable", path) from exc
    if hashlib.sha256(result.stdout).hexdigest() != expected_sha:
        _fail("candidate_baseline_digest_mismatch", path)
    return result.stdout


def _git_vintage_snapshot(revision: str) -> dict[str, bytes]:
    try:
        listed = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", revision, "--", str(VINTAGE_RELATIVE)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise EventLedgerError("event_ledger_archive_history_unavailable", revision) from exc
    snapshot: dict[str, bytes] = {}
    for relative in [line for line in listed.stdout.splitlines() if line]:
        if not VINTAGE_NAME.fullmatch(Path(relative).name):
            _fail("authorized_release_filename_invalid", relative)
        try:
            blob = subprocess.run(
                ["git", "show", f"{revision}:{relative}"],
                cwd=ROOT,
                check=True,
                capture_output=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError) as exc:
            raise EventLedgerError("event_ledger_archive_history_unavailable", relative) from exc
        snapshot[relative] = blob
    return snapshot


def _enforce_archive_transition(
    parent: dict[str, bytes], head: dict[str, bytes], working: dict[str, bytes]
) -> None:
    for relative, prior in parent.items():
        if relative not in head:
            _fail("authorized_release_archive_removed", relative)
        if head[relative] != prior:
            _fail("authorized_release_archive_rewritten", relative)
    for relative, committed in head.items():
        if working.get(relative) != committed:
            _fail("authorized_release_worktree_drift", relative)
    added = sorted(set(head) - set(parent))
    untracked = sorted(set(working) - set(head))
    if len(added) > 1 or len(untracked) > 1 or (added and untracked):
        _fail("authorized_release_append_count_invalid")
    if added:
        match = VINTAGE_NAME.fullmatch(Path(added[0]).name)
        if match is None or int(match.group(1)) != len(parent) + 1:
            _fail("authorized_release_append_sequence_invalid", added[0])
    if untracked:
        match = VINTAGE_NAME.fullmatch(Path(untracked[0]).name)
        if match is None or int(match.group(1)) != len(head) + 1:
            _fail("authorized_release_append_sequence_invalid", untracked[0])


def _enforce_archive_history(
    transitions: Iterable[tuple[dict[str, bytes], dict[str, bytes]]]
) -> None:
    """Replay every committed archive transition, not merely HEAD^..HEAD."""

    for parent, current in transitions:
        _enforce_archive_transition(parent, current, current)


def _validate_archive_append_only() -> None:
    try:
        commits = subprocess.run(
            [
                "git",
                "log",
                "--first-parent",
                "--reverse",
                "--format=%H",
                "--",
                str(VINTAGE_RELATIVE),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise EventLedgerError("event_ledger_archive_history_unavailable") from exc

    transitions: list[tuple[dict[str, bytes], dict[str, bytes]]] = []
    for commit in commits:
        try:
            ancestry = subprocess.run(
                ["git", "rev-list", "--parents", "-n", "1", commit],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.split()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise EventLedgerError(
                "event_ledger_archive_history_unavailable", commit
            ) from exc
        if not ancestry or ancestry[0] != commit:
            _fail("event_ledger_archive_history_unavailable", commit)
        parent = _git_vintage_snapshot(ancestry[1]) if len(ancestry) > 1 else {}
        current = _git_vintage_snapshot(commit)
        transitions.append((parent, current))
    _enforce_archive_history(transitions)

    head = _git_vintage_snapshot("HEAD")
    working: dict[str, bytes] = {}
    if VINTAGE_DIR.exists():
        for path in VINTAGE_DIR.glob("*.json"):
            relative = path.relative_to(ROOT).as_posix()
            try:
                working[relative] = path.read_bytes()
            except OSError as exc:
                raise EventLedgerError("authorized_release_archive_unreadable", relative) from exc
    # A worktree may contain only one next sequential vintage.  Every already
    # committed transition was independently replayed above.
    _enforce_archive_transition(head, head, working)


def _validate_candidate_baseline(
    contract: dict[str, Any], observed_dates: set[date]
) -> None:
    baseline = contract.get("candidate_baseline")
    if not isinstance(baseline, dict):
        _fail("candidate_baseline_contract_invalid")
    commit = baseline.get("git_commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        _fail("candidate_baseline_contract_invalid")
    required = (
        ("events_daily_path", "events_daily_sha256"),
        ("events_dyads_path", "events_dyads_sha256"),
        ("events_states_path", "events_states_sha256"),
        ("unavailable_register_path", "unavailable_register_sha256"),
    )
    blobs: dict[str, bytes] = {}
    for path_key, sha_key in required:
        path = baseline.get(path_key)
        sha = baseline.get(sha_key)
        if (
            not isinstance(path, str)
            or path.startswith("/")
            or ".." in Path(path).parts
            or not isinstance(sha, str)
            or not re.fullmatch(r"[0-9a-f]{64}", sha)
        ):
            _fail("candidate_baseline_contract_invalid")
        blobs[path_key] = _git_blob(commit, path, sha)
    try:
        reader = csv.DictReader(blobs["events_daily_path"].decode("utf-8").splitlines())
        if tuple(reader.fieldnames or ()) != DAILY_FIELDS:
            _fail("candidate_baseline_daily_columns_invalid")
        baseline_dates = {
            _day(row.get("date"), "candidate_baseline_date_invalid") for row in reader
        }
    except (UnicodeDecodeError, csv.Error) as exc:
        raise EventLedgerError("candidate_baseline_daily_invalid") from exc
    removed = sorted(baseline_dates - observed_dates)
    if removed:
        _fail("candidate_baseline_observed_day_removed", removed[0].isoformat())


def _rights_gate(as_of: date) -> dict[str, Any]:
    signers_raw, signers_sha = _read_json(
        RIGHTS_SIGNERS_PATH, "rights_signers_unreadable"
    )
    registry_raw, registry_sha = _read_json(RIGHTS_PATH, "rights_registry_unreadable")
    if not isinstance(signers_raw, dict) or not isinstance(registry_raw, dict):
        _fail("rights_registry_shape_invalid")
    try:
        signers = publication_guard._validate_signers(signers_raw)
        sources = publication_guard._validate_rights_registry(
            registry_raw, ROOT, signers
        )
    except publication_guard.PublicationGuardError as exc:
        raise EventLedgerError("rights_registry_invalid", exc.code) from exc
    required: list[dict[str, Any]] = []
    blocked: list[str] = []
    for source_id in REQUIRED_PUBLIC_SOURCES:
        source = sources.get(source_id)
        if source is None:
            _fail("rights_source_missing", source_id)
        uses = set(cast(list[str], source["permitted_uses"]))
        signer_id = source.get("signer_id")
        signer = signers.get(signer_id) if isinstance(signer_id, str) else None
        trusted_key = (
            TRUSTED_RIGHTS_SIGNERS.get(signer_id)
            if isinstance(signer_id, str)
            else None
        )
        signer_trusted = (
            signer is not None
            and signer.get("role") in ALLOWED_RIGHTS_SIGNER_ROLES
            and signer.get("public_key_ed25519_base64") == trusted_key
        )
        review_due_raw = source.get("review_due")
        review_current = (
            isinstance(review_due_raw, str)
            and _day(review_due_raw, "rights_review_due_invalid") >= as_of
        )
        authorized = (
            source["decision_state"] == "approved"
            and REQUIRED_PUBLIC_USES.issubset(uses)
            and signer_trusted
            and review_current
        )
        if not authorized:
            blocked.append(source_id)
        required.append(
            {
                "source_id": source_id,
                "decision_state": source["decision_state"],
                "decision_id": source["decision_id"],
                "required_uses": sorted(REQUIRED_PUBLIC_USES),
                "authorized": authorized,
                "signer_id": signer_id,
                "signer_trusted": signer_trusted,
                "review_due": review_due_raw,
                "review_current_as_of_release": review_current,
                "decision_artifact_sha256": source["decision_artifact_sha256"],
            }
        )
    return {
        "authorized": not blocked,
        "blocked_source_ids": blocked,
        "required_sources": required,
        "evaluated_as_of": as_of.isoformat(),
        "trusted_signer_ids": sorted(TRUSTED_RIGHTS_SIGNERS),
        "allowed_signer_roles": sorted(ALLOWED_RIGHTS_SIGNER_ROLES),
        "rights_registry_sha256": registry_sha,
        "rights_signers_sha256": signers_sha,
    }


def _validate_daily(rows: list[dict[str, str]]) -> tuple[dict[date, dict[str, Any]], set[date]]:
    out: dict[date, dict[str, Any]] = {}
    for row in rows:
        current = _day(row.get("date"), "daily_date_invalid")
        if current in out:
            _fail("daily_date_duplicate", current.isoformat())
        n_global = _integer(row.get("n_global"), "daily_count_invalid")
        n_india = _integer(row.get("n_india"), "daily_count_invalid")
        verbal = _integer(row.get("n_verbal_conflict"), "daily_count_invalid")
        material = _integer(row.get("n_material_conflict"), "daily_count_invalid")
        protest = _integer(row.get("n_protest"), "daily_count_invalid")
        mentions = _integer(row.get("mentions_sum"), "daily_count_invalid")
        sources = _optional_integer(row.get("sources_sum"), "daily_count_invalid")
        articles = _optional_integer(row.get("articles_sum"), "daily_count_invalid")
        if n_india > n_global or verbal + material > n_india or protest > n_india:
            _fail("daily_subset_constraint_invalid", current.isoformat())
        goldstein_raw = row.get("goldstein_mean")
        goldstein = None if goldstein_raw == "" else _float(goldstein_raw, "daily_float_invalid")
        out[current] = {
            "valid_layout_export_rows": n_global,
            "india_involving_rows": n_india,
            "verbal_conflict_rows": verbal,
            "material_conflict_rows": material,
            "protest_rows": protest,
            "goldstein_mean": goldstein,
            "mentions_sum": mentions,
            "sources_sum": sources,
            "articles_sum": articles,
        }
    ordered = sorted(out)
    if ordered != list(out) or ordered[0].isoformat() != "2017-01-01":
        _fail("daily_order_or_start_invalid")
    return out, set(out)


def _validate_grouped_dates(
    rows: list[dict[str, str]], expected_dates: set[date], kind: str
) -> dict[str, int]:
    dates: set[date] = set()
    keys: set[tuple[date, str]] = set()
    totals: dict[str, int] = {}
    for row in rows:
        current = _day(row.get("date"), f"{kind}_date_invalid")
        dates.add(current)
        if kind == "dyad":
            member = row.get("partner")
            if not isinstance(member, str) or not member.strip():
                _fail("dyad_partner_invalid")
            values = (
                _integer(row.get("n"), "dyad_count_invalid"),
                _integer(row.get("n_coop"), "dyad_count_invalid"),
                _integer(row.get("n_conflict"), "dyad_count_invalid"),
                _integer(row.get("mentions_sum"), "dyad_count_invalid"),
            )
            _optional_integer(row.get("sources_sum"), "dyad_count_invalid")
            _optional_integer(row.get("articles_sum"), "dyad_count_invalid")
            if values[1] + values[2] > values[0]:
                _fail("dyad_subset_constraint_invalid", current.isoformat())
            totals[member] = totals.get(member, 0) + values[0]
            if row.get("goldstein_mean") != "":
                _float(row.get("goldstein_mean"), "dyad_float_invalid")
        else:
            member = row.get("adm1")
            if not isinstance(member, str) or not member.strip():
                _fail("state_member_invalid")
            n = _integer(row.get("n"), "state_count_invalid")
            conflict = _integer(row.get("n_conflict"), "state_count_invalid")
            protest = _integer(row.get("n_protest"), "state_count_invalid")
            if conflict > n or protest > n:
                _fail("state_subset_constraint_invalid", current.isoformat())
            totals[member] = totals.get(member, 0) + n
        key = (current, member)
        if key in keys:
            _fail(f"{kind}_key_duplicate", f"{current.isoformat()}:{member}")
        keys.add(key)
    if dates != expected_dates:
        _fail(f"{kind}_date_frame_mismatch")
    return totals


def _unavailable_days(value: Any) -> tuple[list[date], str]:
    if not isinstance(value, dict) or set(value) != {"_meta", "days"}:
        _fail("unavailable_register_shape_invalid")
    meta = value["_meta"]
    rows = value["days"]
    if not isinstance(meta, dict) or not isinstance(rows, list):
        _fail("unavailable_register_shape_invalid")
    verified = _day(meta.get("verified"), "unavailable_verified_invalid").isoformat()
    days = [_day(item, "unavailable_day_invalid") for item in rows]
    if days != sorted(days) or len(days) != len(set(days)):
        _fail("unavailable_days_order_or_duplicate")
    return days, verified


def _validate_calendar(
    observed: set[date], unavailable: list[date]
) -> tuple[date, date, list[date]]:
    start = min(observed)
    end = max(observed)
    unavailable_set = set(unavailable)
    if observed & unavailable_set:
        _fail("calendar_state_overlap")
    calendar = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    if set(calendar) != observed | unavailable_set:
        _fail("calendar_partition_incomplete")
    return start, end, calendar


def _validate_world(
    world: Any, relations: Any, dyad_totals: dict[str, int]
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    if not isinstance(world, dict) or not isinstance(world.get("countries"), dict):
        _fail("world_frame_invalid")
    countries = cast(dict[str, Any], world["countries"])
    if len(countries) != 247:
        _fail("world_frame_denominator_invalid")
    if not isinstance(relations, dict) or not isinstance(relations.get("partners"), dict):
        _fail("partner_frame_invalid")
    if not isinstance(relations.get("_meta"), dict) or relations["_meta"].get("partial") is not False:
        _fail("partner_frame_partial")
    partners = cast(dict[str, Any], relations["partners"])
    if "IND" not in countries or "IND" in partners:
        _fail("partner_self_frame_invalid")
    if not set(partners).issubset(countries):
        _fail("partner_outside_world_frame")
    for code, item in partners.items():
        if not isinstance(item, dict) or not isinstance(item.get("n"), int) or item["n"] < 0:
            _fail("partner_observation_invalid", code)
        if dyad_totals.get(code) != item["n"]:
            _fail("partner_projection_count_mismatch", code)
    mapped_from_dyads = sorted(code for code in dyad_totals if code in countries)
    if sorted(partners) != mapped_from_dyads:
        _fail("partner_projection_membership_mismatch")
    unmappable_provider_codes = sorted(code for code in dyad_totals if code not in countries)
    return countries, partners, unmappable_provider_codes


def _validate_detector_cutoff(value: Any) -> date:
    if not isinstance(value, dict):
        _fail("detector_cutoff_shape_invalid")
    return _day(value.get("date"), "detector_cutoff_date_invalid")


def _validate_episodes(
    value: Any, frame_start: date, detector_through: date
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        _fail("episodes_shape_invalid")
    out: list[dict[str, Any]] = []
    ids: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict) or set(raw) != {
            "channel", "start", "end", "peak_date", "peak_value", "n_spike_days", "label"
        }:
            _fail("episode_shape_invalid")
        channel = raw["channel"]
        if channel not in CHANNELS or not isinstance(raw["label"], str) or not raw["label"].strip():
            _fail("episode_identity_invalid")
        start = _day(raw["start"], "episode_date_invalid")
        end = _day(raw["end"], "episode_date_invalid")
        peak = _day(raw["peak_date"], "episode_date_invalid")
        if not frame_start <= start <= peak <= end <= detector_through:
            _fail("episode_window_invalid")
        peak_value = _float(raw["peak_value"], "episode_peak_invalid")
        n_spike_days = raw["n_spike_days"]
        if (
            peak_value <= 0
            or isinstance(n_spike_days, bool)
            or not isinstance(n_spike_days, int)
            or not 1 <= n_spike_days <= (end - start).days + 1
        ):
            _fail("episode_measure_invalid")
        episode_id = f"episode:{channel}:{start.isoformat()}"
        if episode_id in ids:
            _fail("episode_id_duplicate", episode_id)
        ids.add(episode_id)
        lifecycle_state = (
            "detector_window_closed"
            if (detector_through - end).days >= 3
            else "provisional_open_window"
        )
        out.append(
            {
                "episode_id": episode_id,
                "object_type": "detected_salience_episode",
                "channel": channel,
                "label": raw["label"],
                "start": start.isoformat(),
                "end": end.isoformat(),
                "peak_date": peak.isoformat(),
                "peak_value": peak_value,
                "n_spike_days": n_spike_days,
                "lifecycle_state": lifecycle_state,
                "canonical_event_ids": None,
                "canonical_event_link_state": "unavailable_no_canonical_release",
            }
        )
    return sorted(out, key=lambda row: (row["start"], row["channel"]))


def _validate_contract(value: Any) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or value.get("status") != "rights_gated_release_candidate"
        or value.get("effective") != "2026-08-09"
        or value.get("schema_version") != "1.0.0"
    ):
        _fail("contract_identity_invalid")
    frame = value.get("frame")
    rows = value.get("count_units")
    gate = value.get("canonical_event_gate")
    replay = value.get("historical_series_policy")
    release_gate = value.get("public_release_gate")
    prohibited = value.get("prohibited_interpretations")
    if (
        not isinstance(frame, dict)
        or frame.get("time_start") != "2017-01-01"
        or frame.get("rights_state") != "blocked_until_signed_source_decisions"
        or not isinstance(rows, list)
        or not isinstance(gate, dict)
        or not isinstance(replay, dict)
        or not isinstance(release_gate, dict)
        or not isinstance(prohibited, list)
    ):
        _fail("contract_boundary_invalid")
    if [row.get("id") for row in rows if isinstance(row, dict)] != list(UNIT_IDS):
        _fail("contract_count_units_invalid")
    availability = {
        row["id"]: row.get("candidate_available")
        for row in rows
        if isinstance(row, dict) and row.get("id") in UNIT_IDS
    }
    if availability != {
        "aggregate_source_rows": True,
        "deduplicated_source_events": False,
        "canonical_geopolitical_events": False,
        "detected_salience_episodes": True,
    }:
        _fail("contract_count_unit_availability_invalid")
    if (
        tuple(value.get("canonical_event_target_states", ())) != TARGET_STATES
        or gate.get("current_state") != "unavailable_no_production_canonical_release"
        or gate.get("model_promotion") != "prohibited"
        or not isinstance(gate.get("requirements"), list)
        or len(gate["requirements"]) < 7
        or replay.get("current_capability")
        != "current_release_historical_aggregate_series"
        or not isinstance(replay.get("archive_append_rule"), str)
        or not isinstance(replay.get("release_time_rule"), str)
        or release_gate.get("required_source_ids") != list(REQUIRED_PUBLIC_SOURCES)
        or release_gate.get("required_permitted_uses")
        != sorted(REQUIRED_PUBLIC_USES)
        or release_gate.get("human_signature_required") is not True
        or release_gate.get("agent_signature_prohibited") is not True
        or release_gate.get("trusted_signer_ids")
        != sorted(TRUSTED_RIGHTS_SIGNERS)
        or release_gate.get("allowed_signer_roles")
        != sorted(ALLOWED_RIGHTS_SIGNER_ROLES)
        or release_gate.get("trusted_release_signer_ids")
        != sorted(TRUSTED_RELEASE_SIGNERS)
        or release_gate.get("allowed_release_signer_roles")
        != sorted(ALLOWED_RELEASE_SIGNER_ROLES)
        or release_gate.get("detached_release_signature_required") is not True
        or release_gate.get("release_integrity_profile")
        != TYPED_CANONICAL_PROFILE
        or not isinstance(release_gate.get("release_integrity_rule"), str)
        or release_gate.get("release_signer_separate_from_rights_signer") is not True
        or not isinstance(release_gate.get("trust_root_change_authority"), str)
        or not isinstance(
            release_gate.get("release_trust_root_change_authority"), str
        )
        or len(prohibited) < 7
    ):
        _fail("contract_canonical_or_replay_boundary_invalid")
    return cast(dict[str, Any], value)


def _totals(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    items = list(rows)
    return {
        "valid_layout_export_rows": sum(
            row["valid_layout_export_rows"] for row in items
        ),
        "india_involving_rows": sum(row["india_involving_rows"] for row in items),
        "verbal_conflict_rows": sum(row["verbal_conflict_rows"] for row in items),
        "material_conflict_rows": sum(row["material_conflict_rows"] for row in items),
        "protest_rows": sum(row["protest_rows"] for row in items),
        "mentions_sum": sum(row["mentions_sum"] for row in items),
    }


def _build_candidate() -> dict[str, Any]:
    contract, contract_sha = _read_json(CONTRACT_PATH, "contract_unreadable")
    if contract_sha != REGISTERED_CONTRACT_SHA256:
        _fail("contract_digest_mismatch")
    daily_rows, daily_sha = _read_csv(DAILY_PATH, DAILY_FIELDS, "daily_store")
    dyad_rows, dyads_sha = _read_csv(DYADS_PATH, DYAD_FIELDS, "dyad_store")
    state_rows, states_sha = _read_csv(STATES_PATH, STATE_FIELDS, "state_store")
    unavailable_raw, unavailable_sha = _read_json(UNAVAILABLE_PATH, "unavailable_register_unreadable")
    world, world_sha = _read_json(WORLD_PATH, "world_frame_unreadable")
    relations, relations_sha = _read_json(RELATIONS_PATH, "partner_frame_unreadable")
    episodes_raw, episodes_sha = _read_json(EPISODES_PATH, "episodes_unreadable")
    latest_raw, latest_sha = _read_json(LATEST_PATH, "detector_cutoff_unreadable")

    contract = _validate_contract(contract)

    daily, observed_dates = _validate_daily(daily_rows)
    _validate_candidate_baseline(contract, observed_dates)
    dyad_totals = _validate_grouped_dates(dyad_rows, observed_dates, "dyad")
    _validate_grouped_dates(state_rows, observed_dates, "state")
    unavailable, unavailable_verified = _unavailable_days(unavailable_raw)
    frame_start, frame_end, calendar = _validate_calendar(observed_dates, unavailable)
    if frame_start.isoformat() != contract["frame"]["time_start"]:
        _fail("contract_time_start_mismatch")
    countries, partners, unmappable_provider_codes = _validate_world(
        world, relations, dyad_totals
    )
    detector_through = _validate_detector_cutoff(latest_raw)
    episodes = _validate_episodes(episodes_raw, frame_start, detector_through)

    dates: list[str] = []
    states: list[str] = []
    global_rows: list[int | None] = []
    india_rows: list[int | None] = []
    verbal_rows: list[int | None] = []
    material_rows: list[int | None] = []
    protest_rows: list[int | None] = []
    for current in calendar:
        dates.append(current.isoformat())
        if current in daily:
            row = daily[current]
            states.append("observed_aggregate")
            global_rows.append(row["valid_layout_export_rows"])
            india_rows.append(row["india_involving_rows"])
            verbal_rows.append(row["verbal_conflict_rows"])
            material_rows.append(row["material_conflict_rows"])
            protest_rows.append(row["protest_rows"])
        else:
            states.append("legacy_unavailable_without_retrieval_receipt")
            global_rows.append(None)
            india_rows.append(None)
            verbal_rows.append(None)
            material_rows.append(None)
            protest_rows.append(None)

    not_observed_members = [
        {"area_id": code, "name": countries[code]["name"]}
        for code in sorted(countries)
        if code not in partners and code != "IND"
    ]
    not_applicable_members = [{"area_id": "IND", "name": countries["IND"]["name"]}]
    unmappable_members = [
        {"provider_code": code, "aggregate_rows": dyad_totals[code]}
        for code in unmappable_provider_codes
    ]
    totals = _totals(daily.values())
    unit_rows = cast(list[dict[str, Any]], contract["count_units"])
    count_units = {cast(str, row["id"]): dict(row) for row in unit_rows}
    count_units["aggregate_source_rows"]["counts"] = totals
    count_units["aggregate_source_rows"]["observed_days"] = len(observed_dates)
    count_units["deduplicated_source_events"]["count"] = None
    count_units["canonical_geopolitical_events"]["count"] = None
    count_units["detected_salience_episodes"]["count"] = len(episodes)

    shares = [
        None if global_count is None or global_count == 0 or india_count is None else round(
            100 * india_count / global_count, 6
        )
        for global_count, india_count in zip(global_rows, india_rows)
    ]
    input_sha256 = {
        "event_ledger_builder": _file_sha256(Path(__file__)),
        "event_ledger_contract": contract_sha,
        "events_daily": daily_sha,
        "events_dyads": dyads_sha,
        "events_states": states_sha,
        "events_unavailable_days": unavailable_sha,
        "world_geometry": world_sha,
        "map_relations": relations_sha,
        "detected_episodes": episodes_sha,
        "detector_cutoff": latest_sha,
    }
    state_projection = {
        "input_sha256": input_sha256,
        "count_units": count_units,
        "calendar_dates": dates,
        "calendar_states": states,
        "valid_layout_rows": global_rows,
        "india_rows": india_rows,
        "india_row_share": shares,
        "verbal_rows": verbal_rows,
        "material_rows": material_rows,
        "protest_rows": protest_rows,
        "episodes": episodes,
        "world_members": [
            {"area_id": code, "name": countries[code]["name"]}
            for code in sorted(countries)
        ],
        "mapped_partners": partners,
        "unmappable_provider_members": unmappable_members,
    }
    state_sha = _sha_projection(state_projection)
    rights_as_of = max(
        _day(contract["effective"], "contract_effective_invalid"),
        frame_end,
        detector_through,
    )
    return {
        "_meta": {
            "schema_version": "1.0.0",
            "artifact_status": "validated_internal_candidate",
            "date": frame_end.isoformat(),
            "generated": f"{contract['effective']}T00:00:00Z",
            "generated_semantics": (
                "Deterministic earliest candidate-knowledge date from registered inputs; "
                "not a wall-clock build or retrieval timestamp."
            ),
            "observation_through": frame_end.isoformat(),
            "detector_observation_through": detector_through.isoformat(),
            "source_retrieved_at": None,
            "source_retrieved_at_state": "unavailable_legacy_aggregate_stores",
            "partial": False,
            "partial_definition": (
                "False means the declared calendar, aggregate-store and world-geometry "
                "denominators reconcile. It does not mean unique or canonical events are available."
            ),
            "license": "Not licensed for public values until signed source-rights decisions authorize the required uses",
            "citation": (
                "Krishna, Ishan (2026). IGRM Global Event and Episode Ledger, "
                "aggregate-observation foundation. https://igrm.in/data/event_ledger.json"
            ),
            "codebook": "https://igrm.in/codebook.html",
            "source": "https://igrm.in/data/event_ledger.json",
            "what": (
                "A denominator-complete aggregate observation and detector-episode ledger. "
                "It explicitly does not publish a global or unique-event census."
            ),
            "contract_effective": contract["effective"],
            "rights_as_of": rights_as_of.isoformat(),
            "measurement_state_sha256": state_sha,
            "input_sha256": input_sha256,
            "rights_state": contract["frame"]["rights_state"],
            "canonical_release_state": contract["canonical_event_gate"]["current_state"],
        },
        "boundary": {
            "purpose": contract["purpose"],
            "geographic_subject": contract["frame"]["geographic_subject"],
            "permitted_claims": [
                "Aggregate source-row counts involving India by represented UTC day",
                "Valid-layout export-row denominators by represented UTC day",
                "The exact current set of IGRM detector-defined salience episodes",
                "The complete represented and unavailable calendar-day partition",
                "The complete 247-member display geometry with self, mapped, not-observed and unmappable states separated",
            ],
            "prohibited_interpretations": contract["prohibited_interpretations"],
        },
        "frame": {
            "start": frame_start.isoformat(),
            "end": frame_end.isoformat(),
            "calendar_days": len(calendar),
            "observed_aggregate_days": len(observed_dates),
            "legacy_unavailable_days": len(unavailable),
            "legacy_unavailable_dates": [item.isoformat() for item in unavailable],
            "legacy_register_last_reviewed": unavailable_verified,
            "legacy_unavailable_evidence_state": "no_immutable_retrieval_receipts",
            "calendar_partition_complete": True,
            "aggregate_store_date_sets_equal": True,
            "global_geometry_members": len(countries),
            "eligible_external_partner_members": len(countries) - 1,
            "partner_members_mapped": len(partners),
            "partner_members_not_observed_reason_unresolved": len(not_observed_members),
            "partner_members_not_applicable_self": 1,
            "not_observed_partner_members": not_observed_members,
            "not_applicable_partner_members": not_applicable_members,
            "unmappable_provider_partner_codes": unmappable_members,
            "partner_coverage_share": None,
            "partner_coverage_share_state": "not_published_without_provider_eligibility_frame",
        },
        "count_units": count_units,
        "aggregate_historical_series": {
            "unit": "GDELT Events v1 aggregate rows after valid-layout parsing; null denotes a legacy missing source file without a retained retrieval receipt, never zero",
            "default_comparison_series": "india_involving_share_of_valid_layout_export_rows_pct",
            "raw_level_comparison_warning": "Raw row levels are not like-for-like across unregistered provider corpus regimes.",
            "source_regime_annotations": None,
            "source_regime_annotation_state": "unavailable_legacy_store",
            "dates": dates,
            "states": states,
            "valid_layout_export_rows": global_rows,
            "india_involving_rows": india_rows,
            "india_involving_share_of_valid_layout_export_rows_pct": shares,
            "verbal_conflict_rows": verbal_rows,
            "material_conflict_rows": material_rows,
            "protest_rows": protest_rows,
        },
        "episodes": episodes,
        "canonical_event_layer": {
            "available": False,
            "event_count": None,
            "target_states": contract["canonical_event_target_states"],
            "model_promotion": contract["canonical_event_gate"]["model_promotion"],
            "requirements": contract["canonical_event_gate"]["requirements"],
        },
        "candidate_lineage_policy": contract["historical_series_policy"],
    }


def _blocked_public_artifact(candidate: dict[str, Any], rights: dict[str, Any]) -> dict[str, Any]:
    candidate_units = cast(dict[str, dict[str, Any]], candidate["count_units"])
    units = {
        unit_id: {
            "definition": row["definition"],
            "public_available": False,
            "value": None,
            "blocked_reason": (
                "signed_source_rights_decisions_absent"
                if unit_id in {"aggregate_source_rows", "detected_salience_episodes"}
                else row.get("unavailable_reason", "source_identity_layer_unavailable")
            ),
        }
        for unit_id, row in candidate_units.items()
    }
    artifact: dict[str, Any] = {
        "_meta": {
            "schema_version": "1.0.0",
            "artifact_status": "public_release_blocked_rights_review",
            "date": candidate["_meta"]["contract_effective"],
            "generated": f"{candidate['_meta']['contract_effective']}T00:00:00Z",
            "generated_semantics": "Registered contract-effective time for a deterministic refusal artifact.",
            "partial": True,
            "partial_definition": "This endpoint emits no provider-derived values while any required signed rights decision is absent.",
            "license": "CC BY 4.0 for IGRM-authored schema and refusal text only; this endpoint releases no upstream-derived values",
            "citation": "Krishna, Ishan (2026). IGRM Global Event and Episode Ledger rights-gated release status. https://igrm.in/data/event_ledger.json",
            "codebook": "https://igrm.in/codebook.html",
            "source": "https://igrm.in/data/event_ledger.json",
            "what": "A fail-closed Global Event and Episode Ledger endpoint. Its blocked form contains no source-derived values; a future authorized form may publish the explicitly bounded aggregate and detector units described by the stable API contract.",
            "contract_effective": candidate["_meta"]["contract_effective"],
            "rights_state": "blocked_unsigned_or_unapproved_source_decisions",
            "canonical_release_state": "unavailable_no_production_canonical_release",
        },
        "rights_gate": rights,
        "boundary": {
            "publication_state": "blocked",
            "candidate_validation_state": "validated_in_process_not_published",
            "required_human_action": "Independent source-terms review and a human-signed decision for every required source; agents may not sign.",
            "scope_note": "This refusal governs event_ledger.json and ledger.html. It neither licenses nor retracts pre-existing source-specific endpoints, whose rights decisions remain separate and pending.",
            "prohibited_interpretations": candidate["boundary"]["prohibited_interpretations"],
        },
        "frame": None,
        "count_units": units,
        "aggregate_historical_series": None,
        "episodes": None,
        "canonical_event_layer": candidate["canonical_event_layer"],
        "release_lineage": {
            "public_vintage_number": None,
            "predecessor_release_integrity_sha256": None,
            "state": "no_public_value_release",
        },
    }
    state = _sha_projection(artifact)
    artifact["_meta"]["refusal_state_sha256"] = state
    artifact["_meta"]["status_id"] = f"event-ledger-blocked-{state[:16]}"
    return artifact


def _released_at(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail("release_time_invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _fail("release_time_invalid")
    if parsed.tzinfo != timezone.utc or parsed.microsecond:
        _fail("release_time_invalid")
    return parsed


def _verify_release_time(
    meta: dict[str, Any], predecessor_meta: dict[str, Any] | None = None
) -> datetime:
    released = _released_at(meta.get("released_at"))
    bound_keys = (
        "contract_effective",
        "observation_through",
        "detector_observation_through",
        "rights_as_of",
        "knowledge_cutoff",
    )
    bound_dates = [_day(meta.get(key), f"authorized_release_{key}_invalid") for key in bound_keys]
    if released.date() < max(bound_dates):
        _fail("authorized_release_precedes_evidence")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    if released > now + MAX_RELEASE_CLOCK_SKEW:
        _fail("authorized_release_future_clock_invalid")
    if predecessor_meta is not None:
        predecessor_time = _released_at(predecessor_meta.get("released_at"))
        if released <= predecessor_time:
            _fail("authorized_release_time_not_monotonic")
    return released


def _artifact_integrity(value: dict[str, Any]) -> str:
    clone = json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    meta = clone.get("_meta")
    if not isinstance(meta, dict):
        _fail("authorized_release_meta_invalid")
    meta.pop("artifact_integrity_sha256", None)
    return _typed_canonical_sha256(clone)


def _release_content_integrity(value: dict[str, Any]) -> str:
    """Hash release content without either self-hash or signature envelope."""

    clone = json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    meta = clone.get("_meta")
    if not isinstance(meta, dict):
        _fail("authorized_release_meta_invalid")
    meta.pop("artifact_integrity_sha256", None)
    meta.pop("release_content_sha256", None)
    meta.pop("release_signature", None)
    return _typed_canonical_sha256(clone)


def _release_signature_statement(value: dict[str, Any]) -> dict[str, Any]:
    meta = value.get("_meta")
    if not isinstance(meta, dict):
        _fail("authorized_release_meta_invalid")
    return {
        "schema_version": "igrm-event-ledger-release-signature-v1",
        "release_id": meta.get("release_id"),
        "vintage_number": meta.get("vintage_number"),
        "release_integrity_profile": meta.get("release_integrity_profile"),
        "release_content_sha256": meta.get("release_content_sha256"),
        "release_state_sha256": meta.get("release_state_sha256"),
        "predecessor_release_integrity_sha256": meta.get(
            "predecessor_release_integrity_sha256"
        ),
        "released_at": meta.get("released_at"),
        "knowledge_cutoff": meta.get("knowledge_cutoff"),
    }


def _release_signature_bytes(value: dict[str, Any]) -> bytes:
    try:
        return json.dumps(
            _release_signature_statement(value),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EventLedgerError("authorized_release_signature_statement_invalid") from exc


def _verify_release_signature(value: dict[str, Any]) -> None:
    meta = value.get("_meta")
    if not isinstance(meta, dict):
        _fail("authorized_release_meta_invalid")
    content_sha = meta.get("release_content_sha256")
    if (
        meta.get("release_integrity_profile") != TYPED_CANONICAL_PROFILE
        or not isinstance(content_sha, str)
        or not re.fullmatch(r"[0-9a-f]{64}", content_sha)
        or _release_content_integrity(value) != content_sha
    ):
        _fail("authorized_release_content_digest_invalid")
    envelope = meta.get("release_signature")
    if not isinstance(envelope, dict) or set(envelope) != {
        "schema_version",
        "algorithm",
        "signer_id",
        "signer_role",
        "public_key_ed25519_base64",
        "signed_payload_sha256",
        "signature_ed25519_base64",
    }:
        _fail("authorized_release_signature_missing")
    signer_id = envelope.get("signer_id")
    trusted = (
        TRUSTED_RELEASE_SIGNERS.get(signer_id)
        if isinstance(signer_id, str)
        else None
    )
    public_key_text = envelope.get("public_key_ed25519_base64")
    role = envelope.get("signer_role")
    statement = _release_signature_bytes(value)
    trusted_active = False
    if isinstance(trusted, dict) and set(trusted) == {
        "role",
        "public_key_ed25519_base64",
        "effective",
        "revoked_on",
    }:
        effective = _day(trusted.get("effective"), "release_signer_effective_invalid")
        revoked_raw = trusted.get("revoked_on")
        revoked = (
            _day(revoked_raw, "release_signer_revoked_invalid")
            if revoked_raw is not None
            else None
        )
        release_day = _released_at(meta.get("released_at")).date()
        trusted_active = effective <= release_day and (
            revoked is None or release_day < revoked
        )
    if (
        envelope.get("schema_version") != "1.0.0"
        or envelope.get("algorithm") != "Ed25519"
        or not isinstance(trusted, dict)
        or not trusted_active
        or trusted.get("public_key_ed25519_base64") != public_key_text
        or trusted.get("role") != role
        or role not in ALLOWED_RELEASE_SIGNER_ROLES
        or not isinstance(public_key_text, str)
        or not isinstance(envelope.get("signature_ed25519_base64"), str)
    ):
        _fail("authorized_release_signer_untrusted")
    if envelope.get("signed_payload_sha256") != hashlib.sha256(statement).hexdigest():
        _fail("authorized_release_signature_invalid")
    try:
        public_key = base64.b64decode(public_key_text, validate=True)
        signature = base64.b64decode(
            cast(str, envelope["signature_ed25519_base64"]), validate=True
        )
        if len(public_key) != 32 or len(signature) != 64:
            _fail("authorized_release_signature_invalid")
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, statement)
    except (binascii.Error, InvalidSignature, ValueError) as exc:
        raise EventLedgerError("authorized_release_signature_invalid") from exc


def _verify_authorized_release(
    value: dict[str, Any],
    expected_vintage: int,
    predecessor_integrity: str | None,
    filename: str | None = None,
    predecessor_release: dict[str, Any] | None = None,
) -> None:
    meta = value.get("_meta")
    rights = value.get("rights_gate")
    lineage = value.get("release_lineage")
    if (
        not isinstance(meta, dict)
        or meta.get("artifact_status") != "public_observation_foundation"
        or not isinstance(rights, dict)
        or rights.get("authorized") is not True
        or not isinstance(lineage, dict)
    ):
        _fail("authorized_release_shape_invalid")
    _verify_release_signature(value)
    integrity = meta.get("artifact_integrity_sha256")
    if (
        not isinstance(integrity, str)
        or not re.fullmatch(r"[0-9a-f]{64}", integrity)
        or _artifact_integrity(value) != integrity
    ):
        _fail("authorized_release_integrity_invalid")
    measurement_sha = meta.get("measurement_state_sha256")
    if not isinstance(measurement_sha, str) or not re.fullmatch(
        r"[0-9a-f]{64}", measurement_sha
    ):
        _fail("authorized_release_measurement_digest_invalid")
    release_state = _sha_projection(
        {"measurement_state_sha256": measurement_sha, "rights_gate": rights}
    )
    if meta.get("release_state_sha256") != release_state:
        _fail("authorized_release_state_digest_invalid")
    release_id = f"event-ledger-v{expected_vintage}-{release_state[:16]}"
    if (
        meta.get("vintage_number") != expected_vintage
        or meta.get("release_id") != release_id
        or lineage.get("vintage_number") != expected_vintage
        or lineage.get("predecessor_release_integrity_sha256")
        != predecessor_integrity
        or meta.get("predecessor_release_integrity_sha256")
        != predecessor_integrity
    ):
        _fail("authorized_release_chain_invalid")
    if filename is not None and filename != f"{release_id}.json":
        _fail("authorized_release_filename_invalid")
    predecessor_meta = (
        cast(dict[str, Any], predecessor_release["_meta"])
        if predecessor_release is not None
        else None
    )
    _verify_release_time(meta, predecessor_meta)


def _authorized_history() -> list[dict[str, Any]]:
    if not VINTAGE_DIR.exists():
        return []
    indexed: list[tuple[int, Path]] = []
    for path in VINTAGE_DIR.glob("*.json"):
        match = VINTAGE_NAME.fullmatch(path.name)
        if match is None:
            _fail("authorized_release_filename_invalid", path.name)
        indexed.append((int(match.group(1)), path))
    indexed.sort()
    if [number for number, _ in indexed] != list(range(1, len(indexed) + 1)):
        _fail("authorized_release_vintage_sequence_invalid")
    history: list[dict[str, Any]] = []
    predecessor: str | None = None
    predecessor_release: dict[str, Any] | None = None
    for number, path in indexed:
        value, _ = _read_json(path, "authorized_release_archive_unreadable")
        if not isinstance(value, dict):
            _fail("authorized_release_shape_invalid")
        _verify_authorized_release(
            value,
            number,
            predecessor,
            path.name,
            predecessor_release,
        )
        lineage = cast(dict[str, Any], value["release_lineage"])
        if lineage.get("delta") != _release_delta(predecessor_release, value):
            _fail("authorized_release_delta_invalid", path.name)
        history.append(value)
        predecessor_release = value
        predecessor = cast(str, value["_meta"]["artifact_integrity_sha256"])
    return history


def _release_delta(
    previous: dict[str, Any] | None, candidate: dict[str, Any]
) -> dict[str, Any]:
    fields = (
        "states",
        "valid_layout_export_rows",
        "india_involving_rows",
        "india_involving_share_of_valid_layout_export_rows_pct",
        "verbal_conflict_rows",
        "material_conflict_rows",
        "protest_rows",
    )
    new_series = cast(dict[str, Any], candidate["aggregate_historical_series"])
    new_dates = cast(list[str], new_series["dates"])

    def day_value(series: dict[str, Any], index: int, day: str) -> dict[str, Any]:
        return {
            "date": day,
            **{
                field: cast(list[Any], series[field])[index]
                for field in fields
            },
        }

    new_rows = {day: i for i, day in enumerate(new_dates)}
    new_episodes = {
        cast(str, row["episode_id"]): row
        for row in cast(list[dict[str, Any]], candidate["episodes"])
    }
    if previous is None:
        return {
            "type": "initial_release",
            "added_dates": [
                {
                    "date": day,
                    "after_sha256": _sha_projection(
                        day_value(new_series, new_rows[day], day)
                    ),
                }
                for day in new_dates
            ],
            "revised_dates": [],
            "removed_dates": [],
            "added_episode_ids": sorted(new_episodes),
            "revised_episodes": [],
            "removed_episode_ids": [],
        }
    old_series = previous.get("aggregate_historical_series")
    if not isinstance(old_series, dict):
        _fail("predecessor_series_invalid")
    old_dates = cast(list[str], old_series.get("dates"))
    if not isinstance(old_dates, list) or not all(isinstance(day, str) for day in old_dates):
        _fail("predecessor_series_invalid")
    old_rows = {day: i for i, day in enumerate(old_dates)}
    removed_dates = sorted(set(old_rows) - set(new_rows))
    if removed_dates:
        _fail("previously_published_date_removed", removed_dates[0])
    revised_dates: list[dict[str, Any]] = []
    for day in sorted(set(old_rows) & set(new_rows)):
        old_i = old_rows[day]
        new_i = new_rows[day]
        before = day_value(old_series, old_i, day)
        after = day_value(new_series, new_i, day)
        if before["states"] == "observed_aggregate" and after["states"] != "observed_aggregate":
            _fail("previously_observed_day_became_unavailable", day)
        if before != after:
            revised_dates.append(
                {
                    "date": day,
                    "changed_fields": [
                        field for field in fields if before[field] != after[field]
                    ],
                    "before_sha256": _sha_projection(before),
                    "after_sha256": _sha_projection(after),
                    "reason_state": "not_recorded_in_legacy_aggregate_store",
                }
            )
    old_episodes = {
        cast(str, row["episode_id"]): row
        for row in cast(list[dict[str, Any]], previous.get("episodes", []))
    }
    revised_episodes = [
        {
            "episode_id": key,
            "before_sha256": _sha_projection(old_episodes[key]),
            "after_sha256": _sha_projection(new_episodes[key]),
            "reason_state": "detector_output_changed_reason_not_recorded",
        }
        for key in sorted(set(old_episodes) & set(new_episodes))
        if old_episodes[key] != new_episodes[key]
    ]
    return {
        "type": "successor_release",
        "added_dates": [
            {
                "date": day,
                "after_sha256": _sha_projection(day_value(new_series, new_rows[day], day)),
            }
            for day in sorted(set(new_rows) - set(old_rows))
        ],
        "revised_dates": revised_dates,
        "removed_dates": [],
        "added_episode_ids": sorted(set(new_episodes) - set(old_episodes)),
        "revised_episodes": revised_episodes,
        "removed_episode_ids": sorted(set(old_episodes) - set(new_episodes)),
    }


def _unsigned_authorized_public_artifact(
    candidate: dict[str, Any],
    rights: dict[str, Any],
    previous: dict[str, Any] | None,
    released_at: str,
) -> dict[str, Any]:
    release_basis = {
        "measurement_state_sha256": candidate["_meta"]["measurement_state_sha256"],
        "rights_gate": rights,
    }
    release_state_sha = _sha_projection(release_basis)
    release_time = _released_at(released_at)
    previous_meta = cast(dict[str, Any], previous["_meta"]) if previous else {}
    vintage = int(previous_meta.get("vintage_number", 0)) + 1
    predecessor_integrity = previous_meta.get("artifact_integrity_sha256")
    if predecessor_integrity is not None and not isinstance(
        predecessor_integrity, str
    ):
        _fail("authorized_release_chain_invalid")
    released = dict(candidate)
    meta = dict(cast(dict[str, Any], candidate["_meta"]))
    meta.update(
        {
            "artifact_status": "public_observation_foundation",
            "license": "CC BY 4.0 for the IGRM-authored derived artifact; exact signed upstream decisions are bound below",
            "rights_state": "approved_signed_snapshot",
            "vintage_number": vintage,
            "release_state_sha256": release_state_sha,
            "release_id": f"event-ledger-v{vintage}-{release_state_sha[:16]}",
            "released_at": release_time.isoformat().replace("+00:00", "Z"),
            "knowledge_cutoff": candidate["_meta"]["detector_observation_through"],
            "release_integrity_profile": TYPED_CANONICAL_PROFILE,
            "predecessor_release_integrity_sha256": predecessor_integrity,
        }
    )
    released["_meta"] = meta
    released["count_units"] = {
        unit_id: {**row, "public_available": row["candidate_available"]}
        for unit_id, row in cast(
            dict[str, dict[str, Any]], candidate["count_units"]
        ).items()
    }
    released["rights_gate"] = rights
    released["release_lineage"] = {
        "vintage_number": vintage,
        "predecessor_release_integrity_sha256": predecessor_integrity,
        "delta": _release_delta(previous, candidate),
        "permitted_claim": candidate["candidate_lineage_policy"]["permitted_claim"],
        "prohibited_claim": candidate["candidate_lineage_policy"]["prohibited_claim"],
        "future_release_rule": candidate["candidate_lineage_policy"]["future_release_rule"],
    }
    released.pop("candidate_lineage_policy", None)
    release_meta = cast(dict[str, Any], released["_meta"])
    release_meta["release_content_sha256"] = _release_content_integrity(released)
    _verify_release_time(
        release_meta,
        cast(dict[str, Any], previous["_meta"]) if previous is not None else None,
    )
    return released


def _authorized_public_artifact(
    candidate: dict[str, Any],
    rights: dict[str, Any],
    previous: dict[str, Any] | None,
    released_at: str | None = None,
    release_signature: dict[str, Any] | None = None,
) -> dict[str, Any]:
    release_state_sha = _sha_projection(
        {
            "measurement_state_sha256": candidate["_meta"][
                "measurement_state_sha256"
            ],
            "rights_gate": rights,
        }
    )
    if (
        previous is not None
        and previous["_meta"].get("release_state_sha256") == release_state_sha
    ):
        previous_meta = cast(dict[str, Any], previous["_meta"])
        previous_lineage = cast(dict[str, Any], previous["release_lineage"])
        prior_integrity = previous_lineage.get(
            "predecessor_release_integrity_sha256"
        )
        if prior_integrity is not None and not isinstance(prior_integrity, str):
            _fail("authorized_release_chain_invalid")
        _verify_authorized_release(
            previous,
            cast(int, previous_meta["vintage_number"]),
            prior_integrity,
        )
        return previous
    if released_at is None:
        _fail("release_time_required")
    released = _unsigned_authorized_public_artifact(
        candidate, rights, previous, released_at
    )
    if release_signature is None:
        _fail("authorized_release_signature_required")
    cast(dict[str, Any], released["_meta"])["release_signature"] = json.loads(
        json.dumps(release_signature, ensure_ascii=False, allow_nan=False)
    )
    cast(dict[str, Any], released["_meta"])["artifact_integrity_sha256"] = (
        _artifact_integrity(released)
    )
    release_meta = cast(dict[str, Any], released["_meta"])
    predecessor_integrity = release_meta.get(
        "predecessor_release_integrity_sha256"
    )
    _verify_authorized_release(
        released,
        cast(int, release_meta["vintage_number"]),
        predecessor_integrity,
        predecessor_release=previous,
    )
    return released


def build(
    released_at: str | None = None,
    release_signature: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_archive_append_only()
    history = _authorized_history()
    candidate = _build_candidate()
    rights_as_of = _day(candidate["_meta"]["rights_as_of"], "rights_as_of_invalid")
    if released_at is not None:
        rights_as_of = max(rights_as_of, _released_at(released_at).date())
    rights = _rights_gate(rights_as_of)
    if not rights["authorized"]:
        return _blocked_public_artifact(candidate, rights)
    previous = history[-1] if history else None
    return _authorized_public_artifact(
        candidate, rights, previous, released_at, release_signature
    )


def _encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, 0o644)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _write_immutable(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            _fail("event_ledger_vintage_collision", str(path))
        return
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, 0o444)
        os.link(temp_path, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except FileExistsError:
        if path.read_bytes() != content:
            _fail("event_ledger_vintage_collision", str(path))
    finally:
        temp_path.unlink(missing_ok=True)


def write(path: Path = OUTPUT_PATH) -> None:
    try:
        report = build()
    except EventLedgerError as exc:
        if exc.code != "release_time_required":
            raise
        now = datetime.now(timezone.utc).replace(microsecond=0)
        report = build(now.isoformat().replace("+00:00", "Z"))
    content = _encoded(report)
    if report["_meta"]["artifact_status"] == "public_observation_foundation":
        release_id = cast(str, report["_meta"]["release_id"])
        _write_immutable(VINTAGE_DIR / f"{release_id}.json", content)
    _atomic_write(path, content)


def check(path: Path = OUTPUT_PATH) -> None:
    try:
        current = path.read_bytes()
    except OSError as exc:
        raise EventLedgerError("event_ledger_report_missing") from exc
    if current != _encoded(build()):
        _fail("event_ledger_report_stale")


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
