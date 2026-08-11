"""The release wrapper must push the exact commit it gates."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHIP = (ROOT / "scripts" / "ship.sh").read_text(encoding="utf-8")


def test_ship_pushes_the_gated_head_not_an_unrelated_local_branch() -> None:
    # --publish since 2026-08-11: ship.sh was subject to the publish deadlock
    # too, so while igrm.in served stale payloads it could not push anything --
    # including the commit fixing that deadlock. It still gates the committed
    # tree; only already-served-site assertions are excluded.
    assert "bash scripts/gate.sh --publish" in SHIP
    assert "git push origin HEAD:main" in SHIP
    assert "git push origin main" not in SHIP
