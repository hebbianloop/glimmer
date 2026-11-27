# Changelog

All notable changes to Glimmer (`glimmer-rokb`) are documented in this file.

## [0.7.0] - 2026-11-26

### Added
- **Live query & traversal CLI (`glimmer/tools/query.py`)**:
  - `glimmer summary <rokb>`: type/status/role breakdowns, star-hub detection, root/entrypoints, modified range, and index enrichment status.
  - `glimmer query <rokb>`: filter by `--type`, repeatable `--field` (`key=value`, `key~=substr`, `key?`), `--rel`, `--direction`, `--source`/`--target`, `--limit`, `--format table|json|paths|ids`, metadata-only by default (`--no-body`) with opt-in `--include-body` / `--body-chars`.
  - `glimmer neighbors <rokb> <id>`: `--hops N` breadth-first traversal with edge filtering and metadata-only default.
  - `glimmer search <rokb> "<query>"`: ranked search with snippet locators and optional `--emit-finding`.
  - `--graph` flag on all query commands to inspect compiled `glimmer-workspace` `graph.json` files.
- **Built-in stdlib BM25 retriever (`glimmer/tools/retrieval.py`)**:
  - Shipped `Bm25Retriever` and `NullRetriever` directly in core (weighted title/summary/body indexing, section/line locators, deterministic index SHA, idempotent on `(id, provenance-hash)`).
- **Rich, backwards-compatible `_glimmer-index.json`**:
  - Optional top-level `root-node`, `entrypoints`, `generated-at` and per-node `name`, `status`, `subtype`, `claim-kind`, `role`, `modified`, `provenance-hash`, `summary`, and compact `edges`.
- **Clean external literature vs. project outputs (Schema v0.7.0)**:
  - Added core `reference` node type (`ref-kind`, `authors`, `year`, `venue`, `doi`, `url`, `citekey`, `pub-status`) for external cited works.
  - Added backwards-compatible `role: project-output | external-reference` on `publication` so v0.6 graphs clear false `publication has no cites-* edges` warnings without forced re-typing.
  - Added epistemic stance edges (`supports`, `challenges`, `contradicts`, `overlaps-with`, `extends`, `superseded-by`, `cites-concept`) across `reference`, `publication`, `concept`, and `finding`.
- **Authoring, bootstrap & drift detection (`glimmer/tools/sync.py`)**:
  - `glimmer init`, `glimmer sync` (with `--check` and `--build-workspace`), `glimmer status` (body-hash, index, validation, and sibling draft/artifact drift), `glimmer hash`, `glimmer amend`, and `glimmer migrate-references`.
- **Packaged Agent Skill (`skills/glimmer/` + `glimmer install-skill`)**:
  - Cross-agent skill (`SKILL.md`, `agents/openai.yaml`, `references/`, `scripts/glimmer-cli.py`) installable into `.agents/skills/glimmer`, `.claude/skills/glimmer`, or `.codex/skills/glimmer`.

### Changed
- Bumped `glimmer-version`, `frontmatter.yaml`, and `pyproject.toml` to `0.7.0`.
- Added `--strict` and `--json` flags to `glimmer validate`.
- `examples/retrieval-adapter/bm25_retriever.py` now re-exports core `Bm25Retriever` and `NullRetriever`.

## [0.6.0] - 2026-11-11

- Added `run-record` node type and fail-closed `glimmer run` / `glimmer rerun` verifier with standards gates, registered DataLad container execution, four verification tiers, and container qualification evidence.
