# Glimmer Schema (v0.3)

Research-object knowledge-base schema. Sidecars are YAML front-matter (mirrors shimmer-kb's `memory/*.md` pattern) when standalone, or BIDS-native JSON augmented with an `_x-glimmer` block when extending a BIDS sidecar in place. Every node is a file. Edges are properties on the source node.

v0.3.1 makes the core schema **domain-neutral**: fields fixed by a domain standard (BIDS modality, fMRI design, Nipype node kind, neuroimaging `output-kind`) move out of the core node types into [domain profiles](#domain-profiles), a curated + local library keyed by `domain`. It also adds the meta-graph social layer: `persona` (a person or role) and `organization` (institution/lab/funder/journal) node types, plus the in-graph attribution edges `authored-by`, `affiliated-with`, `funded-by`, `mentors`, `leads`, and `part-of`. v0.3 adds `experiment` (a task/acquisition paradigm as a first-class node), `concept` (a research question / hypothesis as a first-class node, the unit a research program operates at), and `contributed-by` (a universal attribution edge with out-of-graph contributor targets). v0.2 changes from v0.1: dropped `qc-artifact` and `rater` entity types (over-indexed on QC as the canonical example). Added `finding` between `derivative` and `publication`. Agent identity is now a string field on `finding` and `derivative`, not a separate node type.

## Common front-matter (all node types)

```yaml
---
id: <kebab-case-slug>            # MUST be unique within the dataset
type: <one of: dataset|method|experiment|derivative|finding|concept|standard|publication|persona|organization>
name: <human-readable name>
created: <ISO8601>
modified: <ISO8601>
provenance-hash: <sha256 of the body content; auto-computed>
edges:                           # outgoing edges; each is {type, target, optional metadata}
  - {type: <edge-type>, target: <node-id>, ...}
description: |
  Free-text agent-readable description.
domain: <profile-name>           # optional; selects this node's domain profile
---
```

## Domain profiles

The core schema (`frontmatter.yaml`) defines only **domain-neutral** node types. Any field whose vocabulary is fixed by a domain standard — BIDS modalities, fMRI task designs, Nipype node kinds, neuroimaging output kinds — lives in a **domain profile**, not in the core. A profile is a small YAML file that *augments* one or more core node types with extra `required` / `optional` fields. This keeps the core stable while a library of domains grows around it.

**Where profiles live (two tiers).**
- `glimmer/schema/profiles/<domain>.yaml` — the **curated library**, versioned in this repo. `neuroimaging.yaml` (BIDS) ships today; behavioral (Psych-DS), genomics (GA4GH), etc. are added here over time.
- `<rokb>/_glimmer-profiles/<domain>.yaml` — a **researcher's own** profile, local to one knowledge base. Drop a file here to model a new kind of data without touching the core schema or the shared library. A local profile shadows a curated one of the same name (the validator warns).

Each profile carries its own metadata (`standard`, `standard-url`, `version`, `status: curated|community|local`) so the library is self-describing and maps onto the cross-institution **schema registry** planned in `docs/roadmap.md` (v0.6). See `glimmer/schema/profiles/_profile.schema.yaml` for the format.

**How a node's profile is resolved (most specific wins):**
1. the node's own `domain` field, else
2. the KB-level `default-domain` in `_glimmer-index.json`, else
3. the core schema's `default-domain` (currently `neuroimaging`).

The validator merges the resolved profile's `augments.<node-type>.required` onto the core requirements for that node. A `domain` naming a profile that can't be found is a non-fatal hint (its domain-specific fields go unchecked) — never a hard error, so a KB can reference a standard Glimmer doesn't ship yet.

**Adding a profile** (e.g. `behavioral`):
```yaml
# glimmer/schema/profiles/behavioral.yaml   (curated)  — or
# mykb/_glimmer-profiles/behavioral.yaml    (local)
profile: behavioral
standard: Psych-DS
status: curated
augments:
  dataset:
    required: {participant-id: string}
    optional: {n-trials: int, instrument: string}
  experiment:
    optional: {response-device: string}
```
Then tag a node `domain: behavioral`, or set `default-domain: behavioral` for the whole KB. No validator change is needed — profile merging is generic.

## Entity types + canonical edges

### `dataset`
Research data of any kind. The core `dataset` is **domain-neutral** — it carries only identity, generic provenance (`acquisition-date`, `metrics`), and domain-neutral DataLad re-fetch coordinates. The attributes specific to a *kind* of data (participant, session, modality, …) come from the node's **domain profile** — see [Domain profiles](#domain-profiles). For neuroimaging (standard: BIDS) the profile adds the required `subject-id` and optional `session` / `modality` / `scanner` / `bids-version` shown below.

Canonical edges:
- `produced-by` → `method` node (the acquisition method)
- `derives-from` → upstream `dataset` node
- `conforms-to` → `standard` node (e.g. BIDS spec version)
- `cited-in` → `publication` node

Example sidecar fields (core fields + the `neuroimaging` profile; `domain` may be omitted when the KB's `default-domain` is neuroimaging):
```yaml
# core (domain-neutral)
datalad-superdataset: "https://github.com/OpenNeuroDatasets/ds000114"
datalad-relative-path: "sub-01/anat/sub-01_ses-test_T1w.nii.gz"
datalad-commit-sha: "abc123..."
datalad-annex-key: "MD5E-s12345--..."
# neuroimaging profile (BIDS)
subject-id: "01"
modality: anat-T1w
scanner: "Siemens 3T TimTrio"
bids-version: "1.11.1"
```

### `experiment`
A task or acquisition **paradigm** — the experimental design under which data is acquired — as a first-class node. Distinct from `standard` because a paradigm is an *active design* (conditions, timing, regressors), not a static spec. E.g. an event-related emotional-film design, a reward task, or resting-state.

Canonical edges:
- `realized-by` → `dataset` node (the data acquired under this paradigm)
- `analyzed-by` → `method` node
- `tests-hypothesis` → `concept` node (the paradigm is designed to test this hypothesis)
- `conforms-to` → `standard` node
- `cited-in` → `publication` node

Core fields are domain-neutral (`task-name`, `conditions`, `duration-sec`, `n-trials`); the fMRI design vocabulary (`design`, `regressors`, `timing-source`, `stimulus-set`) comes from the neuroimaging profile.

Example sidecar fields (core + neuroimaging profile):
```yaml
task-name: emoFilm                 # core
conditions: [REST, NEU, POS, NEG]  # core
design: naturalistic               # neuroimaging profile
regressors: ["salience-SRF ⊗ HRF"] # neuroimaging profile
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

Example sidecar fields (`tool` / `version` / `parameters` are core; `nipype-node-type` comes from the neuroimaging profile):
```yaml
tool: fsl.BET
version: "fsl-6.0.5"
parameters: {frac: 0.5, robust: true}
parameters-hash: "sha256:..."
workflow-definition-sha: "<git-sha of the .py file>"
nipype-node-type: Node             # neuroimaging profile
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
- `provenance-mode` — (core, required) `deterministic` (Nipype/FSL deterministic ops), `agent-inferred` (LLM-produced summary), or `stochastic` (e.g., randomized initialization)
- `output-kind` — the kind of output (`volume`, `surface`, `timeseries`, `statistical-map`, …); supplied (and required) by the neuroimaging profile, since the taxonomy is domain-specific

### `finding`
An interpreted assertion grounded in one or more derivatives. The unit between "the pipeline produced this output" (a derivative) and "we wrote a paper about it" (a publication). EVI-aligned: a finding has interpretation text + evidence pointers + verifiable provenance.

Canonical edges:
- `based-on` → `derivative` or `dataset` node (the evidence chain)
- `cited-in` → `publication`
- `challenged-by` → `finding` or `publication` (contradictory evidence)
- `supports` → `finding` or `publication` (reinforcing evidence)
- `addresses-concept` → `concept` node

Required fields:
- `interpretation` — human-readable assertion ("Subject sub-01 T1w brain volume = 1,234,567 mm³")
- `based-on` — list of derivative or dataset node IDs

When `produced-by-agent` is set (an LLM emitted this finding rather than a deterministic computation), the `reasoning-trace` field becomes required. See `docs/agent-protocol.md` for the full verifiability contract.

### `concept`
A research question, hypothesis, or theme as a first-class node — the unit a research **program** operates at (what a grant funds, what a thesis defends, what a meta-analysis examines). Findings and publications point *up* at a concept via `addresses-concept`; the agentic loop decomposes a question *down* into sub-hypotheses via `decomposes-into`. See [`docs/agentic-loop.md`](../../docs/agentic-loop.md).

Canonical edges:
- `decomposes-into` → `concept` (a question decomposed into sub-hypotheses)
- `extends-concept` → `concept` (specialization / theory inheritance)
- `subsumed-by` → `concept` (becomes a special case of a broader concept)
- `competes-with` → `concept` (rival hypothesis)
- `superseded-by` → `concept` (a refined replacement supersedes this one)
- `supports` / `contradicts` → `finding`, `publication`, or `concept`
- `authored-by` → `persona` (who framed / leads this question)
- `funded-by` → `organization` (the funder of this line of work)
- `tested-by-experiment` → `experiment` (a paradigm designed to test this concept)
- `cited-in` → `publication`

Required fields:
- `statement` — the question / hypothesis / theme as a sentence

Optional scientometric fields (scout- / autoresearch-emitted concepts): `outcome-data`, `outcome-access`, `sensitivity`.

Example sidecar fields:
```yaml
statement: "Naturalistic emotional-film fMRI in adolescence predicts violence outcomes in emerging adulthood."
concept-kind: hypothesis
status: under-investigation
falsifiable: true
```

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
- `addresses-concept` → `concept` (the publication's claim is about this concept)
- `authored-by` → `persona` (an author of this work, as an in-graph node)

### `persona`
A person (researcher, collaborator) or an organizational role, as a first-class node — the in-graph identity an `authored-by` or `contributed-by` edge can resolve to. Model a `persona` when the social graph matters (who mentors whom, who leads which question); use the lighter `contributed-by` universal edge with an out-of-graph ORCID/email target when you only need attribution, not a node.

Canonical edges:
- `affiliated-with` → `organization` (current or historical affiliation)
- `mentors` → `persona` (advising / supervision relationship)
- `leads` → `concept` / `organization` / `experiment` (drives / heads this)

Required fields:
- `persona-kind` — one of `researcher`, `collaborator`, `role`, `group`

Example sidecar fields:
```yaml
persona-kind: researcher
orcid: "0000-0002-1825-0097"
aliases: ["A. VanMeter", "Ashley S. VanMeter"]
```

### `organization`
An institution, lab, consortium, department, journal, or funding body. Personas affiliate with it, concepts are funded by it, and organizations nest via `part-of`.

Canonical edges:
- `part-of` → `organization` (a lab within a department within a university)

Required fields:
- `org-kind` — one of `institution`, `lab`, `consortium`, `department`, `journal`, `funder`, `other`

### `program`
A research **study, cohort, or initiative** as a first-class node — the *container* that organizes datasets, experiments, concepts, and publications around one research mission. A program may nest inside a parent program via `part-of` (a **subproject** relationship), so multi-study programs form a hierarchy. Distinct from `organization` (the institution that runs it) and `concept` (a question it investigates).

Any node declares membership in a program with the universal [`in-program`](#in-program) edge. Relationships to nodes that live in **another program's graph** use the universal [`cross-project`](#cross-project) edge (out-of-graph, namespaced target) — this is how a subproject inherits a canonical node from its parent, or how a harmonizing analysis connects to both graphs.

Canonical edges:
- `part-of` → `program` (subproject nesting within a parent program, **same graph**)
- `led-by` → `persona` (PI / study director)
- `funded-by` → `organization`
- `includes-dataset` → `dataset`, `includes-experiment` → `experiment`
- `addresses-concept` → `concept`, `cited-in` → `publication`

Required fields:
- `program-kind` — one of `study`, `cohort`, `subproject`, `initiative`, `consortium`

Worked example — the **CLAD** subproject is part of the **ADS** study (separate graphs), and a node it inherits from the parent points back to the ADS-canonical id:

```yaml
# in clad-glimmer:
---
id: program-clad
type: program
program-kind: subproject
name: "Community Life & Adolescent Development (CLAD)"
edges:
  - {type: cross-project, target: "ads-glimmer:program-ads", role: subproject-of-parent}
  - {type: led-by, target: persona-shady-el-damaty}
  - {type: funded-by, target: org-nij}
---
# an inherited node, canonical in the parent ADS graph:
---
id: org-nij
type: organization
org-kind: funder
name: "National Institute of Justice"
edges:
  - {type: in-program, target: program-clad}
  - {type: cross-project, target: "ads-glimmer:org-nij", role: inherited-from-parent}
---
```

## Cross-cutting edges (`_universal-edges`)

Some edges are allowed from **any** node type; the validator unions these in regardless of the source node's `edges-allowed`.

### `contributed-by`
Attribution **as an edge**: who (or what) contributed to this node, and in what role. The target is an **out-of-graph contributor identifier** (ORCID URI preferred, else email or a kebab id) — like `publication.authors`, contributors are referenced by stable id, not required to be graph nodes. Role + identity ride as edge metadata. (Once you model contributors as `persona` nodes, the target *may* be a persona node-id; for strict in-graph attribution that the validator checks against the index, prefer `authored-by` → `persona`.)

```yaml
edges:
  - {type: contributed-by, target: "0000-0002-1825-0097", role: pi,       name: "Ashley VanMeter"}
  - {type: contributed-by, target: "se394@georgetown.edu", role: analyzed, name: "Shady El Damaty"}
```

Suggested roles: `pi`, `scanned`, `qc`, `coded`, `analyzed`, `drafted`, `funded`. The **who-did-what attribution layer** is derived by aggregating `contributed-by` edges across the whole graph (group by target). Because the target is out-of-graph, the validator does not require it to appear in the index.

### `in-program`
Membership: this node belongs to a `program`. The target is a **program node in this graph** (in-graph, validated against the index). Aggregating `in-program` edges yields the membership roster of a study/cohort/subproject.

```yaml
edges:
  - {type: in-program, target: program-clad}
```

### `cross-project`
A relationship to a node in **another project's Glimmer graph**, addressed by a **namespaced id** `<graph>:<node-id>` (e.g. `ads-glimmer:concept-striatum-parcellation`). The target is **out-of-graph** — like `contributed-by`, the validator does **not** require it to appear in the local index — so it carries inter-project claims and parent-canonical references across graph boundaries without a federated index. Use it to (a) declare a subproject's link to its parent program, (b) point an inherited copy at the parent-canonical node, or (c) connect a harmonizing analysis/claim/experiment to the sibling project.

```yaml
edges:
  - {type: cross-project, target: "ads-glimmer:concept-striatum-parcellation", role: harmonizes-with}
  - {type: cross-project, target: "ads-glimmer:org-nij", role: inherited-from-parent}
```

Convention: resolve duplicated nodes to the **parent** project (it owns the canonical node); a subproject keeps an inherited copy that points back with `role: inherited-from-parent`. Cross-graph resolution is by namespace; a future federated index (roadmap v0.6) may validate these targets.

## Index file (`_glimmer-index.json`)

At the dataset root. Lists every node ID + its file path. Mandatory load for the agent.

```json
{
  "schema": "glimmer/v0.3.0",
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

The autoresearch meta-graph layers people, organizations, and hypotheses over
the imaging data layer. Its node types — `concept`, `persona`, `organization` —
are documented in full under [Entity types](#entity-types--canonical-edges)
above; this section records only the v0.3 deltas to the data-layer types:

- `experiment.task-name` is now **optional** — the research-program layer uses
  `experiment` for hypothesis-level study designs with no single task file, and
  adds `depends-on-method` → `method` and `co-acquired-with` → `experiment`/`dataset` edges.
- `publication` may carry `addresses-concept` → `concept` and `authored-by` →
  `persona` edges (scout-emitted literature).

## Project / subproject layer (v0.4)

v0.4 adds the `program` node type (a study / cohort / subproject container) and two
universal edges, making multi-study programs and cross-graph relationships first-class:

- `program` nests via `part-of` → `program` (a **subproject** of a parent study, same graph).
- `in-program` (universal, in-graph) — any node declares membership in a `program`.
- `cross-project` (universal, **out-of-graph**) — a relationship to a node in another
  project's graph by namespaced id (`<graph>:<node-id>`); carries inter-project claims and
  parent-canonical (inherited-copy) references. Added to the validator's out-of-graph
  allowlist alongside `contributed-by`. Backward-compatible; existing sidecars stay valid.
