"""The fast canonical encoder must be byte-identical to the one it replaced.

`_typed_canonical_bytes` was rewritten on 2026-08-10 from a join-per-
container form (which re-copied every descendant's bytes once per ancestor
level; 76.6M recursive calls in the registry test alone) to a single
downward accumulator. Every sealed digest in the repository binds this
encoding, and docs/typed-canonical.js implements it independently -- so
the rewrite is only safe if it is not a change at all, byte for byte.

This file freezes the ORIGINAL implementation verbatim as the reference
and drives both over a corpus chosen to hit every encoding branch and
every refusal, plus a randomized structural fuzz. If the fast path ever
diverges by one byte or one error code, this fails before any digest
does.
"""
from __future__ import annotations

import hashlib
import math
import random
import string
import struct

import pytest
from src import event_ledger as el

MAX_SAFE = el.MAX_SAFE_JSON_INTEGER


def _reference(value: object) -> bytes:
    """The pre-2026-08-10 implementation, kept verbatim (join form)."""
    if value is None:
        return b"n;"
    if isinstance(value, bool):
        return b"b1;" if value else b"b0;"
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number) or (
            number.is_integer() and abs(number) > MAX_SAFE
        ):
            raise el.EventLedgerError("typed_canonical_number_invalid")
        return b"d" + struct.pack(">d", number).hex().encode("ascii") + b";"
    if isinstance(value, str):
        try:
            encoded = value.encode("utf-8")
        except UnicodeEncodeError:
            raise el.EventLedgerError("typed_canonical_string_invalid") from None
        return (b"s" + str(len(encoded)).encode("ascii") + b":"
                + encoded.hex().encode("ascii") + b";")
    if isinstance(value, list):
        return (b"a" + str(len(value)).encode("ascii") + b":"
                + b"".join(_reference(item) for item in value) + b";")
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise el.EventLedgerError("typed_canonical_object_key_invalid")
        try:
            keys = sorted(value, key=lambda key: key.encode("utf-8"))
        except UnicodeEncodeError:
            raise el.EventLedgerError("typed_canonical_string_invalid") from None
        return (b"o" + str(len(keys)).encode("ascii") + b":"
                + b"".join(_reference(key) + _reference(value[key])
                           for key in keys) + b";")
    raise el.EventLedgerError("typed_canonical_type_invalid")


CORPUS = [
    None, True, False,
    0, 1, -1, 0.0, -0.0, 1.0, 1.5, -273.15,
    MAX_SAFE, -MAX_SAFE, float(MAX_SAFE),
    1e-308, 5e-324,
    "", "a", "hello world", "üñïçödé ☃ \U0001F600", "\x00\x7f",
    "क्षेत्रीय जोखिम",  # the site's own script family
    [], [1, 2, 3], [[]], [None, True, "x", 1.5, [{"k": []}]],
    {}, {"a": 1}, {"b": 2, "a": 1}, {"": None},
    {"nested": {"deep": [{"deeper": [0.1, {"deepest": "🪷"}]}]}},
    # Key ordering is by UTF-8 bytes, not code points or locale.
    {"é": 1, "z": 2, "a": 3, "è": 4},
]


def test_every_corpus_value_encodes_byte_identically() -> None:
    for value in CORPUS:
        assert el._typed_canonical_bytes(value) == _reference(value), value


def test_randomized_structures_encode_byte_identically() -> None:
    rng = random.Random(20260810)

    def build(depth: int) -> object:
        kind = rng.randrange(7 if depth < 4 else 5)
        if kind == 0:
            return None
        if kind == 1:
            return rng.random() * rng.choice([1, -1, 1e6, 1e-6])
        if kind == 2:
            return rng.randrange(-MAX_SAFE, MAX_SAFE)
        if kind == 3:
            return "".join(rng.choice(string.printable) for _ in range(rng.randrange(0, 12)))
        if kind == 4:
            return rng.choice([True, False])
        if kind == 5:
            return [build(depth + 1) for _ in range(rng.randrange(0, 5))]
        return {f"k{i}": build(depth + 1) for i in range(rng.randrange(0, 5))}

    for _ in range(300):
        value = build(0)
        assert el._typed_canonical_bytes(value) == _reference(value)


@pytest.mark.parametrize("bad, code", [
    (float("nan"), "typed_canonical_number_invalid"),
    (float("inf"), "typed_canonical_number_invalid"),
    (MAX_SAFE + 1, "typed_canonical_number_invalid"),
    # Huge floats are mathematically integers (is_integer() is True), so
    # the profile refuses DBL_MAX as an out-of-safe-range integer. Both
    # implementations agree; a first draft of this file misfiled it as
    # encodable.
    (1.7976931348623157e308, "typed_canonical_number_invalid"),
    ({1: "x"}, "typed_canonical_object_key_invalid"),
    ("\ud800", "typed_canonical_string_invalid"),      # lone surrogate value
    ({"\ud800": 1}, "typed_canonical_string_invalid"),  # lone surrogate key
    (object(), "typed_canonical_type_invalid"),
    (b"bytes", "typed_canonical_type_invalid"),
])
def test_refusals_match_the_reference(bad: object, code: str) -> None:
    with pytest.raises(el.EventLedgerError) as fast:
        el._typed_canonical_bytes(bad)
    assert fast.value.code == code
    with pytest.raises(el.EventLedgerError) as ref:
        _reference(bad)
    assert str(ref.value) == code


def test_sha256_helper_matches_the_bytes_path() -> None:
    for value in CORPUS:
        assert el._typed_canonical_sha256(value) == hashlib.sha256(
            el._typed_canonical_bytes(value)).hexdigest()
