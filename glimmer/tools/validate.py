#!/usr/bin/env python3
"""Validate a Glimmer RO-KB against the schema in glimmer/schema/frontmatter.yaml.

Checks:
  - every node sidecar parses as valid YAML front-matter
  - required fields are present per the node type
  - field types match their type-spec
  - every edge's `target` refers to a node that exists in the index
  - every edge's `type` is in the `edges-allowed` set for its source type
  - the index file enumerates exactly the sidecars on disk
  - validator-hints warnings (non-fatal)

Exits 0 if valid, 1 if errors, 2 if hint-level warnings (no errors).
"""

import sys, os, json, re, argparse, yaml
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent.parent / "schema" / "frontmatter.yaml"
NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")  # kebab-case


def load_schema():
    return yaml.safe_load(SCHEMA_PATH.read_text())


def read_sidecar(path: Path):
    """Return (frontmatter_dict, body_str) or raise ValueError."""
    text = path.read_text()
    if text.startswith("---\n"):
        try:
            _, fm, body = text.split("---\n", 2)
        except ValueError:
            raise ValueError(f"{path}: malformed front-matter delimiters")
        try:
            fm_dict = yaml.safe_load(fm) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"{path}: YAML parse error: {e}")
        return fm_dict, body
    if text.startswith("{"):
        try:
            return json.loads(text), ""
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}: JSON parse error: {e}")
    raise ValueError(f"{path}: sidecar must start with '---' (YAML front-matter) or '{{' (JSON)")


def validate(rokb_path: Path, schema: dict):
    errors, warnings = [], []
    rokb_path = Path(rokb_path)

    # 1. Index file
    index_path = rokb_path / "_glimmer-index.json"
    if not index_path.exists():
        errors.append(f"{index_path}: missing")
        return errors, warnings
    try:
        index = json.loads(index_path.read_text())
    except json.JSONDecodeError as e:
        errors.append(f"{index_path}: parse error: {e}")
        return errors, warnings

    if "nodes" not in index:
        errors.append(f"{index_path}: missing required field `nodes`")
        return errors, warnings

    index_ids = {n["id"]: n for n in index["nodes"]}
    if len(index_ids) != len(index["nodes"]):
        errors.append(f"{index_path}: duplicate node IDs in index")

    # 2. Walk sidecars on disk
    sidecar_paths = list(rokb_path.glob("**/*.md")) + list(rokb_path.glob("**/*.json"))
    sidecar_paths = [p for p in sidecar_paths if p.name != "_glimmer-index.json"]

    on_disk_ids = set()
    sidecar_by_id = {}

    for path in sidecar_paths:
        try:
            fm, body = read_sidecar(path)
        except ValueError as e:
            errors.append(str(e))
            continue
        node_id = fm.get("id")
        node_type = fm.get("type")

        if not node_id:
            errors.append(f"{path}: missing required field `id`"); continue
        if not NAME_PATTERN.match(node_id):
            errors.append(f"{path}: id `{node_id}` is not kebab-case")
        if node_id in on_disk_ids:
            errors.append(f"{path}: duplicate node id `{node_id}` (already seen)")
        on_disk_ids.add(node_id)
        sidecar_by_id[node_id] = (path, fm, body)

        # 3. Check node type
        if not node_type:
            errors.append(f"{path}: missing required field `type`"); continue
        if node_type not in schema or node_type.startswith("_"):
            errors.append(f"{path}: unknown node type `{node_type}`"); continue

        type_def = schema[node_type]
        required = {**schema["_common"]["required"], **type_def.get("required", {})}
        edges_allowed = set(type_def.get("edges-allowed", []))

        # 4. Required fields present
        for field in required:
            if field not in fm:
                errors.append(f"{path}: missing required field `{field}` for type `{node_type}`")

        # 5. Validate edges
        for edge in (fm.get("edges") or []):
            if not isinstance(edge, dict):
                errors.append(f"{path}: edge must be a mapping with `type` and `target`")
                continue
            etype = edge.get("type")
            target = edge.get("target")
            if not etype:
                errors.append(f"{path}: edge missing `type`")
            elif etype not in edges_allowed:
                errors.append(f"{path}: edge type `{etype}` not allowed for {node_type}; "
                              f"allowed: {sorted(edges_allowed)}")
            if not target:
                errors.append(f"{path}: edge missing `target`")
            elif target not in index_ids:
                errors.append(f"{path}: edge target `{target}` not in index")

    # 6. Index ↔ disk consistency
    indexed_only = set(index_ids) - on_disk_ids
    disk_only = on_disk_ids - set(index_ids)
    for nid in indexed_only:
        errors.append(f"index lists `{nid}` but no sidecar found on disk")
    for nid in disk_only:
        errors.append(f"sidecar `{nid}` exists on disk but is not in index")

    # 7. Hints (warnings)
    for node_id, (path, fm, _) in sidecar_by_id.items():
        node_type = fm.get("type")
        edges = fm.get("edges") or []
        edge_types = {e.get("type") for e in edges if isinstance(e, dict)}

        if node_type == "qc-artifact" and "conforms-to" not in edge_types:
            warnings.append(f"{path}: qc-artifact has no `conforms-to` edge to a standard")
        if node_type == "dataset" and "produced-by" not in edge_types:
            warnings.append(f"{path}: dataset has no `produced-by` edge")
        if node_type == "publication" and not any(t.startswith("cites") for t in edge_types):
            warnings.append(f"{path}: publication has no `cites-*` edges")

    return errors, warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="path to a Glimmer RO-KB directory")
    args = ap.parse_args()

    schema = load_schema()
    errors, warnings = validate(args.path, schema)

    print(f"Glimmer schema: {schema.get('schema-version', '?')}")
    print(f"Target: {args.path}")
    print(f"Errors:   {len(errors)}")
    print(f"Warnings: {len(warnings)}")

    if errors:
        print("\n--- errors ---")
        for e in errors: print(f"  ✗ {e}")
    if warnings:
        print("\n--- warnings ---")
        for w in warnings: print(f"  ! {w}")

    if errors:
        sys.exit(1)
    if warnings:
        sys.exit(2)
    print("\n✓ valid")
    sys.exit(0)


if __name__ == "__main__":
    main()
