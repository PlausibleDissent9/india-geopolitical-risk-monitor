"""One result, many audiences, and no audience told something different.

WHY THIS EXISTS
The same analytical result is shown to a researcher, a board, a newsroom, an
API client and a reader. Every one of those views is shorter than the last,
and shortening is where claims quietly change: a denominator disappears, an
interval becomes a point, a refusal becomes a blank, a limitation is dropped
because it did not fit.

The rule this module enforces is narrow on purpose:

    An audience profile MAY omit a clause, and MAY use a shorter registered
    rendering. It MAY NEVER change what a clause says.

"What a clause says" is the protected field set in
``governance/analytical_clause_contract.json`` -- value, unit, denominator,
observed period, epistemic type, uncertainty, missingness, citation, rights
state and proof binding. Those are compared across roles by typed canonical
digest, the same primitive the signed releases use, so a comparison cannot
drift between Python and a browser.

WHAT IT DOES NOT CLAIM
Cross-role agreement is not accuracy. If a clause is wrong, this module keeps
it consistently wrong in seven places. It decides one thing: that the short
view and the long view are the same claim. That is worth having precisely
because it is the property nobody checks by reading.

Slice 1 is synthetic and contract-only. It writes no payload, publishes no
route, and makes no production, utility or adoption claim.

  python -m src.analytical_clause --check    verify the contract loads and
                                             its digest matches
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn, cast

from . import event_ledger

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_RELATIVE = Path("governance") / "analytical_clause_contract.json"
CONTRACT_PATH = ROOT / CONTRACT_RELATIVE


class AnalyticalClauseError(ValueError):
    """Stable fail-closed analytical clause refusal."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise AnalyticalClauseError(code, detail)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate JSON keys instead of letting the last one win.

    A document carrying "value" twice is not a document with one value; it is
    two claims and a parser preference.
    """
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("clause_duplicate_id", key)
        result[key] = value
    return result


def load_contract(path: Path = CONTRACT_PATH) -> tuple[dict[str, Any], str]:
    """Return the registered contract and the sha256 of its exact bytes."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AnalyticalClauseError("clause_contract_digest_mismatch", str(path)) from exc
    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, ValueError) as exc:
        raise AnalyticalClauseError("clause_contract_digest_mismatch", str(path)) from exc
    if not isinstance(document, dict):
        _fail("clause_contract_digest_mismatch", str(path))
    return document, hashlib.sha256(raw).hexdigest()


def _typed_sha(value: object) -> str:
    try:
        return event_ledger._typed_canonical_sha256(value)
    except event_ledger.EventLedgerError as exc:
        raise AnalyticalClauseError("clause_protected_field_divergence", str(exc)) from exc


def _clause_id(clause: Mapping[str, Any]) -> str:
    clause_id = clause.get("clause_id")
    if not isinstance(clause_id, str) or not clause_id:
        _fail("clause_unknown_id_in_role", repr(clause_id))
    return clause_id


def protected_digest(clause: Mapping[str, Any], contract: Mapping[str, Any]) -> str:
    """Digest of exactly the protected fields, in registered order.

    Everything outside the protected set -- rendering length, prose, ordering
    hints -- is deliberately excluded, because those are what a role is
    allowed to vary.
    """
    fields = cast(Sequence[str], contract["protected_fields"])
    payload = []
    for name in fields:
        if name not in clause:
            _fail("clause_protected_field_missing", f"{_clause_id(clause)}.{name}")
        payload.append([name, clause[name]])
    return _typed_sha(payload)


def validate_clause(clause: Mapping[str, Any], contract: Mapping[str, Any]) -> None:
    """Structural checks on one compiled clause, before any role sees it."""
    clause_id = _clause_id(clause)
    kinds = cast(Mapping[str, Any], contract["clause_kinds"])
    kind = clause.get("kind")
    if kind not in kinds:
        _fail("clause_kind_unregistered", f"{clause_id}: {kind!r}")
    if clause.get("epistemic_type") not in contract["epistemic_types"]:
        _fail("clause_epistemic_type_unregistered",
              f"{clause_id}: {clause.get('epistemic_type')!r}")
    missingness = clause.get("missingness")
    if missingness not in contract["missingness_states"]:
        _fail("clause_missingness_unregistered", f"{clause_id}: {missingness!r}")

    # A value and its missingness must agree. "source_blank" carrying a number
    # is the coercion this project refuses everywhere else, and a zero
    # standing in for an absence is the specific lie.
    if missingness == "present" and clause.get("value") is None:
        _fail("clause_value_absent_despite_presence", clause_id)
    if missingness != "present" and clause.get("value") is not None:
        _fail("clause_value_present_despite_missingness",
              f"{clause_id}: {missingness}")
    protected_digest(clause, contract)


def compile_clauses(
    clauses: Sequence[Mapping[str, Any]], contract: Mapping[str, Any]
) -> dict[str, str]:
    """Validate the compiled clause set and return clause_id -> digest."""
    compiled: dict[str, str] = {}
    for clause in clauses:
        validate_clause(clause, contract)
        clause_id = _clause_id(clause)
        if clause_id in compiled:
            _fail("clause_duplicate_id", clause_id)
        compiled[clause_id] = protected_digest(clause, contract)
    return compiled


def _mandatory_ids(
    clauses: Sequence[Mapping[str, Any]], contract: Mapping[str, Any]
) -> set[str]:
    kinds = cast(Mapping[str, Mapping[str, Any]], contract["clause_kinds"])
    return {
        _clause_id(clause)
        for clause in clauses
        if kinds[cast(str, clause["kind"])]["never_omittable"]
    }


def validate_role_view(
    role: str,
    view: Sequence[Mapping[str, Any]],
    clauses: Sequence[Mapping[str, Any]],
    contract: Mapping[str, Any],
) -> dict[str, str]:
    """Check one role's view against the compiled clause set.

    Returns clause_id -> protected digest for the role, so callers can compare
    roles without recomputing.
    """
    if role not in contract["roles"]:
        _fail("clause_role_unregistered", role)
    compiled = compile_clauses(clauses, contract)
    mandatory = _mandatory_ids(clauses, contract)

    seen: dict[str, str] = {}
    for clause in view:
        clause_id = _clause_id(clause)
        if clause_id not in compiled:
            _fail("clause_unknown_id_in_role", f"{role}: {clause_id}")
        if clause_id in seen:
            _fail("clause_duplicate_id", f"{role}: {clause_id}")
        length = clause.get("rendering_length")
        if length not in contract["rendering_lengths"]:
            _fail("clause_rendering_length_unregistered", f"{role}: {length!r}")
        digest = protected_digest(clause, contract)
        if digest != compiled[clause_id]:
            _fail("clause_protected_field_divergence", f"{role}: {clause_id}")
        seen[clause_id] = digest

    missing = sorted(mandatory - set(seen))
    if missing:
        _fail("clause_mandatory_omitted", f"{role}: {', '.join(missing)}")
    return seen


def cross_role_invariant(views: Mapping[str, Mapping[str, str]]) -> dict[str, Any]:
    """The property this module exists for.

    For every clause carried by more than one role, the protected digest must
    be identical. Where roles differ, the difference must be omission and
    nothing else.
    """
    everywhere: dict[str, str] = {}
    for role, digests in sorted(views.items()):
        for clause_id, digest in sorted(digests.items()):
            if clause_id not in everywhere:
                everywhere[clause_id] = digest
            elif everywhere[clause_id] != digest:
                _fail("clause_protected_field_divergence",
                      f"{clause_id} differs in {role}")
    return {
        "clause_ids": sorted(everywhere),
        "roles": sorted(views),
        "shared_clause_digest_sha256": _typed_sha(
            [[clause_id, everywhere[clause_id]] for clause_id in sorted(everywhere)]
        ),
        "omitted_by_role": {
            role: sorted(set(everywhere) - set(views[role])) for role in sorted(views)
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify the registered contract loads and hash it")
    parser.parse_args()
    contract, digest = load_contract()
    print(f"[clause] contract {contract['contract_id']} sha256={digest}")
    print(f"[clause] {len(contract['roles'])} roles, "
          f"{len(contract['protected_fields'])} protected fields, "
          f"{sum(1 for k in contract['clause_kinds'].values() if k['never_omittable'])}"
          " never-omittable kinds")


if __name__ == "__main__":
    main()
