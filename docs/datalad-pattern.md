# DataLad as the Glimmer I/O Backbone

> Glimmer is a graph layer above the file tree. **DataLad is how the file tree gets written, versioned, and distributed.** This document specifies how the two compose, drawing directly from the [`hebbianloop/mrinit`](https://github.com/hebbianloop/mrinit) reproducible-MRI project that pioneered the pattern in 2020.
>
> **Choosing *where* the annex lives** (which cloud / NAS / object store) is a separate, provider-agnostic decision — see [`data-hosting.md`](data-hosting.md).

## The mrinit / DataLad superdataset pattern

A reproducible neuroimaging project rendered in DataLad has a top-level superdataset and one sub-dataset per pipeline stage. Each sub-dataset is an independent git repo, tracked via `.gitmodules` and pinned at a specific commit. The top-level superdataset is itself git-annex-managed (DataLad's storage layer); large files are content-addressed and fetched on demand.

The mrinit template instantiates this with seven independent repositories:

```
mrinit_dataset_template/                   (DataLad superdataset)
├── .datalad/                              ← DataLad configuration
├── .gitattributes                         ← git-annex large-file rules
├── .gitmodules                            ← submodule pointers (commit-pinned)
├── code/                                  → mrinit_dataset_template-code           [submodule]
├── data/
│   ├── source/                            → mrinit_dataset_template-data-source    [submodule]
│   │   ├── mri/                           → ...data-source-mri                     [submodule]
│   │   └── behav/                         → ...data-source-behav                   [submodule]
│   ├── bids/                              → ...data-bids                           [submodule]
│   └── derivatives/                       → ...data-derivatives                    [submodule]
├── docs/
└── external/                              ← external dependencies (submoduled)
```

Why this matters for Glimmer:

1. **Each sub-dataset is independently citable.** Its git SHA is a complete pin — anyone running `datalad install` against the superdataset gets exactly the state the original analysis ran on.
2. **Stages decouple.** A change to `data-derivatives` doesn't perturb `data-source`. The Glimmer `derivative` node references the specific sub-dataset commit it was produced from.
3. **The graph and the file tree are isomorphic.** A Glimmer `dataset` node maps to a sub-dataset path; a `derivative` node maps to a path under `data/derivatives/`; a `method` node maps to code at a specific commit under `code/`.

## Glimmer's DataLad I/O contract

A Glimmer project that adopts the mrinit pattern follows three rules:

1. **All persistent data is in DataLad.** Raw DICOMs, BIDS-converted scans, FreeSurfer outputs, fMRIPrep derivatives, statistical maps — every byte that an analysis depends on lives in a DataLad sub-dataset, addressable by SHA.
2. **All code is in DataLad.** The `code/` sub-dataset pins the exact version of every script, Nipype workflow, and container reference. A Glimmer `method` node points to a path-plus-commit-SHA inside this sub-dataset.
3. **Glimmer nodes carry the DataLad coordinates.** Every `dataset`, `derivative`, and `method` node sidecar includes `datalad-commit-sha` and `datalad-relative-path` fields. The graph is therefore self-describing for re-fetch: `datalad install <superdataset>; datalad get <path-from-sidecar>` reproduces exactly the bytes the analysis ran on.

## Schema fields for DataLad coordinates

Adding to the v0.1 schema (proposed for v0.1.2, non-breaking minor):

```yaml
# common-optional fields, available on dataset / method / derivative
datalad-superdataset: string              # URL or path of the top-level DataLad dataset
datalad-relative-path: string             # relative path within the superdataset
datalad-commit-sha: string                # the pinned commit of the containing sub-dataset
datalad-annex-key: string                 # for individual files: their git-annex content hash
```

These fields are optional in v0.1.1 and recommended in v0.1.2. A Glimmer instance without them is still valid; a Glimmer instance with them is **fully re-fetchable** from the graph alone.

## The full DataLad + Nipype + Glimmer loop

```
┌─────────────────────────────────────────────────────────────┐
│  Experiment Factory container generates raw data            │
│   ↓                                                         │
│  datalad save → new commit in data-source sub-dataset       │
│   ↓                                                         │
│  Glimmer emits a `dataset` node with the new commit SHA     │
│                                                             │
│  Nipype workflow reads the dataset path-at-SHA              │
│   ↓                                                         │
│  Workflow produces derivatives (NIfTI, surface, stat maps)  │
│   ↓                                                         │
│  datalad save → new commit in data-derivatives              │
│   ↓                                                         │
│  Glimmer emits a `derivative` node:                         │
│    - produced-by: → method-nipype-fmriprep-23.0.2           │
│    - derives-from: → dataset-sub-01-T1w                     │
│    - datalad-commit-sha: <pinned>                           │
│                                                             │
│  Verification agent walks the graph + re-runs methods,      │
│    compares output-hashes, emits a verification `finding`   │
│    with reasoning-trace per the agent protocol              │
│                                                             │
│  Synthesis agent walks the graph + emits draft publication  │
│    citing the chain of evidence                             │
│                                                             │
│  datalad save → new commit (entire graph + all artifacts)   │
│   ↓                                                         │
│  Result: a single SHA at the superdataset level captures    │
│  the full state — data, code, derivatives, graph, drafts.   │
└─────────────────────────────────────────────────────────────┘
```

Every step is verifiable. Every output cites its inputs by content-hash. The Glimmer graph isn't a fragile parallel database — it's a thin reasoning layer over a DataLad superdataset that is itself the source of truth.

## How this relates to the format-agnostic position

Earlier docs argued for a "two-tier" Glimmer/BIDS sidecar strategy. The deeper point is simpler: **format doesn't matter if the agent can translate between formats.** What matters is that the data has the structure the schema requires.

The DataLad pattern reinforces this: a DataLad sub-dataset is just a git repo. The sidecars in it can be JSON (BIDS-conformant), YAML+MD (Glimmer-native), or any other structured format the agent can parse. The Glimmer agent's job is to compile the graph in memory from whatever the sub-datasets contain, and emit new sidecars in whichever format the consumer expects.

So:

- **The schema is the contract.** Required fields, edge types, validator rules.
- **The format is incidental.** YAML, JSON, JSON-LD, TOML — pick what the downstream tool ecosystem wants.
- **The agent is the translator.** Reading and writing across formats is the agent's responsibility, not the schema author's.

The validator's job is to confirm that the *structure* (after format translation) conforms to the schema. The file format choice is a deployment decision, not an architectural one.

## Worked-example plan: Nipype + PyMVPA + a public DataLad dataset

For v0.2 we will ship a Nipype-based worked example that demonstrates verifiability end-to-end:

1. **Public DataLad dataset.** [OpenNeuro ds000114](https://openneuro.org/datasets/ds000114) (Pernet et al., test-retest BIDS dataset for QC studies; ~10 subjects, multiple modalities, public via DataLad URL). Cloning the dataset is a single `datalad install ///openneuro/ds000114` command.

2. **Nipype workflow.** A minimal anatomical preprocessing workflow (BET → FAST → registration to MNI). Each Nipype `Node` becomes a Glimmer `method` node; each `Workflow` becomes a `method` of `tool: nipype-workflow`. The workflow's outputs are saved into a `derivatives` sub-dataset and registered as `derivative` nodes.

3. **PyMVPA verifiable analysis.** [PyMVPA](http://www.pymvpa.org) for a cross-validated classification analysis on a subset of the dataset. The classifier output (accuracy, confusion matrix, permutation-test p-value) is a `derivative` node with `provenance-mode: deterministic`. The agent reasoning over this graph can verify the result by re-running the analysis at the cited commit SHA.

4. **Agent verification.** A Glimmer agent walks the graph, reads the PyMVPA derivative node, and produces a `finding` attesting that the reported accuracy is consistent with the input data and the analysis spec. The finding's `reasoning-trace` includes:
   - The Nipype workflow definition SHA
   - The input dataset commit SHA
   - The PyMVPA result file's git-annex key
   - A re-computation of a key summary statistic that the agent can independently verify

This worked example is the operational realization of the "verifiability of analysis" requirement.

### DataLad is general-purpose, not neuro-specific

DataLad's superdataset pattern is domain-general. The `mrinit` project happens to instantiate it for MRI data, but the same pattern (superdataset + per-stage sub-datasets + content-addressed storage) applies to any project structure that follows the research-harness pattern: raw inputs in one sub-dataset, code in another, derivatives in a third, with the superdataset coordinating their pinned commits. The Glimmer node types (`dataset`, `method`, `derivative`, `finding`) describe positions in this pattern, not MRI-specific concepts. A genomics pipeline running on DataLad, a climate-modeling run, or a particle-physics analysis with the same staged-substructure can adopt Glimmer unchanged.

### Source-first sanity check

A discipline borrowed from years of running multi-year neuroimaging projects: when a verification fails or a pipeline goes sideways, the recovery move is often to rebuild the method from upstream source rather than trust the cached binary. The Glimmer schema makes this expressible via optional `source-checkout-url` and `source-build-instructions` fields on `method` nodes; the verifier can fall back to a source rebuild when output-hash drift is detected. The schema doesn't enforce a source-rebuild on every verification (that would be prohibitively slow); it makes the fallback available when the cheap path fails.

## Nipype-to-Glimmer schema mapping

Nipype concepts map onto Glimmer entities as follows:

| Nipype concept | Glimmer entity | Notes |
|---|---|---|
| `Interface` (e.g., `fsl.BET`) | `method` (atomic) | `tool` field is the interface name; `version` is the wrapped binary's version |
| `Node` (an `Interface` instance) | `method` (instantiated) | Inherits from the atomic `method`; adds the specific parameters used |
| `Workflow` (a DAG of Nodes) | `method` (composite) with `tool: nipype-workflow` | Body field carries the serialized workflow definition |
| `MapNode` (per-iterable Node) | `method` with `iterates-over: <field>` annotation | New optional field for v0.2 |
| Workflow input | `derives-from: → dataset` edge | The data the workflow consumes |
| Workflow output | `produces: → derivative` edge | Each output is its own `derivative` node |
| Workflow execution result | `derivative` with `provenance-mode: deterministic` | The actual file(s) produced on disk |
| Connection between Nodes | (implicit in workflow body) | Captured by the workflow's serialized DAG; not promoted to a Glimmer edge |

The mapping makes a Nipype project transparent to Glimmer: a Glimmer agent can read a workflow's DAG, identify which atomic Interfaces it composes, and reason about which derivatives are produced where.

## Why DataLad and not just git-LFS

git-LFS handles large-file storage but does not provide the sub-dataset / superdataset model. A Glimmer project running on git-LFS alone cannot pin a state across many independent repositories. DataLad's superdataset abstraction is what makes the whole-graph SHA possible. The cost is a slightly steeper learning curve and a Python dependency. The benefit is composability.

When git-LFS is sufficient (a single-repo project, no sub-dataset decomposition), Glimmer still works — it just falls back to single-repo content-hashing. The DataLad fields in the schema are optional.
