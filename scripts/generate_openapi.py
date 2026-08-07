"""
Deliberate-rerun generator for docs/openapi.json and docs/datasheet.md.

docs/openapi.json is an OpenAPI 3.1 description of the public data API,
derived entirely from the committed contract (docs/data/api_contract.json),
the universal _meta constants in src/stamp_meta.py, and CITATION.cff. It
exists so tooling and language models can consume the API without reading
HTML. docs/datasheet.md is a "Datasheets for Datasets" (Gebru et al.,
2018) datasheet whose every answer is extracted verbatim from committed
repository sources; a question with no committed answer says so instead
of inventing one.

Placement is load-bearing, not aesthetic: both files live in docs/, NOT
docs/data/, because four separate mechanisms glob docs/data/*.json and
would fight a committed spec there -- src/stamp_meta.py would inject a
_meta object nightly (breaking OpenAPI validity and the committed ==
generated lock), scripts/generate_api_contract.py and
tests/test_api_contract.py would demand the spec appear inside the very
contract it describes, and src/freshness.py would age it as if it were a
daily payload. Nothing scans docs/*.json or *.md at the docs root
(verified against test_sitemap.py, src/stamp_assets.py,
tests/test_offline_guarantee.py, tests/test_published_data_sanity.py);
docs/codebook.md is the precedent for a served root-level markdown file.

Like the contract itself, this is NOT part of the daily pipeline: the
spec and datasheet change only when the contract or their committed
sources deliberately change, and tests/test_openapi.py holds committed
== generated from the committed surface.

Run:  python -m scripts.generate_openapi
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.stamp_meta import CITATION, CODEBOOK, LICENSE  # noqa: E402

DOCS = ROOT / "docs"
SITE_DATA = DOCS / "data"
CONTRACT_PATH = SITE_DATA / "api_contract.json"

SPEC_OUT = DOCS / "openapi.json"
DATASHEET_OUT = DOCS / "datasheet.md"

MEDIA_TYPES = {"json": "application/json", "csv": "text/csv",
               "rss": "application/rss+xml"}

NOT_DOCUMENTED = "Not documented in the repository as of this generation."


# ---------------------------------------------------------------- sources

def _contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _cff_scalar(key: str) -> str:
    """A single-line scalar from CITATION.cff, quotes stripped."""
    text = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    m = re.search(rf"^\s*{key}:\s*(.+)$", text, re.M)
    if not m:
        raise SystemExit(f"[openapi] CITATION.cff has no scalar {key!r}")
    return m.group(1).strip().strip('"')


def _cff_abstract() -> str:
    """The folded block scalar `abstract` from CITATION.cff, unfolded."""
    lines = (ROOT / "CITATION.cff").read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    grab = False
    for ln in lines:
        if grab:
            if ln.startswith("  "):
                out.append(ln.strip())
            else:
                break
        elif ln.startswith("abstract:"):
            grab = True
    if not out:
        raise SystemExit("[openapi] CITATION.cff has no abstract block")
    return " ".join(out)


def _section(path: Path, heading: str) -> str:
    """Verbatim body of a markdown section, up to the next heading of the
    same or a higher level. Fails loudly if the heading moved, so a source
    rename cannot silently turn an answer into an empty string."""
    lines = path.read_text(encoding="utf-8").splitlines()
    level = 0
    start = None
    for i, ln in enumerate(lines):
        m = re.match(r"(#+)\s+(.*?)\s*$", ln)
        if not m:
            continue
        if start is None:
            if m.group(2) == heading:
                level = len(m.group(1))
                start = i + 1
        elif len(m.group(1)) <= level:
            return "\n".join(lines[start:i]).strip()
    if start is None:
        raise SystemExit(f"[openapi] no heading {heading!r} in {path.name}")
    return "\n".join(lines[start:]).strip()


def _contact_from_citation() -> dict[str, str]:
    """Name and URL parsed mechanically from the universal citation string.

    The citation is 'Family, Given (year). Title. URL' -- the split is on
    that committed shape and fails loudly if the shape changes rather than
    shipping a garbled contact."""
    name = CITATION.split(" (")[0]
    url = CITATION.rstrip().rsplit(None, 1)[-1]
    if not url.startswith("http"):
        raise SystemExit("[openapi] citation string no longer ends in a URL")
    return {"name": name, "url": url}


# ------------------------------------------------------------ the spec

def _operation_id(path: str) -> str:
    return "get_" + re.sub(r"[^A-Za-z0-9]+", "_", path).strip("_")


def _schema(endpoint: dict) -> dict[str, Any]:
    """Response schema from the contract's frozen fields. JSON payloads get
    object/array-of-object schemas whose required list IS the freeze; CSV
    and RSS are strings whose frozen columns ride an extension key."""
    fields = endpoint["frozen_fields"]
    if not isinstance(fields, list):
        raise SystemExit(f"[openapi] {endpoint['path']} has non-list "
                         f"frozen_fields {fields!r}")
    if endpoint["format"] != "json":
        return {"type": "string", "x-igrm-frozen-fields": list(fields)}
    served = DOCS / endpoint["path"]
    if not served.exists():
        raise SystemExit(f"[openapi] {endpoint['path']} is in the contract "
                         "but not served under docs/")
    payload = json.loads(served.read_text(encoding="utf-8"))
    obj: dict[str, Any] = {
        "type": "object",
        "required": list(fields),
        "properties": {f: {} for f in fields},
    }
    if isinstance(payload, list):
        return {"type": "array", "items": obj}
    return obj


def build_spec() -> dict:
    contract = _contract()
    meta = contract["_meta"]
    access = "\n".join(f"{k}: {v}" for k, v in meta["access"].items())
    deprecated = {d["path"] if isinstance(d, dict) else d
                  for d in meta.get("deprecated", [])}

    paths: dict[str, Any] = {}
    for e in contract["endpoints"]:
        p = "/" + e["path"]
        if p in paths:
            raise SystemExit(f"[openapi] duplicate contract endpoint {p}")
        op: dict[str, Any] = {
            "operationId": _operation_id(e["path"]),
            "description": e["description"],
            "x-igrm-stability": e["stability"],
            "responses": {"200": {
                "description": e["description"],
                "content": {MEDIA_TYPES[e["format"]]: {
                    "schema": _schema(e)}},
            }},
        }
        if e["path"] in deprecated or p in deprecated:
            op["deprecated"] = True
        paths[p] = {"get": op}

    return {
        "openapi": "3.1.0",
        "info": {
            "title": _cff_scalar("title"),
            "version": meta["contract_version"],
            "summary": meta["what"],
            "description": (meta["promise"] + "\n\n"
                            + meta["deprecation_policy"] + "\n\n" + access),
            "license": {"name": LICENSE},
            "contact": _contact_from_citation(),
            "x-citation": CITATION,
            "x-igrm-contract": meta["base_url"] + "data/api_contract.json",
            "x-igrm-frozen-date": meta["frozen_date"],
        },
        "externalDocs": {"url": CODEBOOK},
        "servers": [{"url": meta["base_url"].rstrip("/")}],
        "paths": paths,
    }


# -------------------------------------------------------- the datasheet

def _answer(body: str, source: str | None) -> str:
    if source is None:
        return body + "\n"
    return body + f"\n\n*Source: {source}*\n"


def build_datasheet() -> str:
    contract = _contract()
    meta = contract["_meta"]
    endpoints = contract["endpoints"]
    counts = {fmt: sum(1 for e in endpoints if e["format"] == fmt)
              for fmt in ("json", "csv", "rss")}
    register = json.loads(
        (SITE_DATA / "negative_results.json").read_text(encoding="utf-8"))

    readme = ROOT / "README.md"
    governance = ROOT / "GOVERNANCE.md"
    methodology = ROOT / "methodology.md"
    codebook = DOCS / "codebook.md"

    benchmark = next(e for e in endpoints
                     if e["path"] == "data/ai_gpr_benchmark.json")

    sections: list[tuple[str, list[tuple[str, str]]]] = [
        ("Motivation", [
            ("For what purpose was the dataset created?",
             _answer(_cff_abstract(), "CITATION.cff, abstract")),
            ("Who created the dataset and on behalf of which entity?",
             _answer(_section(governance, "Roles"),
                     'GOVERNANCE.md, section "Roles"')),
            ("Who funded the creation of the dataset?",
             _answer(NOT_DOCUMENTED, None)),
        ]),
        ("Composition", [
            ("What do the instances that comprise the dataset represent?",
             _answer(_section(methodology,
                              "1. What the index measures (and what it "
                              "does not)"),
                     'methodology.md, section "1. What the index measures '
                     '(and what it does not)"')),
            ("How many instances are there in total?",
             _answer(f"The API contract (data/api_contract.json, version "
                     f"{meta['contract_version']}, frozen "
                     f"{meta['frozen_date']}) lists {len(endpoints)} "
                     f"endpoints: {counts['json']} JSON, {counts['csv']} "
                     f"CSV, {counts['rss']} RSS. The machine-readable "
                     f"OpenAPI 3.1 description is served at "
                     f"{meta['base_url']}openapi.json.",
                     "docs/data/api_contract.json (counts computed at "
                     "generation)")),
            ("Does the dataset rely on external resources (e.g., websites, "
             "other datasets)?",
             _answer(_section(governance, "Dependencies and bus factor"),
                     'GOVERNANCE.md, section "Dependencies and bus '
                     'factor"')),
        ]),
        ("Collection process", [
            ("How was the data associated with each instance acquired?",
             _answer(_section(readme, "Architecture"),
                     'README.md, section "Architecture"')),
            ("What mechanisms or procedures were used to collect the data?",
             _answer(_section(readme, "Operations"),
                     'README.md, section "Operations"')),
            ("Over what timeframe was the data collected?",
             _answer(_section(readme, "Status"),
                     'README.md, section "Status"')),
        ]),
        ("Preprocessing, cleaning, labeling", [
            ("Was any preprocessing/cleaning/labeling of the data done?",
             _answer(_section(codebook, "Conventions"),
                     'docs/codebook.md, section "Conventions"')),
            ("Is the software that was used to preprocess/clean/label the "
             "data available?",
             _answer(_section(readme, "Local run"),
                     'README.md, section "Local run"')),
        ]),
        ("Uses", [
            ("Has the dataset been used for any tasks already?",
             _answer(benchmark["description"],
                     "docs/data/api_contract.json, description of "
                     "data/ai_gpr_benchmark.json")),
            ("Are there tasks for which the dataset should not be used?",
             _answer(_section(methodology, "7. Known limitations")
                     + "\n\n" + _section(readme, "Honest limitations"),
                     'methodology.md, section "7. Known limitations"; '
                     'README.md, section "Honest limitations"')),
        ]),
        ("Distribution", [
            ("How will the dataset be distributed?",
             _answer("Base URL: " + meta["base_url"] + "\n\n"
                     + "\n".join(f"- {k}: {v}"
                                 for k, v in meta["access"].items()),
                     "docs/data/api_contract.json, _meta.base_url and "
                     "_meta.access")),
            ("Will the dataset be distributed under a copyright or other "
             "intellectual property (IP) license?",
             _answer(f"License: {LICENSE}\n\nCitation: {CITATION}",
                     "the universal _meta fields stamped on every "
                     "published payload (src/stamp_meta.py)")),
        ]),
        ("Maintenance", [
            ("Who will be supporting/hosting/maintaining the dataset? How "
             "can the owner/curator/manager be contacted?",
             _answer(f"Citation: {CITATION}\n\nRepository: "
                     f"{_cff_scalar('repository-code')}\n\nContact: "
                     f"{_cff_scalar('email')}",
                     "the universal _meta citation and CITATION.cff")),
            ("Will the dataset be updated? How often?",
             _answer("Refresh: " + meta["access"]["refresh"] + "\n\n"
                     + meta["promise"] + "\n\n" + meta["deprecation_policy"],
                     "docs/data/api_contract.json, _meta.access.refresh, "
                     "_meta.promise and _meta.deprecation_policy")),
            ("Will older versions of the dataset continue to be "
             "supported/hosted/maintained?",
             _answer(_section(governance, "Deprecation policy (project "
                                          "level)"),
                     'GOVERNANCE.md, section "Deprecation policy (project '
                     'level)"')),
            ("If errors are found, what is the mechanism for communicating "
             "them?",
             _answer(_section(governance, "Failure policy"),
                     'GOVERNANCE.md, section "Failure policy"')),
        ]),
    ]

    out: list[str] = [
        f"# Datasheet: {_cff_scalar('title')}",
        "",
        'This datasheet follows the structure of Gebru et al., "Datasheets '
        'for Datasets" (2018).',
        "Every answer is extracted verbatim from committed repository "
        "sources by",
        "`scripts/generate_openapi.py`; a question with no committed answer "
        "says so rather than",
        "inventing one. Regenerate with: `python -m "
        "scripts.generate_openapi`.",
        "",
        f"Contract version {meta['contract_version']}, frozen "
        f"{meta['frozen_date']}. Machine-readable API description: "
        f"{meta['base_url']}openapi.json",
        "",
    ]
    for section, questions in sections:
        out.append(f"## {section}")
        out.append("")
        for question, answer in questions:
            out.append(f"### {question}")
            out.append("")
            out.append(answer)

    reg_meta = register["_meta"]
    out += [
        "## Known limitations: the negative-results register",
        "",
        "Quoted verbatim from docs/data/negative_results.json (the "
        "register's own description first):",
        "",
        f"> {reg_meta['what']}",
        ">",
        f"> {reg_meta['why']}",
        "",
    ]
    for f in register["findings"]:
        out += [
            f"### {f['finding']}",
            "",
            f"- Number: {f['number']}",
            f"- Reading: {f['reading']}",
            f"- Source: {f['source']} (via docs/data/negative_results.json)",
            "",
        ]
    return "\n".join(out).rstrip() + "\n"


def main() -> None:
    spec = build_spec()
    SPEC_OUT.write_text(json.dumps(spec, indent=1) + "\n", encoding="utf-8")
    print(f"[openapi] wrote {SPEC_OUT} ({len(spec['paths'])} paths, "
          f"contract v{spec['info']['version']})")
    sheet = build_datasheet()
    DATASHEET_OUT.write_text(sheet, encoding="utf-8")
    print(f"[openapi] wrote {DATASHEET_OUT} ({len(sheet.splitlines())} "
          "lines)")


if __name__ == "__main__":
    main()
