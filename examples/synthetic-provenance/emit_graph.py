#!/usr/bin/env python3
"""Rebuild rokb/_glimmer-index.json from the sidecars on disk.

Unlike the ds000114-nipype example (which emits sidecars from a provenance.json),
this example's sidecars are authored directly; emit_graph just (re)generates the
index that enumerates them, so `glimmer validate` / `glimmer run` have their map.
"""
import json, sys
from pathlib import Path

import yaml

ROKB = Path(__file__).resolve().parent / "rokb"


def read_fm(path):
    text = path.read_text()
    _, fm, _ = text.split("---\n", 2)
    return yaml.safe_load(fm) or {}


def main():
    nodes = []
    for path in sorted(ROKB.glob("**/*.md")):
        fm = read_fm(path)
        nodes.append({"id": fm["id"], "type": fm["type"], "path": str(path.relative_to(ROKB))})
    index = {
        "schema": "glimmer/v0.6.0",
        "dataset-name": "synthetic-provenance",
        "description": "Proactive-provenance worked example: the loop + three verification tiers + the standards gate + equivalence.",
        "default-domain": "synthetic",
        "node-count": len(nodes),
        "nodes": nodes,
    }
    (ROKB / "_glimmer-index.json").write_text(json.dumps(index, indent=2) + "\n")
    print(f"wrote {ROKB / '_glimmer-index.json'} with {len(nodes)} nodes")


if __name__ == "__main__":
    main()
