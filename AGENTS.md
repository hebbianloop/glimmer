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

If you are unsure which zone you are in: assume **project**. Only touch `glimmer/` if a human reviewer has explicitly asked.

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
| Add a new entity type to the schema | `glimmer/schema/schema.md` + `glimmer/schema/frontmatter.yaml` | RFC process required — see `docs/extending-the-schema.md`. |
| Apply Glimmer to a new dataset | New subdirectory in `examples/` | Start by adapting `examples/training-fsqc/`. |
| Improve the reference agent | `glimmer/tools/agent.py` | Keep it minimal — see `docs/design-rationale.md` on why the agent's tool set is deliberately small. |
| Add interoperability with BIDS / NIDM / RO-Crate | `glimmer/tools/import_*.py`, `glimmer/tools/export_*.py` | See `docs/interop.md` for the cross-standard mapping. |
| Add a project-specific agent (fMRI QC, DWI QC, behavior coding) | Inside your project's directory under `examples/` | Reuse the primitives in `glimmer/tools/agent.py`; do not add domain logic to the core. |
| Run inter-rater scoring | `glimmer/tools/score.py` | Inputs: a verdicts JSON from the agent, an RO-KB directory. Outputs: a κ matrix + figure. |

## Conventions

- **Sidecars are YAML-front-matter Markdown by default.** JSON sidecars are valid for nodes that consume from existing JSON-only tooling (BIDS).
- **Edges are properties on the source node.** Do not store edges in a separate edge file or table.
- **Provenance hashes are SHA-256 of the body content.** Recomputed on every write.
- **Wiki-style references in the body** (`[[node-id]]`) are resolvable by the agent at traversal time.
- **No graph database.** The graph is the file tree. Survives `git clone`, `datalad export`, `rsync`.

## Output style for agents working in this repo

When you write code: prefer small, composable scripts over frameworks. When you write documentation: prefer concrete examples over abstract description. When you write commit messages: lead with the architectural delta, not the file list.

When you encounter a schema-shape question that is not answered by `glimmer/schema/schema.md`: do not improvise. Open an issue with `schema-rfc:` prefix and stop. The schema is the load-bearing artifact; bending it silently breaks downstream forks.

## Self-test before considering work done

Run these in order and confirm all pass before reporting a task complete:

```bash
glimmer build --example training-fsqc   # rebuilds the example cleanly
glimmer validate examples/training-fsqc/rokb/   # exits 0
python -c "import yaml; [yaml.safe_load(open(f).read().split('---\n')[1]) for f in __import__('glob').glob('examples/training-fsqc/rokb/**/*.md', recursive=True)]"   # every sidecar parses as YAML
```

For changes that touch `glimmer/tools/agent.py`: re-run the agent on the example in both `--blind` and `--informed` conditions and confirm the agent's mean κ against the seven humans remains within ±0.05 of the reported values (blind ≈ +0.07, informed ≈ +0.58). Drift outside this range indicates your change has altered the architectural claim — surface it explicitly.

## Things to never do

- Do not modify `glimmer/schema/schema.md` without an open `schema-rfc:` issue.
- Do not bake project-specific data, API keys, or participant identifiers into anything under `glimmer/`.
- Do not break the file-tree-as-graph property by introducing a database dependency in the core.
- Do not silently rename node types or edge types — these are part of the schema contract and downstream forks rely on them.

## Citation

If your work depends on Glimmer, see `docs/paper-citation.md` for the BibTeX entry.
