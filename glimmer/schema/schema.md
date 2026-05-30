# Glimmer Schema (v0.2)

Research-object knowledge-base schema. Sidecars are YAML front-matter (mirrors shimmer-kb's `memory/*.md` pattern) when standalone, or BIDS-native JSON augmented with an `_x-glimmer` block when extending a BIDS sidecar in place. Every node is a file. Edges are properties on the source node.

v0.2 changes from v0.1: dropped `qc-artifact` and `rater` entity types (over-indexed on QC as the canonical example). Added `finding` between `derivative` and `publication`. Agent identity is now a string field on `finding` and `derivative`, not a separate node type.

## Common front-matter (all node types)

```yaml
---
id: <kebab-case-slug>            # MUST be unique within the dataset
type: <one of: dataset|method|derivative|finding|standard|publication>
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
