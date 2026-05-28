# Glimmer Schema (v0.1)

Research-object knowledge-base schema. Sidecars are YAML front-matter (mirrors shimmer-kb's
`memory/*.md` pattern). Every node is a file. Edges are properties.

## Common front-matter (all node types)

```yaml
---
id: <kebab-case-slug>            # MUST be unique within the dataset
type: <one of: dataset|method|derivative|standard|qc-artifact|rater|publication>
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
A BIDS-conformant dataset or sub-dataset (a subject is itself a sub-dataset). Sidecar lives at
the dataset/subject root.

Canonical edges:
- `produced-by` → `method` node
- `derives-from` → upstream `dataset` node
- `conforms-to` → `standard` node (e.g. BIDS spec version)
- `has-qc-artifact` → `qc-artifact` node
- `cited-in` → `publication` node

Example sidecar fields:
```yaml
subject-id: "001"
session: null
modality: anat-T1w
acquisition-date: 2016-08-15
scanner: "Siemens 3T TimTrio"
```

### `method`
A named analysis (a tool, a pipeline, a manual procedure).

Canonical edges:
- `applies-to` → `dataset` node
- `produces` → `derivative` node
- `validates-against` → `publication` node (reference paper)
- `requires-standard` → `standard` node

Example sidecar fields:
```yaml
tool: recon-all
version: "freesurfer-6.0.0"
parameters: { ... }
parameters-hash: sha256:...
```

### `derivative`
Output of applying a `method` to a `dataset`. First-class node, not a directory.

Canonical edges:
- `produced-by` → `method` node
- `derives-from` → `dataset` node (input)
- `has-qc-artifact` → `qc-artifact` node

### `standard`
A spec, atlas, template, or rating scale. Nodes themselves, not just background metadata.

Canonical edges:
- `defines` → `standard` (sub-standards if any)
- `versions` → `standard` (relates versions of same standard)

Example sidecar fields (rating scale):
```yaml
scale-type: ordinal
scale: {0: "no edits", 1: "local errors but no editing", ...}
```

### `qc-artifact`
A QC pass/fail decision, a manual edit record, a visual report, an automated metric.

Canonical edges:
- `attests-to-quality-of` → `dataset` or `derivative` node
- `issued-by` → `rater` node (or `method` node if automated)
- `conforms-to` → `standard` node (which rating scale)

Example sidecar fields:
```yaml
ratings:
  pial-surface: 4
  skull-strip: 0
  ...
notes: "removed dura and edited wm mask"
```

### `rater`
A human (or AI agent) who issued QC judgments. Tracked because inter-rater reliability is itself
an artifact in the graph.

Canonical edges:
- `issued` → `qc-artifact` nodes
- `trained-on` → `standard` (which rating scale)

Example sidecar fields:
```yaml
role: "human"   # or "agent"
expertise: "senior"
training-date: 2016-08
```

### `publication`
A paper draft, abstract, or preprint.

Canonical edges:
- `cites-dataset` → `dataset` nodes
- `cites-method` → `method` nodes
- `cites-derivative` → `derivative` nodes
- `authored-by` → external person identifier (out-of-graph)

## Index file (`_glimmer-index.json`)

At the dataset root. Lists every node ID + its file path. Mandatory load for the agent.

```json
{
  "schema": "glimmer/v0.1",
  "dataset-name": "Training-FSQC",
  "nodes": [
    {"id": "subject-001", "type": "dataset", "path": "subjects/subject-001.md"},
    {"id": "standard-ads-qc-scale", "type": "standard", "path": "standards/ads-qc-scale.md"},
    {"id": "rater-shady", "type": "rater", "path": "raters/shady.md"},
    {"id": "qc-shady-on-001", "type": "qc-artifact", "path": "qc-artifacts/shady-on-001.md"},
    ...
  ]
}
```

## Wiki-style linking
Within the body of any sidecar, `[[node-id]]` is an inline reference resolvable by the agent.
Used for prose annotations that should travel as graph edges (e.g., "this scan has a similar
defect to `[[subject-007]]`").

## Versioning
Each sidecar's `provenance-hash` is computed over the body. The graph state at any time can be
hashed into a single dataset-level hash for reproducibility claims.
