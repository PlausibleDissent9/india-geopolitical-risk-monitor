"""Published exposure traversal from the deterministic shared Max world.

This is a synthetic L0 contract vector.  It is not a claim that a real event,
entity, source, right, dependency, or exposure exists.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_OUTPUT = ROOT / "docs" / "data" / "exposure_traversal_demo.json"


def build_demo() -> dict[str, Any]:
    """Return the traversal record that the published join actually certifies."""

    from src import max_state_join_fixture

    return max_state_join_fixture.build_published_artifacts().exposure_traversal


def main() -> None:
    PUBLIC_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_OUTPUT.write_text(
        json.dumps(build_demo(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(PUBLIC_OUTPUT)


if __name__ == "__main__":
    main()
