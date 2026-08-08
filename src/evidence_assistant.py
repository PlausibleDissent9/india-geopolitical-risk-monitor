"""Evidence-locked answer core for a future IGRM assistant.

The trust boundary is deliberately narrow.  A model may eventually map a
question to a registered plan, but it never supplies publishable prose,
numbers, entities, dates, citations, or denominators.  This module re-opens
the cited payload bytes, verifies each typed fact, and renders only registered
templates.  Anything outside that finite grammar is refused.

This is a local safety core, not a public chat endpoint and not a forecast or
advice system.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, Union
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
LATEST_SOURCE = PurePosixPath("docs", "data", "latest.json").as_posix()
LATEST_CITATION = "https://igrm.in/data/latest.json"
RECEIPTS_SOURCE = PurePosixPath("docs", "data", "receipts.json").as_posix()
RECEIPTS_CITATION = "https://igrm.in/data/receipts.json"
RECEIPT_ENTRIES_PER_ANSWER = 5
PLAN_SCHEMA_VERSION = "1.0.0"
ANSWER_SCHEMA_VERSION = "1.0.0"

JsonScalar = Union[str, int, float, bool, None]

CHANNELS = (
    "pakistan_west",
    "china_east",
    "gulf_energy",
    "us_trade",
    "shipping",
)


class EvidenceError(ValueError):
    """Fail-closed error carrying a stable machine-readable reason."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class FactSpec:
    source_path: str
    pointer: str
    value_kind: str
    unit: str
    denominator: str
    citation: str


@dataclass(frozen=True)
class Fact:
    fact_id: str
    source_path: str
    pointer: str
    value: JsonScalar
    value_kind: str
    unit: str
    denominator: str
    as_of: str
    citation: str
    source_sha256: str


@dataclass(frozen=True)
class Plan:
    schema_version: str
    intent: str
    template_id: str
    fact_ids: tuple[str, ...]


@dataclass(frozen=True)
class Answer:
    schema_version: str
    status: str
    refusal_code: str | None
    text: str
    as_of: str | None
    template_id: str
    fact_ids: tuple[str, ...]
    evidence: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["fact_ids"] = list(self.fact_ids)
        result["evidence"] = list(self.evidence)
        return result


def _fact_specs() -> dict[str, FactSpec]:
    specs = {
        "latest.date": FactSpec(
            LATEST_SOURCE,
            "/date",
            "date",
            "ISO-8601 completed news day",
            "one completed UTC news day",
            LATEST_CITATION,
        ),
        "latest.composite7": FactSpec(
            LATEST_SOURCE,
            "/composite7",
            "number",
            "percentile, 0-100",
            "unweighted mean of the five channel score7 readings",
            LATEST_CITATION,
        ),
        "latest.definition": FactSpec(
            LATEST_SOURCE,
            "/definition",
            "scope",
            "text",
            "instrument definition carried by latest.json",
            LATEST_CITATION,
        ),
    }
    for channel in CHANNELS:
        base = f"latest.channels.{channel}"
        pointer = f"/channels/{channel}"
        specs[f"{base}.label"] = FactSpec(
            LATEST_SOURCE,
            f"{pointer}/label",
            "label",
            "text",
            "registered channel label",
            LATEST_CITATION,
        )
        specs[f"{base}.score"] = FactSpec(
            LATEST_SOURCE,
            f"{pointer}/score",
            "number",
            "percentile, 0-100",
            "that channel's matched-news share for one completed day ranked "
            "against its own trailing 730 completed days",
            LATEST_CITATION,
        )
        specs[f"{base}.score7"] = FactSpec(
            LATEST_SOURCE,
            f"{pointer}/score7",
            "number",
            "percentile, 0-100",
            "that channel's trailing-7-day matched-news share ranked "
            "against its own trailing 730 completed days",
            LATEST_CITATION,
        )
    specs["receipts.date"] = FactSpec(
        RECEIPTS_SOURCE,
        "/date",
        "date",
        "ISO-8601 completed news day",
        "one completed UTC news day",
        RECEIPTS_CITATION,
    )
    for channel in CHANNELS:
        base = f"receipts.channels.{channel}"
        pointer = f"/channels/{channel}"
        specs[f"{base}.label"] = FactSpec(
            RECEIPTS_SOURCE,
            f"{pointer}/label",
            "label",
            "text",
            "channel label carried by the receipt payload",
            RECEIPTS_CITATION,
        )
        for index in range(RECEIPT_ENTRIES_PER_ANSWER):
            article_base = f"{base}.displayed.{index}"
            article_pointer = f"{pointer}/articles/{index}"
            for field, value_kind, unit, denominator in (
                (
                    "date",
                    "compact_date",
                    "YYYYMMDD completed news day",
                    "date attached to one displayed receipt entry",
                ),
                (
                    "title",
                    "title",
                    "text",
                    "title of one displayed receipt entry; not a score input count",
                ),
                (
                    "domain",
                    "domain",
                    "hostname label",
                    "publisher domain on one displayed receipt entry",
                ),
                (
                    "url",
                    "url",
                    "HTTP(S) URL",
                    "source link on one displayed receipt entry",
                ),
                (
                    "lane",
                    "lane",
                    "registered receipt-lane code",
                    "retrieval lane on one displayed receipt entry",
                ),
            ):
                specs[f"{article_base}.{field}"] = FactSpec(
                    RECEIPTS_SOURCE,
                    f"{article_pointer}/{field}",
                    value_kind,
                    unit,
                    denominator,
                    RECEIPTS_CITATION,
                )
    return specs


FACT_SPECS = _fact_specs()


def _source_file(root: Path, source_path: str) -> Path:
    posix = PurePosixPath(source_path)
    if posix.is_absolute() or ".." in posix.parts:
        raise EvidenceError("unsafe_source_path", source_path)
    candidate = (root / Path(*posix.parts)).resolve()
    resolved_root = root.resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise EvidenceError("unsafe_source_path", source_path)
    return candidate


def _read_source(root: Path, source_path: str) -> tuple[bytes, dict[str, Any], str]:
    path = _source_file(root, source_path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise EvidenceError("source_unavailable", source_path) from exc
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError("source_not_json", source_path) from exc
    if not isinstance(document, dict):
        raise EvidenceError("source_shape_invalid", source_path)
    return raw, document, hashlib.sha256(raw).hexdigest()


def _pointer(document: Any, pointer: str) -> JsonScalar:
    if pointer == "":
        current = document
    elif not pointer.startswith("/"):
        raise EvidenceError("pointer_invalid", pointer)
    else:
        current = document
        for raw_token in pointer[1:].split("/"):
            token = raw_token.replace("~1", "/").replace("~0", "~")
            try:
                if isinstance(current, dict):
                    current = current[token]
                elif isinstance(current, list):
                    current = current[int(token)]
                else:
                    raise KeyError(token)
            except (KeyError, IndexError, ValueError) as exc:
                raise EvidenceError("pointer_missing", pointer) from exc
    if isinstance(current, (dict, list)):
        raise EvidenceError("fact_not_scalar", pointer)
    return current


def _iso_day(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise EvidenceError("date_invalid", field)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise EvidenceError("date_invalid", field) from exc
    if parsed.isoformat() != value:
        raise EvidenceError("date_invalid", field)
    return value


def _build_source_catalog(root: Path, source_path: str) -> dict[str, Fact]:
    raw, document, digest = _read_source(root, source_path)
    del raw
    as_of = _iso_day(document.get("date"), f"{source_path}:date")
    facts: dict[str, Fact] = {}
    for fact_id, spec in FACT_SPECS.items():
        if spec.source_path != source_path:
            continue
        try:
            value = _pointer(document, spec.pointer)
        except EvidenceError as exc:
            if source_path == RECEIPTS_SOURCE and exc.code == "pointer_missing":
                # A channel can have fewer than the finite display allowance.
                # The corresponding plan then fails closed at fact lookup.
                continue
            raise
        facts[fact_id] = Fact(
            fact_id=fact_id,
            source_path=spec.source_path,
            pointer=spec.pointer,
            value=value,
            value_kind=spec.value_kind,
            unit=spec.unit,
            denominator=spec.denominator,
            as_of=as_of,
            citation=spec.citation,
            source_sha256=digest,
        )
    return facts


def build_latest_catalog(root: Path = ROOT) -> dict[str, Fact]:
    """Build the finite latest-reading fact catalog from one payload vintage."""
    return _build_source_catalog(root, LATEST_SOURCE)


def build_receipt_catalog(root: Path = ROOT) -> dict[str, Fact]:
    """Build only displayed receipt-entry facts, never pool-quality claims."""
    return _build_source_catalog(root, RECEIPTS_SOURCE)


def _verify_fact_snapshot(
    fact: Fact,
    document: Mapping[str, Any],
    digest: str,
) -> None:
    spec = FACT_SPECS.get(fact.fact_id)
    if spec is None:
        raise EvidenceError("fact_unregistered", fact.fact_id)
    registered = (
        spec.source_path,
        spec.pointer,
        spec.value_kind,
        spec.unit,
        spec.denominator,
        spec.citation,
    )
    supplied = (
        fact.source_path,
        fact.pointer,
        fact.value_kind,
        fact.unit,
        fact.denominator,
        fact.citation,
    )
    if supplied != registered:
        raise EvidenceError("fact_metadata_mismatch", fact.fact_id)
    if digest != fact.source_sha256:
        raise EvidenceError("source_digest_mismatch", fact.fact_id)
    source_day = _iso_day(document.get("date"), fact.fact_id)
    if source_day != fact.as_of:
        raise EvidenceError("fact_date_mismatch", fact.fact_id)
    actual = _pointer(document, fact.pointer)
    if type(actual) is not type(fact.value) or actual != fact.value:
        raise EvidenceError("fact_value_mismatch", fact.fact_id)
    if fact.value_kind == "date":
        if fact.value != fact.as_of:
            raise EvidenceError("fact_date_mismatch", fact.fact_id)
        return
    if fact.value_kind == "number":
        numeric_value = fact.value
        if isinstance(numeric_value, bool) or not isinstance(
            numeric_value, (int, float)
        ):
            raise EvidenceError("fact_type_mismatch", fact.fact_id)
        if not math.isfinite(float(numeric_value)):
            raise EvidenceError("fact_nonfinite", fact.fact_id)
        if not 0 <= float(numeric_value) <= 100:
            raise EvidenceError("fact_range_invalid", fact.fact_id)
        return
    if not isinstance(fact.value, str):
        raise EvidenceError("fact_type_mismatch", fact.fact_id)
    if any(ord(char) < 32 and char not in "\t\n\r" for char in fact.value):
        raise EvidenceError("fact_text_invalid", fact.fact_id)
    if fact.value_kind == "compact_date":
        if not re.fullmatch(r"\d{8}", fact.value):
            raise EvidenceError("fact_date_mismatch", fact.fact_id)
        try:
            compact = date(
                int(fact.value[:4]), int(fact.value[4:6]), int(fact.value[6:])
            ).isoformat()
        except ValueError as exc:
            raise EvidenceError("fact_date_mismatch", fact.fact_id) from exc
        if compact != fact.as_of:
            raise EvidenceError("fact_date_mismatch", fact.fact_id)
    elif fact.value_kind == "title":
        if not fact.value.strip() or len(fact.value) > 500:
            raise EvidenceError("fact_text_invalid", fact.fact_id)
    elif fact.value_kind == "domain":
        if (
            not fact.value
            or len(fact.value) > 253
            or any(char.isspace() for char in fact.value)
        ):
            raise EvidenceError("fact_domain_invalid", fact.fact_id)
    elif fact.value_kind == "url":
        parsed = urlparse(fact.value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise EvidenceError("fact_url_invalid", fact.fact_id)
    elif fact.value_kind == "lane":
        if fact.value not in {"corpus", "corpus-extended", "artlist"}:
            raise EvidenceError("fact_lane_invalid", fact.fact_id)


def verify_fact(fact: Fact, root: Path = ROOT) -> None:
    """Verify one fact against one exact source-byte snapshot."""
    _, document, digest = _read_source(root, fact.source_path)
    _verify_fact_snapshot(fact, document, digest)


def verify_facts(facts: Sequence[Fact], root: Path = ROOT) -> None:
    """Verify all facts with one read per source, preventing cross-read races."""
    snapshots: dict[str, tuple[dict[str, Any], str]] = {}
    for fact in facts:
        if fact.source_path not in snapshots:
            _, document, digest = _read_source(root, fact.source_path)
            snapshots[fact.source_path] = (document, digest)
        document, digest = snapshots[fact.source_path]
        _verify_fact_snapshot(fact, document, digest)


_PLAN_FIELDS = {"schema_version", "intent", "template_id", "fact_ids"}
_TEMPLATE_IDS = {
    "latest_headline",
    "channel_reading",
    "channel_comparison",
    "instrument_scope",
    "receipt_evidence",
    "current_receipt_evidence",
    "refusal_evidence_unavailable",
    "refusal_forbidden",
    "refusal_unsupported",
}


def parse_plan(raw: Mapping[str, object]) -> Plan:
    """Parse a model-facing plan with no free-text or literal-value channel."""
    if set(raw) != _PLAN_FIELDS:
        raise EvidenceError("plan_fields_invalid", repr(sorted(raw)))
    if raw.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise EvidenceError("plan_version_invalid", repr(raw.get("schema_version")))
    intent = raw.get("intent")
    template_id = raw.get("template_id")
    fact_ids = raw.get("fact_ids")
    if not isinstance(intent, str) or not intent or len(intent) > 64:
        raise EvidenceError("plan_intent_invalid", repr(intent))
    if not isinstance(template_id, str) or template_id not in _TEMPLATE_IDS:
        raise EvidenceError("plan_template_invalid", repr(template_id))
    if not isinstance(fact_ids, list) or len(fact_ids) > 32:
        raise EvidenceError("plan_facts_invalid", repr(fact_ids))
    if any(not isinstance(item, str) or len(item) > 96 for item in fact_ids):
        raise EvidenceError("plan_facts_invalid", repr(fact_ids))
    if len(set(fact_ids)) != len(fact_ids):
        raise EvidenceError("plan_facts_duplicate", repr(fact_ids))
    return Plan(PLAN_SCHEMA_VERSION, intent, template_id, tuple(fact_ids))


_CHANNEL_PATTERNS: dict[str, tuple[str, ...]] = {
    "pakistan_west": (r"\bpakistan\b", r"\bwestern border\b", r"\bloc\b"),
    "china_east": (r"\bchina\b", r"\beastern border\b", r"\blac\b"),
    "gulf_energy": (r"\bgulf\b", r"\benergy security\b", r"\bhormuz\b"),
    "us_trade": (r"\bus trade\b", r"\btrade policy\b", r"\btariffs?\b"),
    "shipping": (r"\bshipping\b", r"\bchokepoints?\b", r"\bsuez\b"),
}

_FORBIDDEN = re.compile(
    r"\b(forecast|predict|will|should|buy|sell|hedge|advice|investment|"
    r"price target|trade recommendation)\b",
    re.IGNORECASE,
)


def _channel_fact_ids(channel: str) -> tuple[str, str]:
    base = f"latest.channels.{channel}"
    return f"{base}.label", f"{base}.score7"


def _receipt_article_fact_ids(channel: str) -> tuple[str, ...]:
    ids: list[str] = []
    for index in range(RECEIPT_ENTRIES_PER_ANSWER):
        base = f"receipts.channels.{channel}.displayed.{index}"
        ids.extend(
            f"{base}.{field}" for field in ("date", "title", "domain", "url", "lane")
        )
    return tuple(ids)


def _receipt_fact_ids(channel: str) -> tuple[str, ...]:
    return (
        "receipts.date",
        f"receipts.channels.{channel}.label",
        *_receipt_article_fact_ids(channel),
    )


def _current_receipt_fact_ids(channel: str) -> tuple[str, ...]:
    base = f"latest.channels.{channel}"
    return (
        "latest.date",
        f"{base}.label",
        f"{base}.score",
        "latest.definition",
        "receipts.date",
        *_receipt_article_fact_ids(channel),
    )


def plan_question(question: str) -> Plan:
    """Deterministic planner used until a separately reviewed classifier exists."""
    normalized = " ".join(question.strip().lower().split())
    if not normalized or len(normalized) > 500:
        return Plan(PLAN_SCHEMA_VERSION, "refuse", "refusal_unsupported", ())
    if _FORBIDDEN.search(normalized):
        return Plan(PLAN_SCHEMA_VERSION, "refuse", "refusal_forbidden", ())

    channels = [
        channel for channel, patterns in _CHANNEL_PATTERNS.items()
        if any(re.search(pattern, normalized) for pattern in patterns)
    ]
    receipt_request = bool(
        re.search(r"\b(evidence|headlines?|sources?|articles?|receipts?|why)\b", normalized)
    )
    current_request = bool(re.search(r"\b(current|today|why|score)\b", normalized))
    comparison = bool(re.search(r"\b(compare|versus|vs\.?|higher|lower)\b", normalized))
    if comparison and len(channels) == 2:
        first_label, first_score = _channel_fact_ids(channels[0])
        second_label, second_score = _channel_fact_ids(channels[1])
        return Plan(
            PLAN_SCHEMA_VERSION,
            "compare_channels",
            "channel_comparison",
            (
                "latest.date",
                first_label,
                first_score,
                second_label,
                second_score,
                "latest.definition",
            ),
        )
    if len(channels) == 1 and receipt_request:
        channel = channels[0]
        if current_request:
            return Plan(
                PLAN_SCHEMA_VERSION,
                "current_receipt_evidence",
                "current_receipt_evidence",
                _current_receipt_fact_ids(channel),
            )
        return Plan(
            PLAN_SCHEMA_VERSION,
            "receipt_evidence",
            "receipt_evidence",
            _receipt_fact_ids(channel),
        )
    if len(channels) == 1:
        label, score = _channel_fact_ids(channels[0])
        return Plan(
            PLAN_SCHEMA_VERSION,
            "channel_reading",
            "channel_reading",
            ("latest.date", label, score, "latest.definition"),
        )
    if len(channels) > 1:
        return Plan(PLAN_SCHEMA_VERSION, "refuse", "refusal_unsupported", ())
    if re.search(r"\b(latest|headline|composite|overall|current|today)\b", normalized):
        return Plan(
            PLAN_SCHEMA_VERSION,
            "latest_headline",
            "latest_headline",
            ("latest.date", "latest.composite7", "latest.definition"),
        )
    if re.search(r"\b(methodology|scope|measure|definition|igrm)\b", normalized):
        return Plan(
            PLAN_SCHEMA_VERSION,
            "instrument_scope",
            "instrument_scope",
            ("latest.date", "latest.definition"),
        )
    return Plan(PLAN_SCHEMA_VERSION, "refuse", "refusal_unsupported", ())


def _validate_plan_shape(plan: Plan) -> None:
    if plan.schema_version != PLAN_SCHEMA_VERSION:
        raise EvidenceError("plan_version_invalid", plan.schema_version)
    if plan.template_id not in _TEMPLATE_IDS:
        raise EvidenceError("plan_template_invalid", plan.template_id)
    if plan.template_id.startswith("refusal_"):
        if plan.fact_ids or plan.intent != "refuse":
            raise EvidenceError("plan_shape_invalid", plan.template_id)
        return
    if plan.template_id == "latest_headline":
        headline_facts = ("latest.date", "latest.composite7", "latest.definition")
        if plan.intent != "latest_headline" or plan.fact_ids != headline_facts:
            raise EvidenceError("plan_shape_invalid", plan.template_id)
        return
    if plan.template_id == "instrument_scope":
        scope_facts = ("latest.date", "latest.definition")
        if plan.intent != "instrument_scope" or plan.fact_ids != scope_facts:
            raise EvidenceError("plan_shape_invalid", plan.template_id)
        return
    if plan.template_id == "channel_reading":
        if plan.intent != "channel_reading" or len(plan.fact_ids) != 4:
            raise EvidenceError("plan_shape_invalid", plan.template_id)
        date_id, label_id, score_id, scope_id = plan.fact_ids
        if date_id != "latest.date" or scope_id != "latest.definition":
            raise EvidenceError("plan_shape_invalid", plan.template_id)
        if not label_id.endswith(".label") or score_id != label_id[:-6] + ".score7":
            raise EvidenceError("plan_shape_invalid", plan.template_id)
        return
    if plan.template_id == "channel_comparison":
        if plan.intent != "compare_channels" or len(plan.fact_ids) != 6:
            raise EvidenceError("plan_shape_invalid", plan.template_id)
        date_id, label_a, score_a, label_b, score_b, scope_id = plan.fact_ids
        valid = (
            date_id == "latest.date"
            and scope_id == "latest.definition"
            and label_a.endswith(".label")
            and score_a == label_a[:-6] + ".score7"
            and label_b.endswith(".label")
            and score_b == label_b[:-6] + ".score7"
            and label_a != label_b
        )
        if not valid:
            raise EvidenceError("plan_shape_invalid", plan.template_id)
        return
    if plan.template_id == "receipt_evidence":
        valid = plan.intent == "receipt_evidence" and any(
            plan.fact_ids == _receipt_fact_ids(channel) for channel in CHANNELS
        )
        if not valid:
            raise EvidenceError("plan_shape_invalid", plan.template_id)
        return
    if plan.template_id == "current_receipt_evidence":
        valid = plan.intent == "current_receipt_evidence" and any(
            plan.fact_ids == _current_receipt_fact_ids(channel)
            for channel in CHANNELS
        )
        if not valid:
            raise EvidenceError("plan_shape_invalid", plan.template_id)
        return
    raise EvidenceError("plan_shape_invalid", plan.template_id)


def _text(fact: Fact) -> str:
    if not isinstance(fact.value, str):
        raise EvidenceError("fact_type_mismatch", fact.fact_id)
    return fact.value


def _number(fact: Fact) -> float:
    value = fact.value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError("fact_type_mismatch", fact.fact_id)
    return float(value)


def _displayed_receipt_entries(
    facts: Sequence[Fact], start: int
) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    width = 5
    for offset in range(start, len(facts), width):
        group = facts[offset:offset + width]
        if len(group) != width:
            raise EvidenceError("plan_shape_invalid", "receipt entry width")
        # date, title, domain, URL and lane were all verified. Bind the
        # displayed publisher label to the actual URL host as well.
        title, domain, url = _text(group[1]), _text(group[2]), _text(group[3])
        hostname = (urlparse(url).hostname or "").lower().rstrip(".")
        normalized_domain = domain.lower().rstrip(".")
        if hostname != normalized_domain and not hostname.endswith(
            "." + normalized_domain
        ):
            raise EvidenceError("receipt_domain_url_mismatch", group[3].fact_id)
        entries.append((title, domain))
    return entries


def _evidence(facts: Sequence[Fact]) -> tuple[dict[str, Any], ...]:
    return tuple({
        "fact_id": fact.fact_id,
        "value": fact.value,
        "source": fact.source_path,
        "pointer": fact.pointer,
        "source_sha256": fact.source_sha256,
        "as_of": fact.as_of,
        "unit": fact.unit,
        "denominator": fact.denominator,
        "citation": fact.citation,
    } for fact in facts)


def render_plan(
    plan: Plan,
    catalog: Mapping[str, Fact],
    root: Path = ROOT,
) -> Answer:
    """Verify a plan and render it without incorporating user or model prose."""
    _validate_plan_shape(plan)
    if plan.template_id == "refusal_forbidden":
        return Answer(
            ANSWER_SCHEMA_VERSION,
            "refused",
            "forecast_or_advice",
            "IGRM describes press salience. It does not provide forecasts, "
            "trading recommendations, hedging advice, or price direction.",
            None,
            plan.template_id,
            (),
            (),
        )
    if plan.template_id == "refusal_unsupported":
        return Answer(
            ANSWER_SCHEMA_VERSION,
            "refused",
            "unsupported_question",
            "This evidence-locked assistant can currently report the latest "
            "headline, a channel reading, a two-channel comparison, displayed "
            "receipt evidence, or the instrument's scope. It refuses "
            "questions outside those facts.",
            None,
            plan.template_id,
            (),
            (),
        )

    try:
        facts = [catalog[fact_id] for fact_id in plan.fact_ids]
    except KeyError as exc:
        raise EvidenceError("fact_missing", str(exc)) from exc
    verify_facts(facts, root)
    as_of_values = {fact.as_of for fact in facts}
    if len(as_of_values) != 1:
        raise EvidenceError("date_join_mismatch", repr(sorted(as_of_values)))
    as_of = as_of_values.pop()

    if plan.template_id == "latest_headline":
        score = _number(facts[1])
        text = (
            f"The latest completed-news-day IGRM headline is {score:.1f} "
            f"on {as_of}. It is a 7-day press-salience percentile, not a "
            "probability or risk forecast."
        )
    elif plan.template_id == "channel_reading":
        label = _text(facts[1])
        score = _number(facts[2])
        text = (
            f"{label}'s latest 7-day press-salience percentile is "
            f"{score:.1f} on {as_of}. This is a within-channel historical "
            "rank, not a probability or forecast."
        )
    elif plan.template_id == "channel_comparison":
        label_a, score_a = _text(facts[1]), _number(facts[2])
        label_b, score_b = _text(facts[3]), _number(facts[4])
        difference = abs(score_a - score_b)
        if score_a == score_b:
            relation = "the readings were equal"
        else:
            higher = label_a if score_a > score_b else label_b
            relation = f"{higher} was higher by {difference:.1f} points"
        text = (
            f"On {as_of}, {label_a} was {score_a:.1f} and {label_b} was "
            f"{score_b:.1f}; {relation}. These are separate within-channel "
            "press-salience percentiles, not comparable probabilities of risk."
        )
    elif plan.template_id == "receipt_evidence":
        label = _text(facts[1])
        entries = _displayed_receipt_entries(facts, 2)
        rendered = "; ".join(
            f"“{title}” ({domain})" for title, domain in entries
        )
        text = (
            f"The latest available displayed receipt entries for {label} are "
            f"dated {as_of}: {rendered}. These {len(entries)} entries are "
            "presentation evidence, not a complete article set, a source-"
            "quality statistic, or the score denominator."
        )
    elif plan.template_id == "current_receipt_evidence":
        label = _text(facts[1])
        score = _number(facts[2])
        entries = _displayed_receipt_entries(facts, 5)
        rendered = "; ".join(
            f"“{title}” ({domain})" for title, domain in entries
        )
        text = (
            f"The completed-day press-salience tape for {label} was "
            f"{score:.1f} on {as_of}. Same-day displayed receipt entries: "
            f"{rendered}. These {len(entries)} links are not a complete score "
            "denominator or a causal explanation of the reading."
        )
    elif plan.template_id == "instrument_scope":
        text = _text(facts[1])
    else:  # pragma: no cover - guarded by _validate_plan_shape
        raise EvidenceError("plan_template_invalid", plan.template_id)

    return Answer(
        ANSWER_SCHEMA_VERSION,
        "answered",
        None,
        text,
        as_of,
        plan.template_id,
        plan.fact_ids,
        _evidence(facts),
    )


def answer_plan(plan: Plan, root: Path = ROOT) -> Answer:
    """Load only the plan's registered sources, then verify and render it."""
    if plan.template_id.startswith("refusal_"):
        return render_plan(plan, {}, root)
    try:
        catalog: dict[str, Fact] = {}
        if any(fact_id.startswith("latest.") for fact_id in plan.fact_ids):
            catalog.update(build_latest_catalog(root))
        if any(fact_id.startswith("receipts.") for fact_id in plan.fact_ids):
            catalog.update(build_receipt_catalog(root))
        return render_plan(plan, catalog, root)
    except EvidenceError as exc:
        if plan.template_id not in {"receipt_evidence", "current_receipt_evidence"}:
            raise
        if exc.code == "date_join_mismatch":
            code = "evidence_date_mismatch"
            text = (
                "The current score and available receipt evidence are not "
                "from the same completed news day, so the assistant will not "
                "present the articles as evidence for that score."
            )
        else:
            code = "evidence_unavailable"
            text = (
                "Receipt evidence could not be verified against its registered "
                "source facts, so no headline or link is displayed."
            )
        return Answer(
            ANSWER_SCHEMA_VERSION,
            "refused",
            code,
            text,
            None,
            "refusal_evidence_unavailable",
            (),
            (),
        )


def answer_question(question: str, root: Path = ROOT) -> Answer:
    return answer_plan(plan_question(question), root)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run the local evidence-locked IGRM answer core."
    )
    parser.add_argument("question", help="A latest-reading or scope question")
    args = parser.parse_args(argv)
    print(json.dumps(answer_question(args.question).to_dict(), indent=2))


if __name__ == "__main__":
    main()
