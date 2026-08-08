"""Regression locks for the OpenAPI 3.1 spec and the datasheet.

docs/openapi.json and docs/datasheet.md are derived documents: every
string in them comes from docs/data/api_contract.json, the universal
_meta constants, CITATION.cff, or committed markdown sources. These
tests hold the derivation to the same discipline as the contract's own
committed == generated lock -- with one tightening: the regeneration
runs inside a `git archive HEAD` extract, because this checkout is
shared with another agent whose uncommitted payload edits would
otherwise leak into the comparison and fail it for reasons not in HEAD.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SPEC_PATH = DOCS / "openapi.json"
CONTRACT_PATH = DOCS / "data" / "api_contract.json"
OUTPUTS = ("docs/openapi.json", "docs/datasheet.md")


def _spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def _contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def committed_tree(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """HEAD extracted to a temp dir: the committed surface, nothing else."""
    dest = tmp_path_factory.mktemp("committed")
    tar = dest / "head.tar"
    subprocess.run(["git", "archive", "HEAD", "-o", str(tar)],
                   cwd=ROOT, check=True)
    tree = dest / "tree"
    tree.mkdir()
    with tarfile.open(tar) as tf:
        try:
            tf.extractall(tree, filter="data")
        except TypeError:  # Python < 3.12 has no filter argument
            tf.extractall(tree)
    return tree


def test_the_spec_and_datasheet_match_their_generator(committed_tree: Path):
    """committed == regenerated-from-the-committed-surface, both files.

    Runs the extracted copy of the generator inside the extract, so the
    inputs (contract, payload shapes, CITATION.cff, markdown sources)
    and the outputs are all HEAD's -- the working tree never enters.
    """
    before = {rel: (committed_tree / rel).read_bytes() for rel in OUTPUTS}
    r = subprocess.run([sys.executable, "-m", "scripts.generate_openapi"],
                       cwd=committed_tree, capture_output=True, text=True)
    assert r.returncode == 0, f"generator failed: {r.stderr[-500:]}"
    for rel in OUTPUTS:
        after = (committed_tree / rel).read_bytes()
        assert before[rel] == after, (
            f"{rel} differs from what its generator produces from the "
            "committed surface. Update the source it derives from and "
            "regenerate (python -m scripts.generate_openapi) in the same "
            "commit -- a served description that disagrees with its "
            "inputs is worse than none.")


def test_every_contract_endpoint_appears_exactly_once():
    contract_paths = ["/" + e["path"] for e in _contract()["endpoints"]]
    assert len(contract_paths) == len(set(contract_paths)), (
        "the contract itself lists an endpoint twice")
    spec_paths = list(_spec()["paths"].keys())
    assert sorted(spec_paths) == sorted(contract_paths), (
        "spec paths and contract endpoints diverge: "
        f"only in spec {sorted(set(spec_paths) - set(contract_paths))}, "
        f"only in contract {sorted(set(contract_paths) - set(spec_paths))}")


def test_every_path_is_a_single_get():
    for path, item in _spec()["paths"].items():
        assert list(item.keys()) == ["get"], (
            f"{path} carries operations beyond GET: {list(item.keys())}. "
            "The data API is read-only files on Pages; any other verb is "
            "a promise nothing serves.")


def test_spec_version_equals_contract_version():
    spec, contract = _spec(), _contract()
    assert spec["info"]["version"] == contract["_meta"]["contract_version"], (
        f"spec info.version {spec['info']['version']} != contract "
        f"{contract['_meta']['contract_version']}; the spec would claim a "
        "different freeze than the contract it is derived from")


def test_the_spec_serves_from_igrm_in():
    assert _spec()["servers"] == [{"url": "https://igrm.in"}]


def test_every_path_resolves_to_a_served_file():
    """Link integrity: a path in the spec must be a file under docs/,
    because that is what GitHub Pages actually serves."""
    ghosts = [p for p in _spec()["paths"]
              if not (DOCS / p.lstrip("/")).is_file()]
    assert not ghosts, (
        f"spec paths with no file under docs/: {ghosts}. A machine "
        "reading the spec would request them and get a 404.")


def test_generated_machine_documents_are_linked_from_public_data_surfaces():
    for page_name in ("data.html", "api.html"):
        page = (DOCS / page_name).read_text(encoding="utf-8")
        assert 'href="openapi.json"' in page, (
            f"{page_name} does not expose the generated OpenAPI document")
        assert 'href="datasheet.md"' in page, (
            f"{page_name} does not expose the dataset datasheet")


def test_the_datasheet_quotes_every_register_finding_verbatim():
    """The negative-results register IS the known-limitations section.
    Every finding must appear verbatim -- a paraphrase is an edit, and
    a missing row is a limitation quietly dropped."""
    sheet = (DOCS / "datasheet.md").read_text(encoding="utf-8")
    register = json.loads(
        (DOCS / "data" / "negative_results.json").read_text(encoding="utf-8"))
    missing = []
    for f in register["findings"]:
        for key in ("finding", "number", "reading"):
            if f[key] not in sheet:
                missing.append(f"{f['source']}: {key}")
    assert not missing, (
        f"register text absent from docs/datasheet.md: {missing}. "
        "Regenerate with python -m scripts.generate_openapi.")
