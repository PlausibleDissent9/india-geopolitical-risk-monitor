"""The public API byte verifier is bounded, on-demand and claim-disciplined."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
PAGE = (DOCS / "verify.html").read_text(encoding="utf-8")
SCRIPT = (DOCS / "verify.js").read_text(encoding="utf-8")
MANIFEST_PATH = DOCS / "data" / "public_api_byte_manifest.json"


def _run_node(source: str) -> dict[str, object]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not available in this environment")
    result = subprocess.run(
        [node, "-e", source],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_page_is_explicit_on_demand_and_has_a_no_js_path() -> None:
    for required in (
        "Byte consistency, not authentication",
        "116 requests and about 6.9 MiB",
        "Only the manifest is loaded before you press the button",
        "same-site manifest without an independent digest is not an authenticity check",
        "sha256sum public_api_byte_manifest.json",
        'id="verify-api-bytes"',
        'id="expected-manifest-sha"',
        'id="verification-results"',
        "<noscript>",
    ):
        assert required in PAGE
    assert 'src="verify.js' in PAGE
    assert "data-manifest-load" in PAGE
    assert "data-latest-date" not in PAGE
    assert "data/latest.json" not in SCRIPT
    assert "authenticated deployment" not in PAGE.lower()
    assert not re.search(r"\b[0-9a-f]{64}\b", PAGE)
    assert 'href="verify.html"' in (DOCS / "api.html").read_text(encoding="utf-8")


def test_browser_runtime_parses_and_validates_the_committed_manifest() -> None:
    result = _run_node(
        """
const fs = require("fs");
const v = require("./docs/verify.js");
const m = JSON.parse(fs.readFileSync("docs/data/public_api_byte_manifest.json"));
const out = v.validateManifest(m);
console.log(JSON.stringify({entries: out.entries.length, concurrency: v.CONCURRENCY,
  bytes: out.totals.hashed_bytes, formatted: v.formatBytes(out.totals.hashed_bytes)}));
"""
    )
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert result == {
        "entries": 116,
        "concurrency": 4,
        "bytes": manifest["totals"]["hashed_bytes"],
        "formatted": "6.89 MiB",
    }


def test_browser_digest_matches_raw_manifest_sha256() -> None:
    result = _run_node(
        """
const fs = require("fs");
const v = require("./docs/verify.js");
(async () => {
  const raw = new Uint8Array(fs.readFileSync("docs/data/public_api_byte_manifest.json"));
  console.log(JSON.stringify({digest: await v.digestBytes(raw)}));
})();
"""
    )
    assert result["digest"] == hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest()


def test_manifest_path_and_denominator_attacks_refuse() -> None:
    result = _run_node(
        """
const fs = require("fs");
const v = require("./docs/verify.js");
const base = JSON.parse(fs.readFileSync("docs/data/public_api_byte_manifest.json"));
const attacks = ["../data/latest.json", "data\\\\latest.json",
  "data/latest.json:stream", "data//latest.json", "/data/latest.json"];
const codes = [];
for (const path of attacks) {
  try { v.safePath(path); codes.push("accepted"); } catch (e) { codes.push(e.code); }
}
const shrunk = structuredClone(base);
shrunk.entries.pop();
try { v.validateManifest(shrunk); codes.push("accepted"); } catch (e) { codes.push(e.code); }
const reordered = structuredClone(base);
[reordered.entries[0], reordered.entries[1]] = [reordered.entries[1], reordered.entries[0]];
try { v.validateManifest(reordered); codes.push("accepted"); } catch (e) { codes.push(e.code); }
console.log(JSON.stringify({codes}));
"""
    )
    assert result["codes"] == [
        "manifest_path_invalid",
        "manifest_path_invalid",
        "manifest_path_invalid",
        "manifest_path_invalid",
        "manifest_path_invalid",
        "manifest_boundary_invalid",
        "manifest_entry_order_invalid",
    ]


def test_endpoint_fetches_are_bounded_to_four_and_use_strict_options() -> None:
    result = _run_node(
        """
const crypto = require("crypto");
const v = require("./docs/verify.js");
const body = Buffer.from("bounded payload");
const sha = crypto.createHash("sha256").update(body).digest("hex");
const entries = Array.from({length: 12}, (_, i) => ({
  path: `data/mock-${String(i).padStart(2, "0")}.json`, repository_path: "unused",
  format: "json", git_mode: "100644", bytes: body.length, sha256: sha,
}));
let active = 0, maximum = 0, strict = true;
const mockFetch = async (_url, options) => {
  strict = strict && options.cache === "no-store" && options.credentials === "omit" &&
    options.redirect === "error" && Boolean(options.signal);
  active += 1; maximum = Math.max(maximum, active);
  await new Promise((resolve) => setTimeout(resolve, 8));
  active -= 1;
  return new Response(body, {status: 200, headers: {"content-length": String(body.length)}});
};
(async () => {
  const rows = await v.verifyEntries(entries, "https://igrm.in/verify.html", mockFetch);
  console.log(JSON.stringify({maximum, strict, statuses: rows.map((row) => row.status)}));
})();
"""
    )
    assert result["maximum"] == 4
    assert result["strict"] is True
    assert result["statuses"] == ["matched"] * 12


def test_network_missing_mismatch_and_unsupported_are_not_laundered() -> None:
    result = _run_node(
        """
const v = require("./docs/verify.js");
const entry = {path: "data/x.json", bytes: 1, sha256: "0".repeat(64)};
const missing = async () => new Response("", {status: 404});
const wrong = async () => new Response("xx", {status: 200});
const network = async () => { throw new Error("offline"); };
(async () => {
  const rows = [];
  rows.push(await v.verifyEntry(entry, "https://igrm.in/verify.html", missing));
  rows.push(await v.verifyEntry(entry, "https://igrm.in/verify.html", wrong));
  rows.push(await v.verifyEntry(entry, "https://igrm.in/verify.html", network));
  console.log(JSON.stringify({statuses: rows.map((row) => row.status)}));
})();
"""
    )
    assert result["statuses"] == ["missing", "mismatch", "indeterminate"]


def test_actual_download_is_capped_at_each_exact_declared_length() -> None:
    assert (
        "fetchBytes(endpointURL(entry.path, baseURL), entry.bytes, fetchImpl)" in SCRIPT
    )
    result = _run_node(
        """
const v = require("./docs/verify.js");
const entry = {path: "data/x.json", bytes: 1, sha256: "0".repeat(64)};
let cancelled = false;
const oversized = async () => {
  const stream = new ReadableStream({
    start(controller) { controller.enqueue(new Uint8Array([1, 2])); },
    cancel() { cancelled = true; },
  });
  return new Response(stream, {status: 200});
};
(async () => {
  const row = await v.verifyEntry(entry, "https://igrm.in/verify.html", oversized);
  console.log(JSON.stringify({status: row.status, detail: row.detail, cancelled}));
})();
"""
    )
    assert result == {
        "status": "mismatch",
        "detail": "response_size_limit_exceeded",
        "cancelled": True,
    }


def test_runtime_has_external_anchor_m1_m2_and_precise_verdict_language() -> None:
    for required in (
        'cache: "no-store"',
        'credentials: "omit"',
        'redirect: "error"',
        "release_changed_during_verification",
        "caller_supplied_manifest_digest_and_endpoint_bytes_match",
        "same_origin_bytes_match_unanchored_manifest",
        "manifest_digest_mismatch",
        "verification_indeterminate",
        "navigator.connection && navigator.connection.saveData",
        'matchMedia("(prefers-reduced-data: reduce)")',
    ):
        assert required in SCRIPT
    assert SCRIPT.count("verifyEntries(") == 2  # definition plus click-handler call
    assert SCRIPT.index('button.addEventListener("click"') < SCRIPT.rindex("verifyEntries(")
    assert SCRIPT.index("const raw = await fetchBytes") < SCRIPT.index(
        'button.addEventListener("click"'
    )


def test_verifier_assets_are_deliberately_outside_the_api_endpoint_universe() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    paths = {row["path"] for row in manifest["entries"]}
    assert "verify.html" not in paths
    assert "verify.js" not in paths
    assert "data/public_api_byte_manifest.json" not in paths
    assert manifest["excluded_entries"] == [
        {
            "path": "data/public_api_byte_manifest.json",
            "reason": "self_exclusion_avoids_recursive_digest",
            "repository_path": "docs/data/public_api_byte_manifest.json",
        }
    ]
