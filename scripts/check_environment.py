"""Refuse CI or a local ship when installed packages differ from exact pins.

The committed gate intentionally skips ``pip install`` for speed. That is safe
only when its interpreter already contains the same directly declared
distributions CI installs. This check makes that precondition executable.
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REQUIREMENTS = (ROOT / "requirements.txt", ROOT / "requirements-dev.txt")
EXACT_PIN = re.compile(r"([A-Za-z0-9_.-]+)==([^\s;]+)")


class EnvironmentMismatch(ValueError):
    """The declared environment is not exact or is not installed."""


def required_pins(paths: Sequence[Path]) -> dict[str, str]:
    pins: dict[str, str] = {}
    errors: list[str] = []
    for path in paths:
        for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            requirement = raw.split("#", 1)[0].strip()
            if not requirement:
                continue
            match = EXACT_PIN.fullmatch(requirement)
            if match is None:
                errors.append(f"{path.name}:{line_number}: not an exact name==version pin")
                continue
            name, expected = match.groups()
            key = re.sub(r"[-_.]+", "-", name).lower()
            prior = pins.get(key)
            if prior is not None and prior != expected:
                errors.append(f"{name}: conflicting pins {prior} and {expected}")
            pins[key] = expected
    if errors:
        raise EnvironmentMismatch("; ".join(errors))
    return pins


def installed_mismatches(pins: dict[str, str]) -> list[str]:
    mismatches: list[str] = []
    for name, expected in sorted(pins.items()):
        try:
            actual = metadata.version(name)
        except metadata.PackageNotFoundError:
            mismatches.append(f"{name} missing (expected {expected})")
            continue
        if actual != expected:
            mismatches.append(f"{name}=={actual} installed (expected {expected})")
    return mismatches


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("requirements", nargs="*", type=Path)
    args = parser.parse_args(argv)
    paths = tuple(args.requirements) or DEFAULT_REQUIREMENTS
    try:
        pins = required_pins(paths)
    except (EnvironmentMismatch, OSError) as exc:
        parser.error(str(exc))
    mismatches = installed_mismatches(pins)
    if mismatches:
        parser.error(
            "environment differs from committed pins: "
            + "; ".join(mismatches)
            + ". Rebuild or synchronize the project virtual environment."
        )
    print(f"environment: {len(pins)} exact pins installed")


if __name__ == "__main__":
    main()
