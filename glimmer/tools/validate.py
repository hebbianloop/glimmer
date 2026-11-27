#!/usr/bin/env python3
"""Validate a Glimmer RO-KB against the schema in glimmer/schema/frontmatter.yaml.

Checks:
  - every node sidecar parses as valid YAML front-matter
  - required fields are present per the node type
  - field types / controlled enums match their type-spec where enforced
  - every edge's `target` refers to a node that exists in the index
  - every edge's `type` is in the `edges-allowed` set for its source type
  - the index file enumerates exactly the sidecars on disk
  - validator-hints warnings (non-fatal)

Exits 0 if valid, 1 if errors, 2 if hint-level warnings (no errors).
"""

import sys, os, json, re, argparse, yaml
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent.parent / "schema" / "frontmatter.yaml"
PROFILES_DIR = SCHEMA_PATH.parent / "profiles"      # curated, in-repo profile library
LOCAL_PROFILES_DIRNAME = "_glimmer-profiles"        # researcher profiles, local to one KB
# IDs are kebab-style but allow uppercase letters and dots — needed for BIDS-canonical
# tokens like `T1w`, `T2w`, version strings like `1.11.1`, and similar domain conventions.
NAME_PATTERN = re.compile(r"^[a-zA-Z0-9]+([-.][a-zA-Z0-9]+)*$")
OUT_OF_GRAPH_EDGES = {"contributed-by", "cross-project"}  # target is out-of-graph: an identifier (ORCID/email) or a node in another project's graph (namespaced id), not a node in this index
PUBLICATION_ROLES = {"project-output", "external-reference"}


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys instead of silently
    keeping the last one. A duplicate type/field key is never intentional —
    in the schema it shadows a whole definition (e.g. two `concept:` blocks),
    and in a sidecar it silently drops front-matter — so it must be an error.
    """


def _no_duplicate_keys(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.YAMLError(
                f"duplicate key `{key}` at line {key_node.start_mark.line + 1}"
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys
)


def load_schema():
    try:
        return yaml.load(SCHEMA_PATH.read_text(encoding="utf-8"), Loader=_StrictLoader)
    except yaml.YAMLError as e:
        sys.exit(f"FATAL: schema {SCHEMA_PATH} is malformed: {e}")


def _profile_hint(domain):
    """One-line, actionable next step for an unresolved domain — no fictional CLI."""
    return (f"→ either use a listed profile (the `Profiles:` line above lists what's active), "
            f"or author one at <rokb>/{LOCAL_PROFILES_DIRNAME}/{domain}.yaml "
            f"(template: profiles/_profile.schema.yaml; guide: docs/extending-the-schema.md → Domain profiles)")


def load_profiles(rokb_path):
    """Load the curated profile library + any profiles local to this KB.

    Returns (profiles_by_domain, warnings). Each value is the parsed profile
    dict (with its `augments` map). A local profile shadows a curated one of the
    same name (a warning is emitted). Malformed/incomplete profiles are skipped
    with a warning rather than aborting the whole run.
    """
    profiles, warns = {}, []
    sources = [(PROFILES_DIR, "curated"),
               (Path(rokb_path) / LOCAL_PROFILES_DIRNAME, "local")]
    for directory, tier in sources:
        if not directory.is_dir():
            continue
        for pf in sorted(directory.glob("*.yaml")):
            if pf.name.startswith("_"):          # _profile.schema.yaml, etc.
                continue
            try:
                doc = yaml.load(pf.read_text(encoding="utf-8"), Loader=_StrictLoader) or {}
            except yaml.YAMLError as e:
                warns.append(f"{pf}: YAML parse error: {e}; profile skipped")
                continue
            name = doc.get("profile")
            if not name or "augments" not in doc:
                warns.append(f"{pf}: profile missing `profile` or `augments`; skipped")
                continue
            if name in profiles and tier == "local":
                warns.append(f"{pf}: local profile `{name}` shadows the curated one")
            doc["_tier"] = tier
            profiles[name] = doc
    return profiles, warns


NON_SIDECAR_DOCS = {"README.md", "AGENTS.md", "AGENTS.glimmer.md", "CHANGELOG.md"}


def is_internal_path(path: Path, rokb_path: Path) -> bool:
    """Skip internal `_glimmer-*` directories (profiles, amendments, caches), index, and non-sidecar docs."""
    if path.name == "_glimmer-index.json" or path.name in NON_SIDECAR_DOCS:
        return True
    try:
        rel_parts = path.relative_to(rokb_path).parts
    except ValueError:
        rel_parts = path.parts
    return any(part.startswith("_glimmer-") or part.startswith(".") for part in rel_parts[:-1])


def iter_sidecar_paths(rokb_path: Path):
    """Yield sorted sidecar paths (.md and .json) inside `rokb_path`, skipping internal dirs."""
    rokb_path = Path(rokb_path)
    paths = list(rokb_path.glob("**/*.md")) + list(rokb_path.glob("**/*.json"))
    return sorted(p for p in paths if p.is_file() and not is_internal_path(p, rokb_path))


def read_sidecar(path: Path):
    """Return (frontmatter_dict, body_str) or raise ValueError."""
    text = path.read_text(encoding="utf-8")
    if text.startswith("---\n") or text.startswith("---\r\n"):
        normalized = text.replace("\r\n", "\n")
        try:
            _, fm, body = normalized.split("---\n", 2)
        except ValueError:
            raise ValueError(f"{path}: malformed front-matter delimiters")
        try:
            fm_dict = yaml.load(fm, Loader=_StrictLoader) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"{path}: YAML parse error: {e}")
        if not isinstance(fm_dict, dict):
            raise ValueError(f"{path}: YAML front-matter must be a mapping")
        return fm_dict, body
    if text.startswith("{"):
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}: JSON parse error: {e}")
        if not isinstance(doc, dict):
            raise ValueError(f"{path}: JSON sidecar must be an object")
        return doc, ""
    raise ValueError(f"{path}: sidecar must start with '---' (YAML front-matter) or '{{' (JSON)")


def validate(rokb_path: Path, schema: dict, *, strict: bool = False):
    errors, warnings = [], []
    rokb_path = Path(rokb_path)

    # 1. Index file
    index_path = rokb_path / "_glimmer-index.json"
    if not index_path.exists():
        errors.append(f"{index_path}: missing")
        return errors, warnings
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"{index_path}: parse error: {e}")
        return errors, warnings

    if not isinstance(index, dict) or "nodes" not in index or not isinstance(index["nodes"], list):
        errors.append(f"{index_path}: missing required list field `nodes`")
        return errors, warnings

    index_ids = {}
    for entry in index["nodes"]:
        if not isinstance(entry, dict) or not entry.get("id"):
            errors.append(f"{index_path}: every entry in `nodes` must be an object with `id`")
            continue
        if entry["id"] in index_ids:
            errors.append(f"{index_path}: duplicate node ID `{entry['id']}` in index")
        index_ids[entry["id"]] = entry

    # Validate optional top-level index anchors (v0.7.0)
    root_node = index.get("root-node")
    if root_node and root_node not in index_ids:
        errors.append(f"{index_path}: `root-node` `{root_node}` not in index")
    for ep in (index.get("entrypoints") or []):
        ep_id = ep.get("id") if isinstance(ep, dict) else ep
        if ep_id and ep_id not in index_ids:
            errors.append(f"{index_path}: entrypoint `{ep_id}` not in index")

    # 1b. Domain profiles. A node resolves to a profile by its `domain` field,
    # then the KB-level `default-domain` (index), then the core schema default.
    profiles, profile_warns = load_profiles(rokb_path)
    warnings.extend(profile_warns)
    kb_default_domain = index.get("default-domain") or schema.get("default-domain")
    if kb_default_domain and kb_default_domain not in profiles:
        warnings.append(f"{index_path}: default-domain `{kb_default_domain}` has no profile "
                        f"(curated or local); domain-specific fields go unchecked. "
                        f"{_profile_hint(kb_default_domain)}")

    # v0.5: profiles may declare domain `node-types` + `edge-types` (not just augment fields).
    # Collect the KB-default-domain profile's extras; per-node `domain` profiles add their own below.
    def _profile_extras(p):
        p = p or {}
        return set(p.get("node-types") or []), set(p.get("edge-types") or [])
    kb_extra_types, kb_extra_edges = _profile_extras(profiles.get(kb_default_domain))

    # 2. Walk sidecars on disk
    sidecar_paths = iter_sidecar_paths(rokb_path)

    on_disk_ids = set()
    sidecar_by_id = {}
    incoming_by_id = {}

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
        if not isinstance(node_id, str) or not NAME_PATTERN.match(node_id):
            errors.append(f"{path}: id `{node_id}` is not kebab-case")
        if node_id in on_disk_ids:
            errors.append(f"{path}: duplicate node id `{node_id}` (already seen)")
        on_disk_ids.add(node_id)
        sidecar_by_id[node_id] = (path, fm, body)

        # 3. Check node type — core OR a profile-declared domain node-type (v0.5).
        if not node_type:
            errors.append(f"{path}: missing required field `type`"); continue
        if node_id in index_ids and index_ids[node_id].get("type") and index_ids[node_id]["type"] != node_type:
            errors.append(f"{path}: index type `{index_ids[node_id]['type']}` does not match sidecar type `{node_type}`")

        # Resolve this node's domain (its `domain` field, else the KB default) + that
        # profile's declared node-types / edge-types, unioned with the KB-default extras.
        domain = fm.get("domain") or kb_default_domain
        node_domain_profile = profiles.get(domain) if domain else None
        n_types, n_edges = _profile_extras(node_domain_profile)
        valid_types = kb_extra_types | n_types
        if (node_type not in schema or node_type.startswith("_")) and node_type not in valid_types:
            errors.append(f"{path}: unknown node type `{node_type}`"); continue

        type_def = schema.get(node_type) or {}      # {} for a profile-declared type (no core def)
        required = {**schema["_common"]["required"], **type_def.get("required", {})}
        edges_allowed = (set(type_def.get("edges-allowed", [])) | set(schema.get("_universal-edges", []))
                         | kb_extra_edges | n_edges)

        # Domain profile augments: merge its `augments` required fields onto core requirements.
        if node_domain_profile:
            aug = (node_domain_profile.get("augments") or {}).get(node_type) or {}
            required = {**required, **(aug.get("required") or {})}
        elif fm.get("domain") and fm["domain"] not in profiles:
            warnings.append(f"{path}: domain `{fm['domain']}` has no profile (curated or local); "
                            f"domain-specific fields unchecked. {_profile_hint(fm['domain'])}")

        # 4. Required fields present + controlled role enum check
        for field in required:
            if field not in fm:
                errors.append(f"{path}: missing required field `{field}` for type `{node_type}`")

        if node_type == "publication" and "role" in fm and fm["role"] not in PUBLICATION_ROLES:
            errors.append(f"{path}: publication `role` `{fm['role']}` invalid; "
                          f"expected one of {sorted(PUBLICATION_ROLES)}")

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
            elif etype not in OUT_OF_GRAPH_EDGES and target not in index_ids:
                errors.append(f"{path}: edge target `{target}` not in index")
            elif etype not in OUT_OF_GRAPH_EDGES:
                incoming_by_id.setdefault(target, []).append((node_id, etype))

    # 6. Index ↔ disk consistency
    indexed_only = set(index_ids) - on_disk_ids
    disk_only = on_disk_ids - set(index_ids)
    for nid in sorted(indexed_only):
        errors.append(f"index lists `{nid}` but no sidecar found on disk")
    for nid in sorted(disk_only):
        errors.append(f"sidecar `{nid}` exists on disk but is not in index")

    # 7. Hints (warnings) + agent-protocol enforcement
    for node_id, (path, fm, _) in sidecar_by_id.items():
        node_type = fm.get("type")
        edges = fm.get("edges") or []
        # Agent-protocol: findings/derivatives/run-records produced by an agent require reasoning-trace
        if node_type in ("finding", "derivative", "run-record") and fm.get("produced-by-agent") and not fm.get("reasoning-trace"):
            errors.append(f"{path}: {node_type} has `produced-by-agent` but no `reasoning-trace` (agent protocol)")
        # Findings must have based-on (the evidence chain)
        if node_type == "finding":
            if "based-on" not in fm or not fm.get("based-on"):
                errors.append(f"{path}: finding node missing required `based-on` field (the evidence chain)")
        edge_types = {e.get("type") for e in edges if isinstance(e, dict)}
        non_program_out = [e for e in edges if isinstance(e, dict) and e.get("type") != "in-program"]
        inc = incoming_by_id.get(node_id, [])

        # run-record structured-field + lifecycle checks (v0.6). The generic
        # required-field check (section 4) ensures method/command/status/inputs/
        # outputs are present; here we check their SHAPE and graph consistency.
        if node_type == "run-record":
            status = fm.get("status")
            # `method` must name a method node
            m = fm.get("method")
            if m:
                if m not in index_ids:
                    errors.append(f"{path}: run-record `method` `{m}` not in index")
                elif (index_ids[m].get("type") or "method") != "method":
                    errors.append(f"{path}: run-record `method` `{m}` is type `{index_ids[m].get('type')}`, expected `method`")
                if m not in {e.get("target") for e in edges if isinstance(e, dict) and e.get("type") == "reruns"}:
                    warnings.append(f"{path}: run-record `method` `{m}` not mirrored by a `reruns` edge")
            # inputs: non-empty list of pins; each needs `node` (+ a content pin unless planned)
            inputs = fm.get("inputs")
            if not isinstance(inputs, list) or not inputs:
                errors.append(f"{path}: run-record `inputs` must be a non-empty list of pins")
                inputs = []
            consumes_targets = {e.get("target") for e in edges if isinstance(e, dict) and e.get("type") == "consumes"}
            for i, pin in enumerate(inputs):
                if not isinstance(pin, dict) or not pin.get("node"):
                    errors.append(f"{path}: run-record inputs[{i}] missing `node`"); continue
                n = pin["node"]
                if n not in index_ids:
                    errors.append(f"{path}: run-record input node `{n}` not in index")
                if status != "planned" and not (pin.get("datalad-annex-key") or pin.get("datalad-commit-sha")):
                    errors.append(f"{path}: run-record input `{n}` has no content pin "
                                  f"(datalad-annex-key/commit-sha) and status is `{status}` (pins required unless planned)")
                if n not in consumes_targets:
                    warnings.append(f"{path}: run-record input `{n}` not mirrored by a `consumes` edge")
            # outputs: non-empty list of pins; each `node` must resolve to a derivative
            outputs = fm.get("outputs")
            if not isinstance(outputs, list) or not outputs:
                errors.append(f"{path}: run-record `outputs` must be a non-empty list of pins")
                outputs = []
            regen_targets = {e.get("target") for e in edges if isinstance(e, dict) and e.get("type") == "regenerates"}
            for i, pin in enumerate(outputs):
                if not isinstance(pin, dict) or not pin.get("node"):
                    errors.append(f"{path}: run-record outputs[{i}] missing `node`"); continue
                n = pin["node"]
                if n not in index_ids:
                    errors.append(f"{path}: run-record output node `{n}` not in index")
                elif (index_ids[n].get("type") or "derivative") != "derivative":
                    errors.append(f"{path}: run-record output node `{n}` is type "
                                  f"`{index_ids[n].get('type')}`, expected `derivative`")
                if status == "executed" and not pin.get("expected-hash"):
                    warnings.append(f"{path}: run-record output `{n}` has no `expected-hash` (status=executed)")
                if n not in regen_targets:
                    warnings.append(f"{path}: run-record output `{n}` not mirrored by a `regenerates` edge")
            # reproduction-tolerance, if present, must be a map of {rel?,abs?} numerics
            tol = fm.get("reproduction-tolerance")
            if tol is not None:
                buckets = ([tol.get("default")] + list((tol.get("quantities") or {}).values())) if isinstance(tol, dict) else None
                if buckets is None:
                    errors.append(f"{path}: run-record `reproduction-tolerance` must be a map")
                else:
                    for b in buckets:
                        if b is None:
                            continue
                        if (not isinstance(b, dict) or any(k not in ("rel", "abs") for k in b)
                                or any(not isinstance(v, (int, float)) for v in b.values())):
                            errors.append(f"{path}: run-record `reproduction-tolerance` entries must be {{rel?,abs?}} numerics")
                            break
            # status=executed should carry the runner's verdict
            if status == "executed" and not fm.get("replay-verdict"):
                warnings.append(f"{path}: run-record status=executed but no `replay-verdict` "
                                f"(run `glimmer run`/`rerun` with --write-verdict)")

        if node_type == "dataset" and "produced-by" not in edge_types:
            warnings.append(f"{path}: dataset has no `produced-by` edge")

        # v0.7.0: `reference` is for external cited literature — never expects local `cites-*`
        # edges, only that it connects to at least one node beyond `in-program`.
        if node_type == "reference":
            if not non_program_out and not inc:
                warnings.append(f"{path}: reference has no incoming or outgoing graph edges "
                                f"(link via `addresses-concept`, `supports`/`challenges`, or `cites`)")

        # v0.7.0: `publication` separates project outputs from backwards-compatible external refs.
        if node_type == "publication":
            role = fm.get("role")
            if role == "external-reference":
                if not non_program_out and not inc:
                    warnings.append(f"{path}: external-reference publication has no graph edges")
            else:
                has_local_cites = any(t.startswith("cites") or t == "aggregates" for t in edge_types)
                if not has_local_cites:
                    warnings.append(
                        f"{path}: publication has no `cites-*` or `aggregates` edges "
                        f"(if this is cited external literature, use `type: reference` or set `role: external-reference`)"
                    )

        if strict and node_type == "concept" and "claim-kind" in fm and "concept-kind" not in fm:
            warnings.append(f"{path}: concept sets profile `claim-kind` without core `concept-kind`")

    return errors, warnings


def main():
    ap = argparse.ArgumentParser(description="Validate a Glimmer RO-KB against the schema.")
    ap.add_argument("path", help="path to a Glimmer RO-KB directory")
    ap.add_argument("--strict", action="store_true", help="enable extra advisory checks")
    ap.add_argument("--json", action="store_true", dest="as_json", help="emit machine-readable JSON")
    args = ap.parse_args()

    schema = load_schema()
    errors, warnings = validate(args.path, schema, strict=args.strict)

    profiles, _ = load_profiles(args.path)
    if args.as_json:
        payload = {
            "schema": schema.get("schema-version", "?"),
            "target": str(args.path),
            "profiles": {n: p.get("_tier", "curated") for n, p in sorted(profiles.items())},
            "valid": len(errors) == 0,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": errors,
            "warnings": warnings,
        }
        print(json.dumps(payload, indent=2))
    else:
        profile_list = ", ".join(f"{n} ({p.get('_tier', 'curated')})" for n, p in sorted(profiles.items())) or "none"
        print(f"Glimmer schema: {schema.get('schema-version', '?')}")
        print(f"Profiles: {profile_list}")
        print(f"Target: {args.path}")
        print(f"Errors:   {len(errors)}")
        print(f"Warnings: {len(warnings)}")

        if errors:
            print("\n--- errors ---")
            for e in errors: print(f"  ✗ {e}")
        if warnings:
            print("\n--- warnings ---")
            for w in warnings: print(f"  ! {w}")

        if not errors and not warnings:
            print("\n✓ valid")

    if errors:
        sys.exit(1)
    if warnings:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
