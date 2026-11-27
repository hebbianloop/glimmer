# Sync, Bootstrap & Drift Detection Guide (v0.7.0)

## Bootstrapping a New Project (`glimmer init`)

```sh
glimmer init research-program --name "My Research Program" --domain my-domain --with-profile --agents-snippet
```

Creates standard folders (`concepts/`, `methods/`, `experiments/`, `datasets/`, `publications/`, `references/`, `standards/`, `_glimmer-amendments/`), a starter `program` node (`index.md`), an enriched `_glimmer-index.json`, and an optional local profile + `AGENTS.glimmer.md` snippet.

## Daily Authoring Loop (`glimmer status` & `glimmer sync`)

```sh
# 1. Inspect drift before editing or releasing
glimmer status research-program

# 2. Refresh body provenance hashes, rebuild enriched _glimmer-index.json, and validate
glimmer sync research-program

# 3. Optionally rebuild the workspace bundle in the same command
glimmer sync research-program --build-workspace
```

### What `glimmer status` checks
1. **Body hash drift** — sidecars whose Markdown body SHA-256 differs from `provenance-hash`.
2. **Index drift** — unindexed sidecars, dangling index entries, unenriched v0.6 indexes, or stale summary/edge metadata.
3. **Schema validation** — core + local profile errors and advisory warnings.
4. **Draft & artifact drift** — scans sibling project directories (`writing/`, `exports/`, `artifacts/`, `manuscript/`, `drafts/`, `papers/`, plus any `--watch-dir`) for files newer than the newest graph timestamp or unregistered in `workspace.json` `artifacts` / node `upstream-refs`.

### CI / Non-Destructive Check Mode

```sh
glimmer sync research-program --check      # exits 1 if hashes/index are stale or errors exist; 2 on warnings
glimmer validate research-program --json   # structured validation report
```

## Migrating v0.6 External Publications

```sh
# Preview candidate external publications (no writes)
glimmer migrate-references research-program --mode role

# Option A (zero breaking changes): add `role: external-reference` and re-sync index
glimmer migrate-references research-program --mode role --apply

# Option B (v0.7 native): convert `type: publication` -> `type: reference` and re-sync index
glimmer migrate-references research-program --mode type --apply
```

## File Hashing & Method Amendments

```sh
glimmer hash exports/figure-1.png
glimmer amend research-program method-my-pipeline "Switch normalization to v2 after QC review"
```

## Installing the Skill into a Project

```sh
glimmer install-skill                      # installs to ./.agents/skills/glimmer
glimmer install-skill --claude             # installs to ./.claude/skills/glimmer
glimmer install-skill --codex              # installs to ./.codex/skills/glimmer
glimmer install-skill --global             # installs to ~/.agents/skills/glimmer
```
