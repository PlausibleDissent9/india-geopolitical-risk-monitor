#!/usr/bin/env python3
"""Generate or check the deterministic public API byte manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src import public_api_byte_manifest as manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check-index", action="store_true")
    group.add_argument("--check-tree", metavar="TREEISH")
    args = parser.parse_args()
    if args.check_index:
        result = manifest.verify_index()
    elif args.check_tree:
        result = manifest.verify_tree(args.check_tree)
    else:
        raw = manifest.write_from_index()
        result = json.loads(raw)
    print(
        json.dumps(
            {
                "status": "repository_candidate_bytes_consistent",
                "endpoint_denominator": result["universe"]["endpoint_denominator"],
                "hashed_endpoint_denominator": result["universe"]["hashed_endpoint_denominator"],
                "manifest_path": str(Path(manifest.MANIFEST_REPOSITORY_PATH)),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
