"""The public workbench must produce bounded, byte-identifiable research objects.

This test lands with the page and browser core it asserts.  It executes the same
JavaScript parser/exporter that the public page uses; duplicating those rules in
Python would let the test pass while the product failed.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def _run_node(source: str) -> dict[str, object]:
    node = shutil.which("node")
    if node is None:
        pytest.skip(
            "Node is not installed in this gate environment; the browser core "
            "still receives static contract checks here and executes in CI/browser QA"
        )
    completed = subprocess.run(
        [node, "-e", source],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_workbench_executes_the_public_parser_and_deterministic_export() -> None:
    script = r"""
const fs = require("fs");
const vm = require("vm");
vm.runInThisContext(fs.readFileSync("docs/workbench.js", "utf8"));
const core = globalThis.IGRM_WORKBENCH_CORE;
const raw = fs.readFileSync("docs/data/history.csv", "utf8");
const rows = core.parseHistory(raw);
const selected = core.selectRows(
  rows, ["shipping", "composite"], rows[0].date, rows[1].date
);
const csv = core.rowsToCSV(selected, ["shipping", "composite"]);
const stats = core.summary(selected, ["shipping", "composite"]);
const refusals = [];
for (const mutated of [
  "date,shipping\n2026-01-01,10\n",
  "date,pakistan_west,china_east,gulf_energy,us_trade,shipping,composite\n" +
    "2026-01-01,1,2,3,4,5,101\n",
  "date,pakistan_west,china_east,gulf_energy,us_trade,shipping,composite\n" +
    "2026-01-02,1,2,3,4,5,6\n2026-01-02,1,2,3,4,5,6\n",
]) {
  try { core.parseHistory(mutated); refusals.push(false); }
  catch (_) { refusals.push(true); }
}
let invalidQueryRefused = false;
try { core.selectRows(rows, ["not_a_measure"], rows[0].date, rows[1].date); }
catch (_) { invalidQueryRefused = true; }
process.stdout.write(JSON.stringify({
  n: rows.length,
  first: rows[0].date,
  last: rows[rows.length - 1].date,
  csv,
  stats,
  refusals,
  invalidQueryRefused,
}));
"""
    result = _run_node(script)
    assert int(result["n"]) > 3_000
    assert str(result["first"]) < str(result["last"])
    assert str(result["csv"]).startswith("date,shipping,composite\n")
    assert str(result["csv"]).endswith("\n")
    assert result["refusals"] == [True, True, True]
    assert result["invalidQueryRefused"] is True
    assert result["stats"]["shipping"]["n"] == 2  # type: ignore[index]


def test_workbench_surface_is_linked_and_keeps_the_claim_boundary() -> None:
    page = (DOCS / "workbench.html").read_text(encoding="utf-8")
    script = (DOCS / "workbench.js").read_text(encoding="utf-8")
    shell = (ROOT / "src" / "site_shell.py").read_text(encoding="utf-8")

    assert 'src="workbench.js' in page
    assert 'href="data/history.csv"' in page
    assert "workbench.html" in shell
    assert "crypto.subtle.digest(\"SHA-256\"" in script
    assert "response.arrayBuffer()" in script
    assert "sha256Bytes(rawBytes)" in script
    assert "source_value_out_of_range" in script
    assert "query_outside_published_range" in script
    assert "forbidden_interpretations" in script
    assert re.search(r"event\s+probabilities", page)
    assert "does not by itself establish upstream" in page
    assert "immutable archive" in page

    for linked_page in ("analysis.html", "data.html"):
        text = (DOCS / linked_page).read_text(encoding="utf-8")
        assert 'href="workbench.html"' in text


def test_workbench_has_no_external_runtime_dependency_or_data_egress() -> None:
    page = (DOCS / "workbench.html").read_text(encoding="utf-8")
    script = (DOCS / "workbench.js").read_text(encoding="utf-8")
    fetch_targets = re.findall(r'fetch\("([^"]+)"', script)
    assert fetch_targets == ["data/history.csv"]
    assert "fetch(\"data/history.csv\"" in script
    assert "XMLHttpRequest" not in script
    assert "sendBeacon" not in script
    assert "WebSocket" not in script
    assert "form-action 'self'" not in page  # There is no network-submitted form.
