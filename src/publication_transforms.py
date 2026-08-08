"""Small registered transformations for evidence-bundle publication.

This file is content-hashed by governance/transformation_registry.json. Any
change is therefore a governed transformation-version change, not a quiet code
refactor.
"""

from __future__ import annotations

from typing import Union

JsonScalar = Union[str, int, float, bool, None]


def direct_registered_fact(value: JsonScalar) -> JsonScalar:
    """Return one already-verified scalar without interpretation."""

    return value
