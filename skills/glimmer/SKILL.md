---
name: glimmer
description: Orient, query, search, author, sync, and validate a Glimmer Research-Object Knowledge Base (RO-KB) over typed YAML-frontmatter Markdown sidecars. Use when initializing a research graph, exploring claims/literature/methods/experiments/datasets without overflowing context, checking provenance hashes or draft/artifact drift, or maintaining canonical nodes. Hand off workspace HTML bundling, browser views, and public release manifests to $glimmer-workspace.
---

# Glimmer RO-KB Workflow

Use Glimmer to keep a project's canonical scientific graph accurate, queryable, and aligned with active drafts and artifacts. Prefer the installed `glimmer` CLI; if `glimmer` is not on `PATH`, invoke `python3 scripts/glimmer-cli.py <subcommand> ...` (bundled in this skill) which resolves `glimmer`, `python3 -m glimmer.tools.cli`, or a project's `vendor/glimmer/`.

Read the project's `AGENTS.md` (if present) before editing any canonical graph. Never modify vendored `vendor/glimmer/` inside a downstream project, and never rewrite immutable original source files or `sources/**/SHA256SUMS`.

## 1. Orient in One Pass (Never Open Every File)

Start every session by summarizing the graph and inspecting its enriched `_glimmer-index.json` (which carries `name`, `status`, `subtype`, `role`, `modified`, `summary`, and compact `edges`):

```sh
glimmer summary <rokb>
```

Check `node-count`, `by-type`, `star-hubs` (nodes with degree ≥ 10 such as `program-*`), `root-node`, `entrypoints`, and whether the index is enriched. If the graph has not been initialized yet, bootstrap it with:

```sh
glimmer init <rokb> --name "<project>" --with-profile --agents-snippet
```

## 2. Query & Traverse Safely (Metadata-Only by Default)

All read commands omit Markdown bodies by default (`--no-body`) so traversing star hubs never blows up context. Opt in with `--include-body` or `--body-chars 600` only for the specific nodes you need to read in full.

```sh
glimmer query <rokb> --type concept --field status=open
glimmer query <rokb> --type reference --rel challenges
glimmer neighbors <rokb> <node-id> --hops 1 --limit 25
glimmer search <rokb> "adaptive threshold feedback delay" -k 8
```

Pass `--graph exports/workspace/graph.json` to query a compiled workspace edition with the same flags. See [CLI & Query Reference](references/cli-and-query.md) for all filters (`key=value`, `key~=substr`, `key?`, `--direction`, `--format json|paths|ids`, `--emit-finding`).

## 3. Author with Epistemic Discipline

- **External literature vs. project outputs:**
  - Model cited prior work as **`type: reference`** (under `references/`), with bibliographic metadata (`authors`, `year`, `venue`, `doi`/`url`, `citekey`, `ref-kind`) and epistemic stance edges — never local `cites-dataset` / `cites-method` edges.
  - Model the project's own manuscripts, essays, and abstracts as **`type: publication`** (`role: project-output`) with `cites-*` / `aggregates` / `cites-concept` edges.
  - In existing v0.6 graphs that use `type: publication` for external papers, set `role: external-reference` (or run `glimmer migrate-references <rokb> --mode role|type`) instead of fabricating fake `cites-*` edges.
- **Record *how* evidence relates, not just *that* it relates:** Prefer epistemic stance edges (`supports`, `challenges`, `contradicts`, `overlaps-with`, `extends`, `superseded-by`) alongside `addresses-concept` so downstream readers and agents can distinguish reinforcing precedent from boundary conditions or conflicting evidence.
- **Keep `concept-kind` and local profile fields orthogonal:** Always keep core `concept-kind` (`research-question|hypothesis|theme|construct`) as the structural discriminator; use domain-profile fields (`claim-kind`, `evidence-status`, `design-status`) as orthogonal epistemic annotations.
- **Preserve honesty boundaries:** Never promote proposed studies, drafts, or cited literature into observed findings. Agent-generated `finding`, `derivative`, or `run-record` nodes must carry a grounded `reasoning-trace`.
- **Keep fast-moving drafts lightweight:** Let working prose iterate freely in `writing/` or scratch notes; register canonical milestones, submitted versions, and reviewed artifacts into the graph and `workspace.json` at milestone boundaries rather than thrashing node hashes on every sentence edit. Record method changes via `glimmer amend <rokb> <method-id> "<reason>"`.

See [Epistemic Authoring Guide](references/epistemic-authoring.md) for node templates and edge conventions.

## 4. Sync, Validate & Catch Drift

Before finishing edits — or at the start of a session after a writing sprint — check drift and sync metadata in one loop:

```sh
glimmer status <rokb>
glimmer sync <rokb>
```

- `glimmer status` surfaces body-hash mismatches, stale or unenriched `_glimmer-index.json`, schema errors/warnings, and **draft/artifact drift** (files in `writing/`, `exports/`, `artifacts/` newer than the graph or unregistered in `workspace.json`).
- `glimmer sync` recomputes body `provenance-hash` values, regenerates the enriched `_glimmer-index.json`, validates the graph, and optionally triggers a configured workspace rebuild (`--build-workspace`). Use `glimmer sync --check` in CI.

See [Sync & Drift Guide](references/sync-and-drift.md) for CI checks, migration, and recovery.

## 5. Handoff to `$glimmer-workspace`

Keep separation of concerns clean:
- Use **`$glimmer`** for canonical graph authoring, querying, search, provenance sync, and drift detection.
- Hand off to **`$glimmer-workspace`** when configuring `workspace.json`, building offline/private HTML editions (`build_workspace.py`), validating browser views, or preparing a reviewed exact-byte public release (`--audience public --release release.json`).
