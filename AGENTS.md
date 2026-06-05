# AGENTS.md — Operating Instructions for AI Agents

> This file tells an AI coding agent (Claude Code, Cursor, Aider, an autonomous agent driven by the Glimmer reference agent) how to work productively in this repository.
>
> If you are an AI agent reading this: **load this file first**, then `README.md`, then `glimmer/schema/schema.md`. After that you have enough context to do useful work.

## What this repo is

This is Glimmer, a research-object knowledge-base (RO-KB) architecture for AI-native scientific workflows. The full motivation lives in `README.md`; the architectural claim lives in the CAISC 2026 paper cited in `docs/paper-citation.md`.

## Two-tier mental model

The repo is split into two zones. **Touch the right zone for the work you're doing.**

| Zone | Path | What it is | When to modify |
|---|---|---|---|
| **Core** | `glimmer/` | The Glimmer schema spec and the reference tooling (builder, agent, scorer, validator, CLI). | Only when implementing a change to the architectural pattern itself. Schema additions go through the RFC process in `docs/extending-the-schema.md`. |
| **Project** | `examples/`, `docs/` (project-specific entries) | Specific datasets, project-tailored agents, project documentation. | Freely. Each example is independent. |

If you are unsure which zone you are in: assume **project**. Only touch `glimmer/` if a human reviewer has explicitly asked — **except** for domain profiles, which you are encouraged to author (see below).

## Domain profiles — the encouraged path for domain-specific fields

Glimmer's core node types are **domain-neutral**. Fields specific to a *kind* of data (BIDS modality for neuroimaging, assay for genomics, response device for a behavioral task) live in a **domain profile**, never hard-coded into the core schema. Authoring profiles is **encouraged**, not gated — this is the normal way to adapt Glimmer to new data.

There are three places domain knowledge can go. Pick the lightest one that fits:

| You need… | Do this | RFC? Touches core? |
|---|---|---|
| domain-specific **fields** for *your* data, now | **local profile**: `<rokb>/_glimmer-profiles/<domain>.yaml` (the safe, encouraged zone) | No / No |
| those fields to become **reusable** across projects | **PR a curated profile** into `glimmer/schema/profiles/<domain>.yaml` — maintainers review and add it to the library | No / library-only, reviewed |
| a brand-new **node type or edge type** | core schema change | **Yes** — `schema-rfc:` issue |

**Decision flow when you bring new data:**
1. **Discover** what already exists — run `glimmer validate <rokb>` (it prints a `Profiles:` line with the active profiles + tier), or browse `glimmer/schema/profiles/`.
2. Does a listed profile's `standard` match your data's domain? → **use it**: set `default-domain` in `_glimmer-index.json` (whole KB) or `domain:` on individual nodes. Done.
3. No match, but you only need extra *fields*? → **write a local profile** (template below) in `<rokb>/_glimmer-profiles/`. No RFC, no core edit. `glimmer validate` will then enforce it.
4. Is your profile stable and useful to others? → **PR it upstream** into `glimmer/schema/profiles/` so it joins the shared library. This is welcomed — the library grows from researcher contributions.
5. Need a new node/edge *type* (not just fields)? → stop and open a `schema-rfc:` issue.

The intended lifecycle is exactly: *get started → discover you need a profile → write it locally in the safe zone → use it → PR it into the core library → reviewed and added if it makes sense.*

Minimal local profile:
```yaml
# <rokb>/_glimmer-profiles/behavioral.yaml
profile: behavioral
standard: Psych-DS          # or your own lab convention
status: local
augments:
  dataset:
    required: {participant-id: string}
    optional: {n-trials: int}
```
Full format and constraints: `glimmer/schema/profiles/_profile.schema.yaml`. A profile may only **add fields to existing node types** — it cannot define new node types or edge types (those are core changes, gated by the RFC process).

## Setup

```bash
# Python 3.10+
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt    # numpy, matplotlib, pyyaml, networkx
```

Optional: set `OPENROUTER_API_KEY` (or `ANTHROPIC_API_KEY`) in your environment if you intend to run the reference agent.

## Building the worked example

```bash
glimmer build --example training-fsqc
```

This invokes `glimmer/tools/build_rokb.py` and produces `examples/training-fsqc/rokb/` — a 30-node Glimmer instance.

If you just want to verify the build is clean:

```bash
glimmer validate examples/training-fsqc/rokb/
```

## Common agent tasks and where to do them

| Task | Where | Notes |
|---|---|---|
| Add domain-specific **fields** for a kind of data | `<rokb>/_glimmer-profiles/<domain>.yaml` (local), then PR to `glimmer/schema/profiles/` | **No RFC** — see Domain profiles above. The encouraged path. |
| Add a new entity **type** or **edge type** to the schema | `glimmer/schema/schema.md` + `glimmer/schema/frontmatter.yaml` | RFC process required — see `docs/extending-the-schema.md`. |
| Apply Glimmer to a new dataset | New subdirectory in `examples/` | Start by adapting `examples/training-fsqc/`. |
| Improve the reference agent | `glimmer/tools/agent.py` | Keep it minimal — see `docs/design-rationale.md` on why the agent's tool set is deliberately small. |
| Add interoperability with BIDS / NIDM / RO-Crate | `glimmer/tools/import_*.py`, `glimmer/tools/export_*.py` | See `docs/interop.md` for the cross-standard mapping. |
| Add a project-specific agent (analysis-trace verification, finding synthesis, literature review) | Inside your project's directory under `examples/` | Reuse the primitives in the reference agent in the canonical example; do not add domain logic to the core. |
| Verify a trace | `python examples/<your-example>/verify.py` | Re-runs each derivative's method on its cited dataset SHA + compares output hashes. |

## Conventions

- **Sidecars are YAML-front-matter Markdown by default.** JSON sidecars are valid for nodes that consume from existing JSON-only tooling (BIDS).
- **Edges are properties on the source node.** Do not store edges in a separate edge file or table.
- **Provenance hashes are SHA-256 of the body content.** Recomputed on every write.
- **Wiki-style references in the body** (`[[node-id]]`) are resolvable by the agent at traversal time.
- **No graph database.** The graph is the file tree. Survives `git clone`, `datalad export`, `rsync`.

## Output style for agents working in this repo

When you write code: prefer small, composable scripts over frameworks. When you write documentation: prefer concrete examples over abstract description. When you write commit messages: lead with the architectural delta, not the file list.

When you encounter a schema-shape question that is not answered by `glimmer/schema/schema.md`: do not improvise on the **core**. If you just need extra *fields* for your domain, that's a **domain profile** — write one (see *Domain profiles*); this is expected and safe. If you need a new **node type or edge type**, open an issue with `schema-rfc:` prefix and stop — the core schema is the load-bearing artifact, and bending it silently breaks downstream forks.

## Self-test before considering work done

Run these in order and confirm all pass before reporting a task complete:

```bash
# Build the canonical worked example (requires DataLad + Nipype + FSL)
cd examples/ds000114-nipype
bash install.sh
python workflow.py
python emit_graph.py

# Validate the emitted graph against the schema
glimmer validate rokb/

# Verify the trace — re-run the cited methods, confirm output hashes match
python verify.py
```

For changes that touch the schema or the verification routine: re-run `verify.py` on the canonical example and confirm the verifiability rate remains at 100% for deterministic operations. Drift indicates your change has altered the architectural claim — surface it explicitly in the PR.

When working without FSL installed locally, the architectural changes can still be validated against the schema (`glimmer validate`) without running the workflow. Just don't claim the workflow ran.

## Things to never do

- Do not add a new **node type or edge type** without an open `schema-rfc:` issue. (Adding domain-specific **fields** is a profile, not a schema change, and is encouraged — see *Domain profiles*. Local profiles under `<rokb>/_glimmer-profiles/` need no RFC.)
- Do not bake project-specific data, API keys, or participant identifiers into anything under `glimmer/`.
- Do not break the file-tree-as-graph property by introducing a database dependency in the core.
- Do not silently rename node types or edge types — these are part of the schema contract and downstream forks rely on them.

## Citation

If your work depends on Glimmer, see `docs/paper-citation.md` for the BibTeX entry.
