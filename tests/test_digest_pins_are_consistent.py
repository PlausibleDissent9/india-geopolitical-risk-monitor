"""Every LIVE digest pin must match the bytes it names.

WHY THIS IS A TEST AND NOT JUST A SCRIPT
A stale pin does not announce itself. It surfaces later as a refusal code --
`view_contract_invalid`, `profile_bound_file_digest_mismatch`,
`scenario_proof_profile_digest_mismatch` -- inside whichever suite happens to
exercise that pin, naming the symptom and never the cause. On 2026-08-10 an
unfinished cascade produced 85 such failures across six suites and cost hours
of tracing. This test names the cause in one line.

Internal pin consistency is a property OF THE CANDIDATE, which is why it
belongs in the gate: a tree whose contracts no longer match the files they
name is broken now, independently of anything outside the repository. That is
the opposite of the live-site assertions removed from the publish gate in
98a0050, which described the already-served world and deadlocked publishing.

Frozen pins are exempt BY NAME, never by pattern -- see FROZEN_OWNERS in the
script. The inventory is locked below so a new exemption has to be added
deliberately, in the commit that introduces it, rather than appearing.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_digest_pins as pins  # noqa: E402

# Owners that have a generator, and the exact command that rewrites them.
# Owners are DISCOVERED, not registered, so this map is a courtesy rather
# than an inventory: an owner missing from it still fails, just without
# the shortcut. It exists because on 2026-08-17 the message said
# "re-derive the cascade" and named no command, and the manifest's only
# regenerator lived inside a step of morning.yml -- so the reader had to
# grep the workflows to find out how to repair a red that was refusing
# every lane's publish. Naming the cause without naming the cure still
# leaves the outage running.
#
# Entries are for files that actually CARRY pins and so can actually go
# stale. docs/data/security_integrity.json was in this map for one draft
# and removed: it has a regenerator, but it carries no pins, so it can
# never be a stale owner and listing it would have implied otherwise.
REGENERATORS: dict[str, str] = {
    "docs/data/public_api_byte_manifest.json":
        "PYTHONPATH=. python scripts/generate_public_api_byte_manifest.py",
}


def test_every_live_digest_pin_matches_the_bytes_it_names() -> None:
    result = pins.audit()
    lines = []
    for owner, key, target, _d, _a in result["stale"]:
        lines.append(f"  {owner}: {key} of {target}")
        if owner in REGENERATORS:
            lines.append(f"      regenerate with: {REGENERATORS[owner]}")
    assert result["stale"] == [], (
        "a contract, profile or registry no longer matches the file it pins. "
        "Re-derive the cascade to a fixpoint (replace only exact known-stale "
        "digests, recompute each rewritten file's own digest, repeat) -- or "
        "investigate, if no change should have moved these:\n"
        + "\n".join(lines))


def test_every_named_regenerator_exists() -> None:
    """A command that has been renamed away is worse than no command:
    it sends the reader of a red gate down a path that dead-ends."""
    missing = [
        cmd for cmd in REGENERATORS.values()
        if (script := _script_of(cmd)) and not (ROOT / script).exists()
    ]
    assert not missing, f"REGENERATORS names commands that no longer exist: {missing}"


def _script_of(cmd: str) -> str | None:
    """The repo-relative script path a command runs, if it names one.

    Only the `python scripts/x.py` form has a path to check; the
    `python -m pkg.mod` form is a module reference and is left alone.
    """
    for token in cmd.split():
        if token.endswith(".py"):
            return token
    return None


def test_the_frozen_exemption_list_is_an_inventory_lock() -> None:
    """A frozen pin records a moment that has passed: a registration pins the
    versions it ran against, a fixture pins the world its replay assumes, a
    completion record pins the artifact as delivered. Those must never be
    "fixed" -- doing so falsifies a record. Equally they must never grow
    silently, or this test becomes an ignore list."""
    assert set(pins.FROZEN_OWNERS) == {
        "validation/blind_audit_500/registration.json",
        "validation/precision_v3/registration.json",
        "design/igrm_max_launch_contract.json",
    }, ("the frozen-pin exemption list changed. Adding one is allowed, but it "
        "must be deliberate and carry its reason -- update this lock in the "
        "same commit, and never to a pattern or an inequality.")


def test_a_shadowing_fixture_resolves_to_its_own_copy_not_the_repos() -> None:
    """Pins resolve NEAREST BASE FIRST, and the ordering is load-bearing.

    The consequence_plan replay fixture ships its own schemas/ and governance/
    trees. Its registry pins "schemas/common.schema.json" meaning ITS copy. An
    earlier _resolve tried the repo root first and compared the repo's copy --
    silently verifying 18 pins against the wrong files, then reporting the
    fixture as drifted when it was consistent. The exemption that false
    positive earned excused a healthy file from checking, which is the worse
    half: a checker that has been taught to look away.
    """
    fixture = ROOT / "validation/consequence_plan/replay_fixture"
    owner = fixture / "governance" / "canonical_schema_registry.json"
    if not owner.is_file():
        return  # fixture reshaped; the audit assertions still cover the repo

    resolved = pins._resolve(owner, "schemas/common.schema.json")
    assert resolved is not None, "the fixture's own schema no longer resolves"
    assert resolved == fixture / "schemas" / "common.schema.json", (
        f"a shadowing fixture pin resolved to {resolved}, not to the "
        "fixture's own copy; root-first resolution has come back")
    assert resolved != ROOT / "schemas" / "common.schema.json"
    for owner, reason in pins.FROZEN_OWNERS.items():
        assert len(reason) > 20, f"{owner} is exempt without a stated reason"


def test_every_pin_names_a_file_that_exists() -> None:
    """A pin to a path that does not resolve verifies nothing while looking
    like a control. Fixtures pin their members relative to the fixture root,
    so resolution walks outward from the owner -- 24 pins were invisible to
    an earlier version of this that only tried the repo root."""
    result = pins.audit()
    assert result["missing"] == [], (
        "digest pins name paths that do not resolve:\n"
        + "\n".join(f"  {o} -> {t}" for o, t in result["missing"]))


def test_the_audit_actually_checks_a_meaningful_number_of_pins() -> None:
    """A verifier that silently stops finding pins passes forever. Pin the
    floor so a parsing regression fails loudly instead of reporting green."""
    result = pins.audit()
    assert result["checked"] >= 200, (
        f"only {result['checked']} pins were checked; the walker has probably "
        "stopped recognising a pin shape")
