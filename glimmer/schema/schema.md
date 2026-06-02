# Glimmer Schema (v0.3)

Research-object knowledge-base schema. Sidecars are YAML front-matter (mirrors shimmer-kb's `memory/*.md` pattern) when standalone, or BIDS-native JSON augmented with an `_x-glimmer` block when extending a BIDS sidecar in place. Every node is a file. Edges are properties on the source node.

v0.3 adds `experiment` (a task/acquisition paradigm as a first-class node) and `contributed-by` (a universal attribution edge with out-of-graph contributor targets). v0.2 changes from v0.1: dropped `qc-artifact` and `rater` entity types (over-indexed on QC as the canonical example). Added `finding` between `derivative` and `publication`. Agent identity is now a string field on `finding` and `derivative`, not a separate node type.

## Common front-matter (all node types)

```yaml
---
id: <kebab-case-slug>            # MUST be unique within the dataset
type: <one of: dataset|method|experiment|derivative|finding|standard|publication>
name: <human-readable name>
created: <ISO8601>
modified: <ISO8601>
provenance-hash: <sha256 of the body content; auto-computed>
edges:                           # outgoing edges; each is {type, target, optional metadata}
  - {type: <edge-type>, target: <node-id>, ...}
description: |
  Free-text agent-readable description.
---
```

## Entity types + canonical edges

### `dataset`
A BIDS-conformant dataset or sub-dataset (a subject is itself a sub-dataset). Carries DataLad coordinates so the graph is self-describing for re-fetch.

Canonical edges:
- `produced-by` → `method` node (the acquisition method)
- `derives-from` → upstream `dataset` node
- `conforms-to` → `standard` node (e.g. BIDS spec version)
- `cited-in` → `publication` node

Example sidecar fields:
```yaml
subject-id: "01"
modality: anat-T1w
scanner: "Siemens 3T TimTrio"
bids-version: "1.11.1"
datalad-superdataset: "https://github.com/OpenNeuroDatasets/ds000114"
datalad-relative-path: "sub-01/anat/sub-01_ses-test_T1w.nii.gz"
datalad-commit-sha: "abc123..."
datalad-annex-key: "MD5E-s12345--..."
```

### `experiment`
A task or acquisition **paradigm** — the experimental design under which data is acquired — as a first-class node. Distinct from `standard` because a paradigm is an *active design* (conditions, timing, regressors), not a static spec. E.g. an event-related emotional-film design, a reward task, or resting-state.

Canonical edges:
- `realized-by` → `dataset` node (the data acquired under this paradigm)
- `analyzed-by` → `method` node
- `conforms-to` → `standard` node
- `cited-in` → `publication` node

Example sidecar fields:
```yaml
task-name: emoFilm
design: naturalistic
conditions: [REST, NEU, POS, NEG]
regressors: ["salience-SRF ⊗ HRF"]
timing-source: "code/emofilm-timing"
stimulus-set: "stimuli/emofilm/*.avi"
```

### `method`
A named analysis tool, pipeline, or workflow (Nipype Interface, Node, Workflow, FSL binary, Python script).

Canonical edges:
- `applies-to` → `dataset` node
- `produces` → `derivative` node
- `validates-against` → `publication` node
- `requires-standard` → `standard` node
- `composes` → `method` (sub-methods for workflow composition)

Example sidecar fields:
```yaml
tool: fsl.BET
version: "fsl-6.0.5"
nipype-node-type: Node
parameters: {frac: 0.5, robust: true}
parameters-hash: "sha256:..."
workflow-definition-sha: "<git-sha of the .py file>"
```

### `derivative`
Output of applying a `method` to a `dataset`. First-class node, not a directory. Carries an output hash so re-runs can be verified.

Canonical edges:
- `produced-by` → `method` node
- `derives-from` → `dataset` or upstream `derivative` node
- `cited-in` → `publication` node
- `supports-finding` → `finding` node

Critical fields:
- `output-hash` — SHA-256 of the output file content; load-bearing for verifiability
- `provenance-mode` — `deterministic` (Nipype/FSL deterministic ops), `agent-inferred` (LLM-produced summary), or `stochastic` (e.g., randomized initialization)

### `finding`
An interpreted assertion grounded in one or more derivatives. The unit between "the pipeline produced this output" (a derivative) and "we wrote a paper about it" (a publication). EVI-aligned: a finding has interpretation text + evidence pointers + verifiable provenance.

Canonical edges:
- `based-on` → `derivative` or `dataset` node (the evidence chain)
- `cited-in` → `publication`
- `challenged-by` → `finding` or `publication` (contradictory evidence)
- `supports` → `finding` or `publication` (reinforcing evidence)
- `addresses-concept` → `concept` node (v0.3)

Required fields:
- `interpretation` — human-readable assertion ("Subject sub-01 T1w brain volume = 1,234,567 mm³")
- `based-on` — list of derivative or dataset node IDs

When `produced-by-agent` is set (an LLM emitted this finding rather than a deterministic computation), the `reasoning-trace` field becomes required. See `docs/agent-protocol.md` for the full verifiability contract.

### `standard`
A spec, atlas, template, or protocol. Nodes themselves, not just background metadata, so constraints can be expressed as edges and an agent can read the standard's definition directly.

Canonical edges:
- `defines` → `standard` (sub-standards)
- `versions` → `standard` (relates versions of same standard)

### `publication`
A paper draft, abstract, or preprint. Aggregates findings into a narrative.

Canonical edges:
- `cites-dataset` → `dataset`
- `cites-method` → `method`
- `cites-derivative` → `derivative`
- `cites-finding` → `finding`
- `aggregates` → `finding` (this paper aggregates these findings into its argument)

## Cross-cutting edges (`_universal-edges`)

Some edges are allowed from **any** node type; the validator unions these in regardless of the source node's `edges-allowed`.

### `contributed-by`
Attribution **as an edge**: who (or what) contributed to this node, and in what role. The target is an **out-of-graph contributor identifier** (ORCID URI preferred, else email or a kebab id) — like `publication.authors`, contributors are referenced by stable id, not required to be graph nodes. Role + identity ride as edge metadata:

```yaml
edges:
  - {type: contributed-by, target: "0000-0002-1825-0097", role: pi,       name: "Ashley VanMeter"}
  - {type: contributed-by, target: "se394@georgetown.edu", role: analyzed, name: "Shady El Damaty"}
```

Suggested roles: `pi`, `scanned`, `qc`, `coded`, `analyzed`, `drafted`, `funded`. The **who-did-what attribution layer** is derived by aggregating `contributed-by` edges across the whole graph (group by target). Because the target is out-of-graph, the validator does not require it to appear in the index.

## Index file (`_glimmer-index.json`)

At the dataset root. Lists every node ID + its file path. Mandatory load for the agent.

```json
{
  "schema": "glimmer/v0.2.0",
  "dataset-name": "ds000114-nipype-demo",
  "nodes": [
    {"id": "dataset-sub-01-T1w", "type": "dataset", "path": "datasets/sub-01-T1w.md"},
    {"id": "method-fsl-bet-6.0.5", "type": "method", "path": "methods/fsl-bet-6.0.5.md"},
    {"id": "derivative-sub-01-T1w-brain", "type": "derivative", "path": "derivatives/sub-01-T1w-brain.md"},
    {"id": "finding-sub-01-brain-volume", "type": "finding", "path": "findings/sub-01-brain-volume.md"}
  ]
}
```

## Wiki-style linking
Within the body of any sidecar, `[[node-id]]` is an inline reference resolvable by the agent.

## Versioning
Each sidecar's `provenance-hash` is computed over the body. The graph state at any time can be hashed into a single dataset-level hash for reproducibility claims.

## Verifiability requirement (agent-produced outputs)

When a `finding` or `derivative` has `produced-by-agent` set (i.e., an LLM or autonomous agent produced it, rather than a deterministic computation), the sidecar MUST include a `reasoning-trace` enumerating:

- `nodes-accessed`: every Glimmer node the agent read during the decision
- `metrics-cited`: which numeric or categorical evidence was load-bearing
- `evidence-summary`: one-paragraph justification citing node IDs inline
- `model-identifier`: the agent's stable identifier
- `timestamp`: when the output was issued

This is a hard schema requirement, not a hint. See `docs/agent-protocol.md`.

## Research-program / scientometric layer (v0.3)

Node types for the autoresearch meta-graph — people, organizations, concepts,
and hypothesis-level experiments — distinct from the imaging data layer.

### `concept`
A research concept / hypothesis under study. Edges: `authored-by` → persona,
`funded-by` → organization, `tested-by-experiment` → experiment. Optional
`outcome-data` / `outcome-access` / `sensitivity` for gated outcome variables.

### `persona`
A contributor (researcher, mentor, PI). Edges: `affiliated-with` → organization,
`leads` → organization/experiment, `mentors` → persona.

### `organization`
A lab, institution, or funder. Edge: `part-of` → organization.

Also in v0.3: `experiment.task-name` is now optional (the research-program layer
uses `experiment` for hypothesis-level designs with no single task file, adding
`depends-on-method` / `tests-hypothesis` edges); `publication` may carry
`addresses-concept` / `authored-by` edges (scout-emitted literature).
