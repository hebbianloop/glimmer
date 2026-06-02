# Glimmer

> **A research-object knowledge base for AI-native scientific workflows.**
>
> The 2010s gave us reproducible pipelines. Glimmer is the next layer up — the typed-entity graph that makes the agentic feedback loop traversable over those pipelines.

[![Status: v0.3](https://img.shields.io/badge/status-v0.3-blue.svg)](https://github.com/hebbianloop/glimmer)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Template](https://img.shields.io/badge/repo-template-purple.svg)](https://github.com/hebbianloop/glimmer/generate)

## What this is

Existing standards (BIDS, DataLad, NIDM, Nipype) give your project syntactic structure. Glimmer adds the **graph layer**: datasets, methods, derivatives, findings, standards, and publications become first-class typed nodes with versioned edges, distributed across per-entity sidecars. An AI agent traverses the graph to render verifiable decisions with auditable reasoning traces.

Glimmer is domain-agnostic. The canonical worked example in this repo is neuroimaging because that's where standards like BIDS and tools like DataLad and Nipype are most developed — but the architectural pattern (typed-entity graph over a versioned-data substrate) applies to any compute-intensive scientific domain backed by a mature standards ecosystem.

Glimmer is the architectural pattern + a reference implementation. The full case for it is in the CAISC 2026 paper (see [`docs/paper-citation.md`](docs/paper-citation.md)).

## How to use this repo

### If you're building a project on top of Glimmer

**Fork or use-as-template** (the green button on GitHub). Then:

1. Keep the `glimmer/` directory unchanged — that's the core schema + tooling.
2. Replace `examples/ds000114-nipype/` with your own project data and sidecars (or keep it as reference).
3. Pin the Glimmer core version in your project's `glimmer-version` file.
4. Do your project work in your fork. **Don't modify `glimmer/` in your fork** unless you intend to send a PR back here.

### If you have an improvement to the Glimmer core

**Open a PR against this repo.** Core changes go through review here so every downstream fork can pick them up cleanly:

- Schema additions or edge taxonomy changes → PR to `glimmer/schema/`
- Bug fixes or new utilities → PR to `glimmer/tools/`
- New documentation or examples → PR to `docs/` or `examples/`

The line between "core" and "project" is the `glimmer/` directory. Anything inside is core; anything outside is your project. The maintainer's job is to keep `glimmer/` stable, small, and self-contained.

## Repo layout

```
glimmer/
├── schema/
│   ├── schema.md            # v0.3 spec — 8 entity types, edge taxonomy, sidecar format
│   ├── frontmatter.yaml     # machine-readable contract for validators
│   └── glimmer-version      # current core version (0.3.0)
└── tools/
    ├── validate.py          # schema validator (enforces agent-protocol verifiability)
    ├── cli.py               # `glimmer` CLI single entry point
    └── figure_schema.py     # render the schema diagram

examples/
└── ds000114-nipype/         # canonical worked example from the CAISC 2026 paper
    ├── install.sh           # `datalad install ///openneuro/ds000114` + selective `datalad get`
    ├── workflow.py          # Nipype anatomical preprocessing (BET → FAST)
    ├── emit_graph.py        # walk the workflow's provenance + emit Glimmer sidecars
    ├── verify.py            # re-run the cited methods + confirm output hashes match
    └── rokb/                # generated Glimmer instance after running the steps above

docs/
├── paper-citation.md        # how to cite Glimmer + the CAISC 2026 paper
├── design-rationale.md      # why typed-entity sidecars over a central database
├── extending-the-schema.md  # process for proposing new node/edge types
├── agent-protocol.md        # the verifiability contract for agent-produced outputs
├── agentic-loop.md          # plans-as-issues + autoresearch over a Glimmer graph
├── datalad-pattern.md       # DataLad as the I/O backbone (mrinit's pattern, generalized)
├── interop.md               # cross-reading BIDS / NIDM / RO-Crate / JSON-LD / schema.org
├── roadmap.md               # v0.3+ entity types (persona, concept, experiment, meta-analysis)
└── faq.md
```

## Quick start

```bash
# Install dependencies
pip install -r requirements.txt
# FSL must be on PATH (or use the nipreps/fmriprep Docker container)

# Run the canonical example end-to-end
cd examples/ds000114-nipype
bash install.sh                    # ~30 MB DataLad fetch (sub-01 T1w + dataset metadata)
python workflow.py                 # runs BET + FAST, produces derivatives + provenance.json
python emit_graph.py               # walks provenance + emits Glimmer sidecars under rokb/

# Validate the emitted graph
python ../../glimmer/tools/validate.py rokb/

# Verify the trace (re-runs each method from the graph's pinned SHAs + compares hashes)
python verify.py
```

## Core principles

1. **Distributed-over-files, not centralized.** Glimmer graphs survive `git clone`, `datalad export`, `rsync` without bespoke serialization.
2. **Typed entities, not flat documents.** Different entity types invite different agent reasoning strategies.
3. **Edges are first-class.** Every relationship a researcher would name out loud should be an edge in the graph.
4. **Standards are nodes, not background.** BIDS spec versions, FreeSurfer releases, atlas versions are addressable, not implicit.
5. **Provenance is intrinsic.** Every node carries a content hash; every edge carries a version. Re-running a workflow from the graph's pinned SHAs is the verifiability test.
6. **Source-first sanity check.** When a verification fails or a pipeline goes sideways, rebuilding the method from upstream source is often the recovery move. The schema makes this expressible (`source-checkout-url`, `source-build-instructions`) and the verifier can fall back to a source-rebuild rather than trusting a cached binary that may have drifted.

## Versioning policy

Glimmer follows semantic versioning at the **schema** level. Core utility updates that don't change the schema are minor; schema changes that break existing sidecars are major. The current schema version is recorded in `glimmer/schema/glimmer-version`.

v0.3 added the `experiment` node type (active task/acquisition paradigms), the `concept` node type (the research-question / hypothesis layer a program operates at), and the universal `contributed-by` attribution edge.

v0.2 dropped `qc-artifact` and `rater` (over-indexed on QC as the canonical example) and added `finding` (EVI-aligned) between `derivative` and `publication`. Agent identity is now a string field on `finding` and `derivative` rather than a separate node type.

## Citation

If you use Glimmer in your research, cite:

> El Damaty, S. (2026). *Reproducibility as Knowledge Graph Navigation: Glimmer, a Research-Object Knowledge Base for AI-Native Neuroimaging Analysis.* Conference for AI Scientists 2026.

See [`docs/paper-citation.md`](docs/paper-citation.md) for the BibTeX entry.

## License

MIT.
