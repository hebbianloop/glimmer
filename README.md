# Glimmer

> **A research-object knowledge base for AI-native scientific workflows.**
>
> Reproducibility is a knowledge-graph problem, not a tooling problem. Glimmer is the graph layer.

[![Status: v0.1](https://img.shields.io/badge/status-v0.1-blue.svg)](https://github.com/hebbianloop/glimmer)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Template](https://img.shields.io/badge/repo-template-purple.svg)](https://github.com/hebbianloop/glimmer/generate)

## What this is

Existing standards (BIDS, DataLad, NIDM) give your project syntactic structure. Glimmer adds the **graph layer**: methods, datasets, derivatives, QC artifacts, raters, and standards become first-class typed nodes with versioned edges, distributed across per-entity sidecars. An AI agent traverses the graph to render decisions with auditable reasoning traces.

Glimmer is the architectural pattern + a reference implementation. The full case for it is in the CAISC 2026 paper *Reproducibility as Knowledge Graph Navigation* (see [`docs/paper-citation.md`](docs/paper-citation.md)).

## How to use this repo

### If you're building a project on top of Glimmer

**Fork or use-as-template** (the green button on GitHub). Then:

1. Keep the `glimmer/` directory unchanged — that's the core schema + tooling.
2. Replace `examples/training-fsqc/` with your own project data and sidecars.
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
│   ├── schema.md            # v0.1 spec — 7 entity types, edge taxonomy, sidecar format
│   └── glimmer-version      # current core version
└── tools/
    ├── build_rokb.py        # reference builder: assemble a Glimmer RO-KB from typed data
    ├── agent.py             # reference QC agent over a Glimmer graph
    ├── score.py             # inter-rater κ scorer with Glimmer-format inputs
    └── figure_schema.py     # render the schema diagram from glimmer/schema/

examples/
└── training-fsqc/           # worked example from the CAISC 2026 paper
    ├── raw/                 # the source CSV (3 subjects × 7 raters × 7 categories)
    ├── rokb/                # generated Glimmer-conformant RO-KB (30 nodes)
    └── README.md            # walks through the build + agent + score loop

docs/
├── paper-citation.md        # how to cite Glimmer + the CAISC 2026 paper
├── design-rationale.md      # why typed-entity sidecars over a central database
├── extending-the-schema.md  # process for proposing new node/edge types
└── faq.md
```

## Quick start

```bash
# 1. Generate the worked example
python glimmer/tools/build_rokb.py --example training-fsqc

# 2. Run the reference agent (requires LLM API access — see docs/agent-setup.md)
python glimmer/tools/agent.py --rokb examples/training-fsqc/rokb/ --output verdicts.json

# 3. Score against the ground-truth ratings included in the example
python glimmer/tools/score.py --verdicts verdicts.json --rokb examples/training-fsqc/rokb/
```

## Core principles

1. **Distributed-over-files, not centralized.** Glimmer graphs survive `git clone`, `datalad export`, `rsync` without bespoke serialization.
2. **Typed entities, not flat documents.** Different entity types invite different agent reasoning strategies.
3. **Edges are first-class.** Every relationship a researcher would name out loud should be an edge in the graph.
4. **Standards are nodes, not background.** BIDS spec versions, FreeSurfer releases, atlas versions are addressable, not implicit.
5. **Provenance is intrinsic.** Every node carries a content hash; every edge carries a version.

## Versioning policy

Glimmer follows semantic versioning at the **schema** level. Core utility updates that don't change the schema are minor; schema changes that break existing sidecars are major. The current schema version is recorded in `glimmer/schema/glimmer-version`.

## Citation

If you use Glimmer in your research, cite:

> El Damaty, S. (2026). *Reproducibility as Knowledge Graph Navigation: Glimmer, a Research-Object Knowledge Base for AI-Native Neuroimaging Analysis.* Conference for AI Scientists 2026.

See [`docs/paper-citation.md`](docs/paper-citation.md) for the BibTeX entry.

## License

MIT.
