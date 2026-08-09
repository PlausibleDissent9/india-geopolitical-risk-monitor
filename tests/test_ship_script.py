"""The release wrapper must push the exact commit it gates."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHIP = (ROOT / "scripts" / "ship.sh").read_text(encoding="utf-8")


def test_ship_pushes_the_gated_head_not_an_unrelated_local_branch() -> None:
    assert "bash scripts/gate.sh --committed" in SHIP
    assert "git push origin HEAD:main" in SHIP
    assert "git push origin main" not in SHIP
