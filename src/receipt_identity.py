"""Independent, rights-sealed D-1 source-link receipt lane.

This lane asks GDELT DOC 2.0 only for bounded ArticleList metadata and keeps
only title, URL and derived domain for at most five links per registered
channel.  It never reads or writes a score, an NGram cache, either legacy
receipts payload, an article body or a raw source response.  Pending rights
produce a fresh value-free status without touching the network.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NoReturn, Protocol, cast
from urllib.parse import urlsplit, urlunsplit

import requests
from jsonschema import Draft202012Validator, FormatChecker

from . import receipt_identity_rights as rights

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_RELATIVE = Path("docs/data/receipt_identity.json")
OUTPUT_PATH = ROOT / OUTPUT_RELATIVE
CHANNELS = (
    "pakistan_west",
    "china_east",
    "gulf_energy",
    "us_trade",
    "shipping",
)
MAX_ARTICLES_PER_CHANNEL = 5
MAX_RECORDS_PER_QUERY = 10
MAX_REQUESTS_PER_RUN = 7
REQUEST_TIMEOUT_SECONDS = 45
REQUEST_INTERVAL_SECONDS = 15.0
API_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
QUERY_MAX_CHARS = 230
HEADERS = {"User-Agent": "IGRM/2.0 (bounded receipt identity; attributed GDELT data)"}
EVALUATION_PHASES = ("pre_network", "post_fetch", "pre_write")
EXIT_RIGHTS_BLOCKED = 30
EXIT_SOURCE_UNAVAILABLE = 31
EXIT_CONTRACT_INVALID = 32
EXIT_PAYLOAD_INVALID = 33
EXIT_RELEASE_REFUSED = 34
PREDECESSOR_STATES = ("path_absent", "different_target", "same_target")

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_FORBIDDEN_CONTENT_KEYS = {
    "article_body",
    "author",
    "authors",
    "body",
    "byline",
    "content",
    "description",
    "document_id",
    "documentid",
    "id",
    "image",
    "ngram",
    "post",
    "pre",
    "raw_response",
    "snippet",
    "source_record",
    "story_id",
    "text",
}


class ReceiptIdentityRefusal(RuntimeError):
    """Stable typed refusal for acquisition, payload and release boundaries."""

    def __init__(self, code: str, exit_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.exit_code = exit_code


class ArticleListResponseInvalid(ValueError):
    """The provider answered, but not with the closed ArticleList shape."""


@dataclass(frozen=True)
class PredecessorSnapshot:
    """Exact predecessor identity and, when present, its validated payload."""

    commit_sha: str
    state: str
    blob_git_sha1: str | None
    blob_sha256: str | None
    target_date: date | None
    payload: dict[str, Any] | None


def _fail(code: str, exit_code: int) -> NoReturn:
    raise ReceiptIdentityRefusal(code, exit_code)


class ArticleListClient(Protocol):
    """The sole network capability accepted by this lane."""

    def fetch(self, query: str, target: date) -> object: ...


class GdeltDocArticleListClient:
    """One bounded GDELT DOC ArticleList request with no response caching."""

    def __init__(self) -> None:
        self._last_request_finished: float | None = None

    def fetch(self, query: str, target: date) -> object:
        if self._last_request_finished is not None:
            elapsed = time.monotonic() - self._last_request_finished
            if elapsed < REQUEST_INTERVAL_SECONDS:
                time.sleep(REQUEST_INTERVAL_SECONDS - elapsed)
        params = {
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": str(MAX_RECORDS_PER_QUERY),
            "sort": "hybridrel",
            "startdatetime": target.strftime("%Y%m%d") + "000000",
            "enddatetime": target.strftime("%Y%m%d") + "235959",
        }
        try:
            response = requests.get(
                API_ENDPOINT,
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
                headers=HEADERS,
            )
            self._last_request_finished = time.monotonic()
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
        except requests.RequestException as exc:
            raise RuntimeError("GDELT ArticleList unavailable") from exc
        try:
            return json.loads(
                response.content,
                object_pairs_hook=_unique_response_object,
                parse_constant=_invalid_response_constant,
            )
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise ArticleListResponseInvalid("invalid GDELT ArticleList JSON") from exc


def _unique_response_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate response key")
        result[key] = value
    return result


def _invalid_response_constant(_value: str) -> NoReturn:
    raise ArticleListResponseInvalid("non-finite response value")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _build_query(terms: Sequence[str], anchor: str | None) -> str:
    query = "(" + " OR ".join(terms) + ")"
    return f"{anchor} {query}" if anchor else query


def _build_queries(terms: Sequence[str], anchor: str | None) -> list[str]:
    """Exact registered DOC partition rule, independent of the score fetcher."""

    groups: list[list[str]] = []
    current: list[str] = []
    for term in terms:
        if len(_build_query([term], anchor)) > QUERY_MAX_CHARS:
            _fail("receipt_identity_query_term_too_long", EXIT_CONTRACT_INVALID)
        if current and len(_build_query([*current, term], anchor)) > QUERY_MAX_CHARS:
            groups.append(current)
            current = []
        current.append(term)
    if current:
        groups.append(current)
    return [_build_query(group, anchor) for group in groups]


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        _fail("receipt_identity_json_invalid", EXIT_PAYLOAD_INVALID)


def _payload_seal(payload: Mapping[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("payload_seal_sha256", None)
    return _sha256(_canonical_bytes(unsigned))


def _seal(payload: dict[str, Any]) -> dict[str, Any]:
    payload["payload_seal_sha256"] = _payload_seal(payload)
    return payload


def _utc_second(value: object, code: str, exit_code: int) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail(code, exit_code)
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _fail(code, exit_code)
    if (
        result.utcoffset() != timedelta(0)
        or result.microsecond != 0
        or result.strftime("%Y-%m-%dT%H:%M:%SZ") != value
    ):
        _fail(code, exit_code)
    return result


def _strict_day(value: object, code: str, exit_code: int) -> date:
    if not isinstance(value, str):
        _fail(code, exit_code)
    try:
        result = date.fromisoformat(value)
    except ValueError:
        _fail(code, exit_code)
    if result.isoformat() != value:
        _fail(code, exit_code)
    return result


def _meta() -> dict[str, str]:
    return {
        "what": (
            "Independent D-1 source-link availability for the five registered "
            "channels; it is not a score input and never substitutes for the "
            "legacy construction receipts."
        ),
        "license": (
            "CC BY 4.0 applies only to IGRM-authored metadata; GDELT terms "
            "govern GDELT data and linked publisher works remain separately controlled."
        ),
        "citation": "Data supplied by the GDELT Project. https://www.gdeltproject.org/",
        "codebook": "https://igrm.in/codebook.html",
        "source": "https://igrm.in/data/receipt_identity.json",
        "gdelt_attribution": "Data supplied by the GDELT Project. https://www.gdeltproject.org/",
        "publisher_rights": (
            "Headlines identify and link to publisher-controlled works; no "
            "publisher article body or full record is redistributed."
        ),
    }


def _stable_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in snapshot.items() if key != "evaluated_at_utc"}


def _blockers(snapshot: Mapping[str, Any]) -> list[str]:
    blockers = [cast(str, snapshot["authorization_status"])]
    if snapshot["profile_activation_state"] != "active":
        blockers.append("receipt_identity_profile_inactive")
    return sorted(set(blockers))


def unavailable_payload(
    *,
    target: date,
    generated_at: datetime,
    profile: rights.ProfileIdentity,
    snapshot: Mapping[str, Any],
    predecessor: Mapping[str, Any],
) -> dict[str, Any]:
    channels = {
        channel: {"state": "unavailable", "reason_code": "rights_blocked"}
        for channel in CHANNELS
    }
    return _seal(
        {
            "_meta": _meta(),
            "schema_version": "1.0.0",
            "state": "unavailable",
            "target_date": target.isoformat(),
            "generated_at": generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_id": rights.SOURCE_ID,
            "independence_group": "gdelt_project",
            "profile_id": profile.profile_id,
            "profile_sha256": profile.profile_sha256,
            "predecessor": dict(predecessor),
            "channels": channels,
            "refusal": {
                "code": "rights_blocked",
                "blockers": _blockers(snapshot),
                "authority_snapshot": dict(snapshot),
            },
        }
    )


def _normalize_title(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    title = unicodedata.normalize("NFC", value).strip()
    if not title or len(title) > 500 or _CONTROL.search(title):
        return None
    return title


def _normalize_url(value: object) -> tuple[str, str] | None:
    if not isinstance(value, str) or not value or len(value) > 2048 or _CONTROL.search(value):
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or any(ch.isspace() for ch in value)
    ):
        return None
    host = parsed.hostname.lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return None
    if (
        not host
        or "." not in host
        or host.endswith((".local", ".internal", ".localhost"))
        or len(host) > 253
        or _CONTROL.search(host)
    ):
        return None
    netloc = parsed.hostname.lower()
    if port is not None:
        netloc = f"{netloc}:{port}"
    normalized = urlunsplit((parsed.scheme, netloc, parsed.path or "/", parsed.query, ""))
    return normalized, host


def _response_articles(value: object) -> list[dict[str, str]]:
    if not isinstance(value, dict) or set(value) != {"articles"}:
        raise ValueError("closed ArticleList response shape required")
    rows = value["articles"]
    if not isinstance(rows, list) or len(rows) > MAX_RECORDS_PER_QUERY:
        raise ValueError("ArticleList rows invalid")
    articles: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("ArticleList row invalid")
        title = _normalize_title(row.get("title"))
        url = _normalize_url(row.get("url"))
        if title is None or url is None:
            continue
        articles.append({"title": title, "url": url[0], "domain": url[1]})
    return articles


def _dictionary(root: Path, expected_sha256: str) -> dict[str, Any]:
    path = root / "dictionaries.json"
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        _fail("receipt_identity_dictionary_invalid", EXIT_CONTRACT_INVALID)
    if _sha256(raw) != expected_sha256 or not isinstance(value, dict):
        _fail("receipt_identity_dictionary_digest_mismatch", EXIT_CONTRACT_INVALID)
    return cast(dict[str, Any], value)


def acquire_channels(
    *,
    target: date,
    dictionaries: Mapping[str, Any],
    client: ArticleListClient,
) -> dict[str, dict[str, Any]]:
    """Fetch each channel independently; a failed query invalidates that channel."""

    requests_used = 0
    result: dict[str, dict[str, Any]] = {}
    for channel in CHANNELS:
        spec = dictionaries.get(channel)
        if not isinstance(spec, dict):
            _fail("receipt_identity_dictionary_invalid", EXIT_CONTRACT_INVALID)
        terms = spec.get("terms")
        anchor = spec.get("anchor")
        if not isinstance(terms, list) or any(not isinstance(term, str) for term in terms):
            _fail("receipt_identity_dictionary_invalid", EXIT_CONTRACT_INVALID)
        if anchor is not None and not isinstance(anchor, str):
            _fail("receipt_identity_dictionary_invalid", EXIT_CONTRACT_INVALID)
        queries = _build_queries(cast(list[str], terms), anchor)
        pool: dict[str, dict[str, str]] = {}
        reason: str | None = None
        for query in queries:
            requests_used += 1
            if requests_used > MAX_REQUESTS_PER_RUN:
                _fail("receipt_identity_request_budget_exceeded", EXIT_CONTRACT_INVALID)
            try:
                response = client.fetch(query, target)
            except ArticleListResponseInvalid:
                if reason is None:
                    reason = "source_response_invalid"
                continue
            except (OSError, RuntimeError, ReceiptIdentityRefusal):
                if reason is None:
                    reason = "source_unavailable"
                continue
            if reason is not None:
                continue
            try:
                articles = _response_articles(response)
            except ValueError:
                reason = "source_response_invalid"
                continue
            for article in articles:
                pool.setdefault(article["url"], article)
        if reason is not None:
            result[channel] = {"state": "unavailable", "reason_code": reason}
            continue
        unique_titles: set[str] = set()
        deduplicated = []
        for article in pool.values():
            title_key = article["title"].casefold()
            if title_key in unique_titles:
                continue
            unique_titles.add(title_key)
            deduplicated.append(article)
        result[channel] = {
            "state": "available",
            "articles": deduplicated[:MAX_ARTICLES_PER_CHANNEL],
        }
    if requests_used != MAX_REQUESTS_PER_RUN:
        _fail("receipt_identity_request_budget_mismatch", EXIT_CONTRACT_INVALID)
    return result


def active_payload(
    *,
    target: date,
    generated_at: datetime,
    profile: rights.ProfileIdentity,
    channels: Mapping[str, dict[str, Any]],
    proofs: Sequence[dict[str, Any]],
    predecessor: Mapping[str, Any],
) -> dict[str, Any]:
    if len(proofs) != len(EVALUATION_PHASES):
        _fail("receipt_identity_authority_phase_count_invalid", EXIT_CONTRACT_INVALID)
    available = sum(block.get("state") == "available" for block in channels.values())
    state = "available" if available == len(CHANNELS) else (
        "partial" if available else "unavailable"
    )
    return _seal(
        {
            "_meta": _meta(),
            "schema_version": "1.0.0",
            "state": state,
            "target_date": target.isoformat(),
            "generated_at": generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_id": rights.SOURCE_ID,
            "independence_group": "gdelt_project",
            "profile_id": profile.profile_id,
            "profile_sha256": profile.profile_sha256,
            "predecessor": dict(predecessor),
            "channels": dict(channels),
            "authority": {
                "required_uses": list(rights.CANONICAL_REQUIRED_USES),
                "evaluations": [
                    {"phase": phase, "proof": proof}
                    for phase, proof in zip(EVALUATION_PHASES, proofs)
                ],
            },
        }
    )


def _walk(value: object) -> tuple[set[str], list[str], bool]:
    keys: set[str] = set()
    strings: list[str] = []
    numeric = False
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key).lower())
            child_keys, child_strings, child_numeric = _walk(child)
            keys |= child_keys
            strings.extend(child_strings)
            numeric = numeric or child_numeric
    elif isinstance(value, list):
        for child in value:
            child_keys, child_strings, child_numeric = _walk(child)
            keys |= child_keys
            strings.extend(child_strings)
            numeric = numeric or child_numeric
    elif isinstance(value, str):
        strings.append(value)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = True
    return keys, strings, numeric


def _schema_validate(
    payload: Mapping[str, Any],
    profile: rights.ProfileIdentity,
    reader: rights.AuthorityReader,
) -> None:
    _, schema_raw = reader.read(
        profile.schema_path, "receipt_identity_output_schema_invalid"
    )
    if _sha256(schema_raw) != profile.schema_sha256:
        _fail("receipt_identity_output_schema_digest_mismatch", EXIT_PAYLOAD_INVALID)
    try:
        schema = json.loads(schema_raw)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    except Exception as exc:
        raise ReceiptIdentityRefusal(
            "receipt_identity_payload_schema_invalid", EXIT_PAYLOAD_INVALID
        ) from exc


def validate_payload(
    payload: Mapping[str, Any],
    *,
    root: Path = ROOT,
    expected_target: date | None = None,
    candidate_sha: str | None = None,
) -> None:
    reader: rights.AuthorityReader
    if candidate_sha is None:
        profile, _, reader = (
            *rights.load_profile_configuration(root),
            rights.WorktreeAuthorityReader(root),
        )
    else:
        profile, _, reader = rights.load_candidate_profile_configuration(
            root=root, candidate_sha=candidate_sha
        )
    _schema_validate(payload, profile, reader)
    if payload.get("payload_seal_sha256") != _payload_seal(payload):
        _fail("receipt_identity_payload_seal_invalid", EXIT_PAYLOAD_INVALID)
    target = _strict_day(
        payload.get("target_date"), "receipt_identity_payload_target_invalid", EXIT_PAYLOAD_INVALID
    )
    generated = _utc_second(
        payload.get("generated_at"), "receipt_identity_payload_time_invalid", EXIT_PAYLOAD_INVALID
    )
    if expected_target is not None and target != expected_target:
        _fail("receipt_identity_payload_target_mismatch", EXIT_PAYLOAD_INVALID)
    if generated.date() <= target or generated.date() - target != timedelta(days=1):
        _fail("receipt_identity_payload_not_exact_d_minus_1", EXIT_PAYLOAD_INVALID)
    if (
        payload.get("profile_sha256") != profile.profile_sha256
        or payload.get("profile_id") != profile.profile_id
    ):
        _fail("receipt_identity_payload_profile_invalid", EXIT_PAYLOAD_INVALID)
    predecessor = payload.get("predecessor")
    if not isinstance(predecessor, dict) or set(predecessor) != {
        "state",
        "commit_sha",
        "blob_git_sha1",
        "blob_sha256",
        "target_date",
    }:
        _fail("receipt_identity_payload_predecessor_invalid", EXIT_PAYLOAD_INVALID)
    predecessor_state = predecessor.get("state")
    predecessor_commit = predecessor.get("commit_sha")
    if (
        predecessor_state not in PREDECESSOR_STATES
        or not isinstance(predecessor_commit, str)
        or _GIT_SHA1.fullmatch(predecessor_commit) is None
    ):
        _fail("receipt_identity_payload_predecessor_invalid", EXIT_PAYLOAD_INVALID)
    if predecessor_state == "path_absent":
        if any(
            predecessor.get(field) is not None
            for field in ("blob_git_sha1", "blob_sha256", "target_date")
        ):
            _fail("receipt_identity_payload_predecessor_invalid", EXIT_PAYLOAD_INVALID)
    else:
        blob_git_sha1 = predecessor.get("blob_git_sha1")
        blob_sha256 = predecessor.get("blob_sha256")
        predecessor_target = _strict_day(
            predecessor.get("target_date"),
            "receipt_identity_payload_predecessor_invalid",
            EXIT_PAYLOAD_INVALID,
        )
        if (
            not isinstance(blob_git_sha1, str)
            or _GIT_SHA1.fullmatch(blob_git_sha1) is None
            or not isinstance(blob_sha256, str)
            or _SHA256.fullmatch(blob_sha256) is None
            or (predecessor_state == "same_target") != (predecessor_target == target)
        ):
            _fail("receipt_identity_payload_predecessor_invalid", EXIT_PAYLOAD_INVALID)
    channels = payload.get("channels")
    if not isinstance(channels, dict) or tuple(channels) != CHANNELS:
        _fail("receipt_identity_payload_channels_invalid", EXIT_PAYLOAD_INVALID)
    state = payload.get("state")
    available = 0
    for channel in CHANNELS:
        block = channels[channel]
        if not isinstance(block, dict):
            _fail("receipt_identity_payload_channel_invalid", EXIT_PAYLOAD_INVALID)
        if block.get("state") == "available":
            available += 1
            articles = block.get("articles")
            if not isinstance(articles, list) or len(articles) > MAX_ARTICLES_PER_CHANNEL:
                _fail("receipt_identity_payload_articles_invalid", EXIT_PAYLOAD_INVALID)
            seen: set[str] = set()
            for article in articles:
                if not isinstance(article, dict) or set(article) != {"title", "url", "domain"}:
                    _fail("receipt_identity_payload_article_invalid", EXIT_PAYLOAD_INVALID)
                title = _normalize_title(article["title"])
                normalized = _normalize_url(article["url"])
                if (
                    title != article["title"]
                    or normalized is None
                    or normalized != (article["url"], article["domain"])
                    or article["url"] in seen
                ):
                    _fail("receipt_identity_payload_article_invalid", EXIT_PAYLOAD_INVALID)
                seen.add(cast(str, article["url"]))
        elif set(block) != {"state", "reason_code"} or block.get("state") != "unavailable":
            _fail("receipt_identity_payload_channel_invalid", EXIT_PAYLOAD_INVALID)
    expected_state = "available" if available == len(CHANNELS) else (
        "partial" if available else "unavailable"
    )
    if state != expected_state:
        _fail("receipt_identity_payload_state_invalid", EXIT_PAYLOAD_INVALID)
    if "refusal" in payload:
        if available or "authority" in payload:
            _fail("receipt_identity_payload_refusal_values_invalid", EXIT_PAYLOAD_INVALID)
        keys, strings, numeric = _walk(payload)
        if numeric or _FORBIDDEN_CONTENT_KEYS & keys:
            _fail("receipt_identity_payload_refusal_values_invalid", EXIT_PAYLOAD_INVALID)
        if any(value.startswith(("http://", "https://")) for value in strings if value != rights.SOURCE_ID):
            # Fixed attribution/profile URLs are allowed; arbitrary source values are not.
            allowed = {
                "https://www.gdeltproject.org/",
                "https://igrm.in/codebook.html",
                "https://igrm.in/data/receipt_identity.json",
                "Data supplied by the GDELT Project. https://www.gdeltproject.org/",
            }
            if any(value.startswith(("http://", "https://")) and value not in allowed for value in strings):
                _fail("receipt_identity_payload_refusal_values_invalid", EXIT_PAYLOAD_INVALID)
        refusal = cast(dict[str, Any], payload["refusal"])
        snapshot = rights.validate_snapshot(refusal["authority_snapshot"], target=target)
        if refusal.get("blockers") != _blockers(snapshot):
            _fail("receipt_identity_payload_refusal_stale", EXIT_PAYLOAD_INVALID)
    else:
        authority = payload.get("authority")
        if not isinstance(authority, dict) or set(authority) != {"required_uses", "evaluations"}:
            _fail("receipt_identity_payload_authority_invalid", EXIT_PAYLOAD_INVALID)
        evaluations = authority.get("evaluations")
        if not isinstance(evaluations, list) or len(evaluations) != 3:
            _fail("receipt_identity_payload_authority_invalid", EXIT_PAYLOAD_INVALID)
        proofs = []
        for phase, evaluation in zip(EVALUATION_PHASES, evaluations):
            if not isinstance(evaluation, dict) or set(evaluation) != {"phase", "proof"}:
                _fail("receipt_identity_payload_authority_invalid", EXIT_PAYLOAD_INVALID)
            if evaluation["phase"] != phase or not isinstance(evaluation["proof"], dict):
                _fail("receipt_identity_payload_authority_invalid", EXIT_PAYLOAD_INVALID)
            proofs.append(cast(dict[str, Any], evaluation["proof"]))
        rights.require_compatible_evaluations(proofs, target=target)
    _canonical_bytes(payload)


def _write_payload(payload: Mapping[str, Any], path: Path, root: Path) -> None:
    validate_payload(payload, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, allow_nan=False, indent=1)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def execute(
    *,
    today: date,
    generated_at: datetime,
    root: Path = ROOT,
    path: Path | None = None,
    client: ArticleListClient | None = None,
    test_authority: rights.NonGitTestRightsAuthority | None = None,
    test_predecessor: PredecessorSnapshot | None = None,
) -> dict[str, Any]:
    """Run all rights boundaries and atomically write one D-1 payload."""

    if generated_at.tzinfo is None or generated_at.utcoffset() != timedelta(0):
        _fail("receipt_identity_generated_time_invalid", EXIT_CONTRACT_INVALID)
    generated_at = generated_at.astimezone(timezone.utc).replace(microsecond=0)
    if generated_at.date() != today:
        _fail("receipt_identity_generated_day_invalid", EXIT_CONTRACT_INVALID)
    target = today - timedelta(days=1)
    output = path or (root / OUTPUT_RELATIVE)
    snapshot, pre_network = rights.evaluate_authority(
        target=target, root=root, test_authority=test_authority
    )
    profile, _ = rights.load_profile_configuration(root)
    if profile.profile_sha256 != snapshot["profile_sha256"]:
        _fail("receipt_identity_rights_authority_drift", EXIT_RIGHTS_BLOCKED)
    if pre_network is None:
        pre_write_snapshot, _ = rights.evaluate_authority(
            target=target, root=root, test_authority=test_authority
        )
        if _stable_snapshot(pre_write_snapshot) != _stable_snapshot(snapshot):
            _fail("receipt_identity_rights_authority_drift", EXIT_RIGHTS_BLOCKED)
        predecessor = _prewrite_predecessor(
            root=root,
            target=target,
            test_authority=test_authority,
            test_predecessor=test_predecessor,
        )
        payload = unavailable_payload(
            target=target,
            generated_at=generated_at,
            profile=profile,
            snapshot=pre_write_snapshot,
            predecessor=_predecessor_binding(predecessor, target),
        )
        _write_payload(payload, output, root)
        return payload
    dictionaries = _dictionary(root, pre_network["dictionary_sha256"])
    channels = acquire_channels(
        target=target,
        dictionaries=dictionaries,
        client=client or GdeltDocArticleListClient(),
    )
    post_snapshot, post_fetch = rights.evaluate_authority(
        target=target, root=root, test_authority=test_authority
    )
    if post_fetch is None:
        _fail(str(post_snapshot["authorization_status"]), EXIT_RIGHTS_BLOCKED)
    pre_write_snapshot, pre_write = rights.evaluate_authority(
        target=target, root=root, test_authority=test_authority
    )
    if pre_write is None:
        _fail(str(pre_write_snapshot["authorization_status"]), EXIT_RIGHTS_BLOCKED)
    try:
        proofs = rights.require_compatible_evaluations(
            [pre_network, post_fetch, pre_write], target=target
        )
    except rights.ReceiptIdentityRightsError as exc:
        _fail(exc.code, EXIT_RIGHTS_BLOCKED)
    predecessor = _prewrite_predecessor(
        root=root,
        target=target,
        test_authority=test_authority,
        test_predecessor=test_predecessor,
    )
    channels = _retain_monotone_predecessor_channels(
        channels=channels,
        predecessor=predecessor,
        target=target,
    )
    payload = active_payload(
        target=target,
        generated_at=generated_at,
        profile=profile,
        channels=channels,
        proofs=proofs,
        predecessor=_predecessor_binding(predecessor, target),
    )
    _write_payload(payload, output, root)
    return payload


def _git_head(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"], cwd=root, capture_output=True, text=True
    )
    value = result.stdout.strip()
    if result.returncode != 0 or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        _fail("receipt_identity_release_candidate_invalid", EXIT_RELEASE_REFUSED)
    return value


def _release_predecessor(root: Path, candidate_sha: str) -> PredecessorSnapshot:
    result = subprocess.run(
        ["git", "rev-list", "--parents", "-n", "1", candidate_sha],
        cwd=root,
        capture_output=True,
        text=True,
    )
    parts = result.stdout.strip().split()
    if result.returncode != 0 or len(parts) != 2 or parts[0] != candidate_sha:
        _fail("receipt_identity_release_predecessor_invalid", EXIT_RELEASE_REFUSED)
    parent = parts[1]
    remote = _git_commit(
        root,
        "origin/main",
        "receipt_identity_release_remote_invalid",
        EXIT_RELEASE_REFUSED,
    )
    if parent != remote:
        _fail("receipt_identity_release_predecessor_remote_drift", EXIT_RELEASE_REFUSED)
    return _load_predecessor(
        root=root,
        ref=parent,
        require_remote=False,
        exit_code=EXIT_RELEASE_REFUSED,
    )


def _candidate_payload_bytes(root: Path, candidate_sha: str) -> bytes:
    reader = rights.CandidateAuthorityReader(root, candidate_sha)
    _, raw = reader.read(
        OUTPUT_RELATIVE.as_posix(), "receipt_identity_release_payload_tree_invalid"
    )
    return raw


def _parse_payload_bytes(raw: bytes, code: str, exit_code: int) -> dict[str, Any]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_unique_response_object,
            parse_constant=_invalid_response_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError):
        _fail(code, exit_code)
    if not isinstance(value, dict):
        _fail(code, exit_code)
    return cast(dict[str, Any], value)


def _git_commit(root: Path, ref: str, code: str, exit_code: int) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    if result.returncode != 0 or _GIT_SHA1.fullmatch(commit) is None:
        _fail(code, exit_code)
    return commit


def _git_last_path_commit(
    root: Path, commit: str, relative: Path, code: str, exit_code: int
) -> str:
    result = subprocess.run(
        ["git", "log", "-1", "--format=%H", commit, "--", relative.as_posix()],
        cwd=root,
        capture_output=True,
        text=True,
    )
    written = result.stdout.strip()
    if result.returncode != 0 or _GIT_SHA1.fullmatch(written) is None:
        _fail(code, exit_code)
    return written


def _git_tree_entry(
    root: Path, commit: str, relative: Path, code: str, exit_code: int
) -> tuple[str, str, str] | None:
    text = relative.as_posix()
    result = subprocess.run(
        ["git", "ls-tree", "-z", commit, "--", text],
        cwd=root,
        capture_output=True,
    )
    if result.returncode != 0:
        _fail(code, exit_code)
    if result.stdout == b"":
        return None
    match = re.fullmatch(
        rb"([0-9]{6}) ([a-z]+) ([0-9a-f]{40})\t"
        + re.escape(text.encode("utf-8"))
        + rb"\x00",
        result.stdout,
    )
    if match is None:
        _fail(code, exit_code)
    return (
        match.group(1).decode("ascii"),
        match.group(2).decode("ascii"),
        match.group(3).decode("ascii"),
    )


def _path_ever_existed(root: Path, commit: str, exit_code: int) -> bool:
    result = subprocess.run(
        ["git", "log", "--format=%H", commit, "--", OUTPUT_RELATIVE.as_posix()],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _fail("receipt_identity_predecessor_history_invalid", exit_code)
    return bool(result.stdout.strip())


def _load_predecessor(
    *,
    root: Path,
    ref: str,
    require_remote: bool,
    exit_code: int,
) -> PredecessorSnapshot:
    code = "receipt_identity_predecessor_invalid"
    commit = _git_commit(root, ref, code, exit_code)
    if require_remote:
        remote = _git_commit(root, "origin/main", code, exit_code)
        if commit != remote:
            _fail("receipt_identity_predecessor_remote_drift", exit_code)
    entry = _git_tree_entry(root, commit, OUTPUT_RELATIVE, code, exit_code)
    if entry is None:
        if _path_ever_existed(root, commit, exit_code):
            _fail("receipt_identity_predecessor_path_removed", exit_code)
        return PredecessorSnapshot(commit, "path_absent", None, None, None, None)
    mode, object_type, blob_git_sha1 = entry
    if mode != "100644" or object_type != "blob":
        _fail("receipt_identity_predecessor_mode_invalid", exit_code)
    try:
        _, raw = rights.CandidateAuthorityReader(root, commit).read(
            OUTPUT_RELATIVE.as_posix(), code
        )
        payload = _parse_payload_bytes(raw, code, exit_code)
        # The payload binds the profile it was WRITTEN under. Validating it
        # against the tip's profile deadlocks every profile transition: the
        # old payload can never match a newer profile, and no new payload
        # can be written while this check refuses. The blob is unchanged
        # since its writing commit, so validate it there instead.
        written = _git_last_path_commit(
            root, commit, OUTPUT_RELATIVE, code, exit_code
        )
        validate_payload(payload, root=root, candidate_sha=written)
        target = _strict_day(payload.get("target_date"), code, exit_code)
    except (ReceiptIdentityRefusal, rights.ReceiptIdentityRightsError) as exc:
        _fail(getattr(exc, "code", code), exit_code)
    return PredecessorSnapshot(
        commit,
        "present",
        blob_git_sha1,
        _sha256(raw),
        target,
        payload,
    )


def non_git_test_predecessor(
    payload: Mapping[str, Any], *, root: Path, commit_sha: str = "1" * 40
) -> PredecessorSnapshot:
    """Create explicit predecessor trust only for a non-Git synthetic fixture."""

    if subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=root, capture_output=True
    ).returncode == 0 or _GIT_SHA1.fullmatch(commit_sha) is None:
        _fail("receipt_identity_test_predecessor_forbidden", EXIT_CONTRACT_INVALID)
    validate_payload(payload, root=root)
    raw = (
        json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=1) + "\n"
    ).encode("utf-8")
    git_sha1 = hashlib.sha1(  # noqa: S324 - Git SHA-1 object identity
        b"blob " + str(len(raw)).encode("ascii") + b"\x00" + raw,
        usedforsecurity=False,
    ).hexdigest()
    target = _strict_day(
        payload.get("target_date"),
        "receipt_identity_test_predecessor_invalid",
        EXIT_CONTRACT_INVALID,
    )
    return PredecessorSnapshot(
        commit_sha,
        "present",
        git_sha1,
        _sha256(raw),
        target,
        dict(payload),
    )


def _prewrite_predecessor(
    *,
    root: Path,
    target: date,
    test_authority: rights.NonGitTestRightsAuthority | None,
    test_predecessor: PredecessorSnapshot | None,
) -> PredecessorSnapshot:
    if test_authority is not None:
        predecessor = test_predecessor or PredecessorSnapshot(
            "0" * 40, "path_absent", None, None, None, None
        )
        if predecessor.state == "present":
            if predecessor.payload is None:
                _fail(
                    "receipt_identity_test_predecessor_invalid",
                    EXIT_CONTRACT_INVALID,
                )
            validate_payload(predecessor.payload, root=root)
            raw = (
                json.dumps(
                    predecessor.payload,
                    ensure_ascii=False,
                    allow_nan=False,
                    indent=1,
                )
                + "\n"
            ).encode("utf-8")
            git_sha1 = hashlib.sha1(  # noqa: S324 - Git SHA-1 object identity
                b"blob " + str(len(raw)).encode("ascii") + b"\x00" + raw,
                usedforsecurity=False,
            ).hexdigest()
            target_from_payload = _strict_day(
                predecessor.payload.get("target_date"),
                "receipt_identity_test_predecessor_invalid",
                EXIT_CONTRACT_INVALID,
            )
            if (
                predecessor.blob_git_sha1 != git_sha1
                or predecessor.blob_sha256 != _sha256(raw)
                or predecessor.target_date != target_from_payload
            ):
                _fail(
                    "receipt_identity_test_predecessor_invalid",
                    EXIT_CONTRACT_INVALID,
                )
    else:
        if test_predecessor is not None:
            _fail("receipt_identity_test_predecessor_forbidden", EXIT_CONTRACT_INVALID)
        predecessor = _load_predecessor(
            root=root,
            ref="HEAD",
            require_remote=True,
            exit_code=EXIT_RIGHTS_BLOCKED,
        )
    _predecessor_binding(predecessor, target)
    return predecessor


def _predecessor_binding(
    predecessor: PredecessorSnapshot, target: date
) -> dict[str, Any]:
    if _GIT_SHA1.fullmatch(predecessor.commit_sha) is None:
        _fail("receipt_identity_predecessor_binding_invalid", EXIT_CONTRACT_INVALID)
    if predecessor.state == "path_absent":
        if any(
            value is not None
            for value in (
                predecessor.blob_git_sha1,
                predecessor.blob_sha256,
                predecessor.target_date,
                predecessor.payload,
            )
        ):
            _fail("receipt_identity_predecessor_binding_invalid", EXIT_CONTRACT_INVALID)
        return {
            "state": "path_absent",
            "commit_sha": predecessor.commit_sha,
            "blob_git_sha1": None,
            "blob_sha256": None,
            "target_date": None,
        }
    if (
        predecessor.state != "present"
        or predecessor.blob_git_sha1 is None
        or _GIT_SHA1.fullmatch(predecessor.blob_git_sha1) is None
        or predecessor.blob_sha256 is None
        or _SHA256.fullmatch(predecessor.blob_sha256) is None
        or predecessor.target_date is None
        or predecessor.payload is None
    ):
        _fail("receipt_identity_predecessor_binding_invalid", EXIT_CONTRACT_INVALID)
    return {
        "state": (
            "same_target" if predecessor.target_date == target else "different_target"
        ),
        "commit_sha": predecessor.commit_sha,
        "blob_git_sha1": predecessor.blob_git_sha1,
        "blob_sha256": predecessor.blob_sha256,
        "target_date": predecessor.target_date.isoformat(),
    }


def _retain_monotone_predecessor_channels(
    *,
    channels: Mapping[str, dict[str, Any]],
    predecessor: PredecessorSnapshot,
    target: date,
) -> dict[str, dict[str, Any]]:
    retained = {channel: dict(block) for channel, block in channels.items()}
    if predecessor.target_date != target or predecessor.payload is None:
        return retained
    if "refusal" in predecessor.payload:
        return retained
    prior_channels = cast(dict[str, dict[str, Any]], predecessor.payload["channels"])
    for channel in CHANNELS:
        prior = prior_channels[channel]
        if prior["state"] == "available":
            retained[channel] = {
                "state": "available",
                "articles": [dict(article) for article in prior["articles"]],
            }
    return retained


def _require_monotone_candidate(
    *, candidate: Mapping[str, Any], predecessor: PredecessorSnapshot, target: date
) -> None:
    if predecessor.target_date != target or predecessor.payload is None:
        return
    if "refusal" in predecessor.payload or "refusal" in candidate:
        return
    prior_channels = cast(dict[str, dict[str, Any]], predecessor.payload["channels"])
    current_channels = cast(dict[str, dict[str, Any]], candidate["channels"])
    prior_available = {
        channel for channel in CHANNELS if prior_channels[channel]["state"] == "available"
    }
    current_available = {
        channel for channel in CHANNELS if current_channels[channel]["state"] == "available"
    }
    if not prior_available <= current_available:
        _fail("receipt_identity_predecessor_channel_regression", EXIT_RELEASE_REFUSED)
    if any(
        current_channels[channel]["articles"]
        != prior_channels[channel]["articles"]
        for channel in prior_available
    ):
        _fail("receipt_identity_predecessor_articles_changed", EXIT_RELEASE_REFUSED)


def _require_matching_worktree_payload(root: Path, candidate_raw: bytes) -> None:
    path = root / OUTPUT_RELATIVE
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            _fail("receipt_identity_release_worktree_payload_invalid", EXIT_RELEASE_REFUSED)
        current = path.read_bytes()
    except OSError:
        _fail("receipt_identity_release_worktree_payload_invalid", EXIT_RELEASE_REFUSED)
    if current != candidate_raw:
        _fail("receipt_identity_release_worktree_payload_drift", EXIT_RELEASE_REFUSED)


def check_release_rights(
    *,
    expected_candidate_sha: str,
    root: Path = ROOT,
    test_authority: rights.NonGitTestRightsAuthority | None = None,
) -> dict[str, Any]:
    """Verify exact candidate blobs and current authority immediately pre-push."""

    if _git_head(root) != expected_candidate_sha:
        _fail("receipt_identity_release_candidate_changed", EXIT_RELEASE_REFUSED)
    for args in (("diff", "--quiet"), ("diff", "--cached", "--quiet")):
        if subprocess.run(["git", *args], cwd=root).returncode != 0:
            _fail("receipt_identity_release_tree_dirty", EXIT_RELEASE_REFUSED)
    predecessor = _release_predecessor(root, expected_candidate_sha)
    raw = _candidate_payload_bytes(root, expected_candidate_sha)
    _require_matching_worktree_payload(root, raw)
    payload = _parse_payload_bytes(
        raw, "receipt_identity_release_payload_invalid", EXIT_RELEASE_REFUSED
    )
    try:
        validate_payload(payload, root=root, candidate_sha=expected_candidate_sha)
    except (ReceiptIdentityRefusal, rights.ReceiptIdentityRightsError) as exc:
        code = getattr(exc, "code", "receipt_identity_release_payload_invalid")
        _fail(str(code), EXIT_RELEASE_REFUSED)
    target = _strict_day(
        payload["target_date"], "receipt_identity_release_temporal_invalid", EXIT_RELEASE_REFUSED
    )
    if payload.get("predecessor") != _predecessor_binding(predecessor, target):
        _fail("receipt_identity_release_predecessor_binding_invalid", EXIT_RELEASE_REFUSED)
    _require_monotone_candidate(
        candidate=payload,
        predecessor=predecessor,
        target=target,
    )
    generated = _utc_second(
        payload["generated_at"], "receipt_identity_release_temporal_invalid", EXIT_RELEASE_REFUSED
    )
    snapshot, current = rights.evaluate_candidate_authority(
        target=target,
        candidate_sha=expected_candidate_sha,
        root=root,
        test_authority=test_authority,
    )
    evaluated = _utc_second(
        snapshot["evaluated_at_utc"],
        "receipt_identity_release_temporal_invalid",
        EXIT_RELEASE_REFUSED,
    )
    if target != evaluated.date() - timedelta(days=1) or generated > evaluated:
        _fail("receipt_identity_release_temporal_invalid", EXIT_RELEASE_REFUSED)
    if "refusal" in payload:
        if current is not None:
            _fail("receipt_identity_release_authorized_withdrawal", EXIT_RELEASE_REFUSED)
        refusal = cast(dict[str, Any], payload["refusal"])
        bound_snapshot = cast(dict[str, Any], refusal["authority_snapshot"])
        if _stable_snapshot(snapshot) != _stable_snapshot(bound_snapshot):
            _fail("receipt_identity_release_authority_drift", EXIT_RELEASE_REFUSED)
        if refusal.get("blockers") != _blockers(snapshot):
            _fail("receipt_identity_release_refusal_stale", EXIT_RELEASE_REFUSED)
        return {
            "status": "unavailable_status_release_verified",
            "candidate_sha": expected_candidate_sha,
            "source_id": rights.SOURCE_ID,
            "target_date": target.isoformat(),
            "evaluated_at_utc": snapshot["evaluated_at_utc"],
            "predecessor_commit_sha": predecessor.commit_sha,
            "predecessor_blob_git_sha1": predecessor.blob_git_sha1,
            "predecessor_blob_sha256": predecessor.blob_sha256,
        }
    if current is None:
        _fail("receipt_identity_release_rights_not_authorized", EXIT_RELEASE_REFUSED)
    authority = cast(dict[str, Any], payload["authority"])
    evaluations = cast(list[dict[str, Any]], authority["evaluations"])
    bound_proofs = [
        cast(dict[str, Any], evaluation["proof"]) for evaluation in evaluations
    ]
    try:
        checked = rights.require_compatible_evaluations(
            [*bound_proofs, current], target=target
        )
    except rights.ReceiptIdentityRightsError as exc:
        _fail(exc.code, EXIT_RELEASE_REFUSED)
    return {
        "status": "receipt_identity_release_verified",
        "candidate_sha": expected_candidate_sha,
        "source_id": rights.SOURCE_ID,
        "target_date": target.isoformat(),
        "evaluated_at_utc": checked[-1]["evaluated_at_utc"],
        "predecessor_commit_sha": predecessor.commit_sha,
        "predecessor_blob_git_sha1": predecessor.blob_git_sha1,
        "predecessor_blob_sha256": predecessor.blob_sha256,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-payload", action="store_true")
    parser.add_argument("--expected-target")
    parser.add_argument("--check-release-rights", metavar="EXPECTED_CANDIDATE_SHA")
    args = parser.parse_args(argv)
    try:
        if args.verify_payload:
            value = _parse_payload_bytes(
                OUTPUT_PATH.read_bytes(),
                "receipt_identity_payload_invalid",
                EXIT_PAYLOAD_INVALID,
            )
            expected = (
                _strict_day(
                    args.expected_target,
                    "receipt_identity_expected_target_invalid",
                    EXIT_PAYLOAD_INVALID,
                )
                if args.expected_target
                else None
            )
            validate_payload(value, expected_target=expected)
            print("[receipt-identity] payload contract valid")
            return 0
        if args.check_release_rights:
            result = check_release_rights(expected_candidate_sha=args.check_release_rights)
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
            return 0
        now = datetime.now(timezone.utc).replace(microsecond=0)
        payload = execute(today=now.date(), generated_at=now)
    except (OSError, json.JSONDecodeError):
        print("[receipt-identity] REFUSED payload_unreadable", file=sys.stderr)
        return EXIT_PAYLOAD_INVALID
    except rights.ReceiptIdentityRightsError as exc:
        print(f"[receipt-identity] REFUSED {exc.code}", file=sys.stderr)
        return EXIT_RIGHTS_BLOCKED
    except ReceiptIdentityRefusal as exc:
        print(f"[receipt-identity] REFUSED {exc.code}", file=sys.stderr)
        return exc.exit_code
    if payload["state"] == "unavailable":
        print("[receipt-identity] wrote value-free unavailable status", file=sys.stderr)
        return EXIT_RIGHTS_BLOCKED
    print(f"[receipt-identity] wrote {payload['state']} D-1 source links")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
