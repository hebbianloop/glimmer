# Glimmer Roadmap

> v0.3.1 (current) extends the architecture beyond a single dataset: ten entity types (`dataset`, `method`, `experiment`, `derivative`, `finding`, `concept`, `standard`, `publication`, `persona`, `organization`), the universal `contributed-by` attribution edge plus the in-graph attribution layer (`authored-by`, `affiliated-with`, `funded-by`, `mentors`, `leads`, `part-of`), the `ds000114-nipype` worked example, and the retrieval adapter for the literature-scout role. This document tracks the work that takes Glimmer from "single-project RO-KB" to "the substrate for AI-native science."

## v0.2 — Interop and BIDS Bridge

Targeted improvements that lower adoption friction without changing the core schema.

- [ ] `glimmer import-bids` — walk a BIDS-conformant project and emit a Glimmer overlay.
- [ ] `glimmer export-rocrate` — emit an RO-Crate manifest from a Glimmer RO-KB.
- [ ] JSON-LD context file at `https://glimmer.io/context/v0.1.jsonld`.
- [ ] Cross-tool report adapters: import MRIQC, fMRIPrep, QSIPrep outputs as `derivative` + `finding` nodes.
- [ ] `glimmer validate --include-bids` invokes the BIDS validator and merges results.

## v0.3 — The Meta-Graph + Experiments + Autoresearch

The architectural extension that scales Glimmer beyond a single dataset to span research projects, research programs, literature corpora, and active autoresearch loops. Introduces new node types and a set of cross-cutting edges.

### New entity types

Status: **`experiment`** and **`concept`** shipped in v0.3.0; **`persona`** and **`organization`** shipped in v0.3.1; **`meta-analysis`** remains planned.

| Type | Status | Role |
|---|---|---|
| **`concept`** | ✅ shipped (0.3.0) | A research question, hypothesis, or theme as a first-class node — the unit a research program operates at (what a grant funds, what a thesis defends, what a meta-analysis examines). Findings and publications point at it via `addresses-concept`; the agentic loop decomposes it via `decomposes-into`. |
| **`experiment`** | ✅ shipped (0.3.0) | A task / acquisition paradigm — the active experimental design (conditions, timing, regressors), distinct from a static `standard`. Carries `realized-by` → dataset, `analyzed-by` → method, `tests-hypothesis` → concept. (Container-digest pinning for Experiment Factory artifacts comes with program tooling.) |
| **`persona`** | ✅ shipped (0.3.1) | A person (researcher, collaborator) or an organizational role. Carries `affiliated-with` → organization, `mentors` → persona, `leads` → concept; is the in-graph target of `authored-by` / `contributed-by`. The lighter `contributed-by` universal edge (out-of-graph ORCID/email) remains for attribution without a node. |
| **`organization`** | ✅ shipped (0.3.1) | An institution, lab, consortium, department, journal, or funding body. Personas affiliate with it (`affiliated-with`), concepts are funded by it (`funded-by`), and orgs nest via `part-of`. |
| **`meta-analysis`** | planned | A specialized `publication` subtype that aggregates findings across multiple primary `publication` nodes. Has `meta-analyzes` edges to each primary work, and `addresses-concept` edges to the concepts it tests. |

### Cross-cutting edges

Shipped in v0.3.0:

- `addresses-concept`: `finding → concept` and `publication → concept` (the claim is about this concept)
- `tests-hypothesis`: `experiment → concept` (the paradigm is designed to test this concept)
- `extends-concept`: `concept → concept` (theory inheritance / specialization)
- `subsumed-by`: `concept → concept` (one concept becomes a special case of another over time)
- `competes-with`: `concept → concept` (rival hypotheses)
- `superseded-by`: `concept → concept` (a refined replacement supersedes this one)
- `decomposes-into`: `concept → concept` (a question decomposed into sub-hypotheses)
- `contributed-by`: any node → out-of-graph contributor id (lightweight attribution, see schema.md)

Shipped in v0.3.1 (the in-graph attribution layer):

- `authored-by`: `publication → persona` or `concept → persona`
- `affiliated-with`: `persona → organization`
- `funded-by`: `concept → organization`
- `mentors`: `persona → persona`
- `leads`: `persona → concept`
- `part-of`: `organization → organization`

Planned (await `meta-analysis`):

- `meta-analyzes`: `meta-analysis → publication` (citation with meta-analysis intent)
- `produces-data-for`: `experiment → dataset` (the experiment's outputs)
- `requires-experiment`: `dataset → experiment` (inverse, populated at index time)

### Why `experiment` is its own type, not a sub-`method`

A `method` is an analysis applied to existing data; an `experiment` is the protocol that produces the data in the first place. The distinction matters because:

- Experiments are reproducible artifacts in their own right (a container is shippable; an analysis tool is a dependency of an experiment).
- Experiments have human-subjects considerations (IRB approval, consent forms) that methods don't.
- Experiments produce both behavioral data (TSV files, response logs) and trigger imaging data (DICOM streams), so they bridge between modalities.

The canonical example: Experiment Factory ships [hundreds of validated behavioral tasks](https://expfactory.org/experiments/library) as Docker containers. A Glimmer project that uses one of these references it as an `experiment` node whose container-digest pins the exact version run.

### Why this matters

A single dataset is a building block. A research project is a graph of building blocks plus the people and concepts that hold them together. A meta-analysis is a graph operation that walks across publications, datasets, and concepts. A research program is the time-evolution of all of the above.

At v0.3, the Glimmer agent can answer questions like:

- *"Which datasets does this concept depend on, and what's the QC state of each?"*
- *"Who has worked on this concept across multiple institutions?"*
- *"What concepts have been subsumed by `[[brain-age]]` since 2020?"*
- *"Which publications cite both `[[dataset-ads-wave1]]` and `[[concept-cortical-thickness-error]]`?"*

These are the questions a senior PI answers from working memory today. The meta-graph makes them addressable.

### Worked example for v0.3

A "research-program" example will accompany v0.3:

```
examples/research-program-ads/
├── concepts/
│   ├── concept-cortical-thickness-error.md
│   ├── concept-striatum-parcellation.md
│   └── concept-naturalistic-emotional-fmri.md
├── personas/
│   ├── persona-shady.md
│   ├── persona-ashley-vanmeter.md
│   └── ... (collaborators)
├── organizations/
│   ├── org-cfmi-georgetown.md
│   └── org-nij.md
├── publications/
│   ├── pub-damaty-2020-ohbm.md
│   └── ... (the 18 ADS cohort papers)
└── (sub-graphs for each Wave 1-3 cohort plus CLAD)
```

A meta-analysis traverses the graph: start at a concept, walk `authored-by` to personas, walk to other publications by those personas, walk back to other concepts via `extends-concept` or `subsumed-by`, and accumulate the graph of related work.

## v0.4 — Autodetection + Multi-Standard Support

The high-level "drop any data, Glimmer figures it out" capability you've been reaching for. v0.4 adds:

- **`glimmer discover <path>`** — walk a directory, classify the data, propose the right standard overlay.
- **Standards beyond BIDS:** GA4GH (genomics), MIAME / MINSEQE (microarray / sequencing), CIF (crystallography), Frictionless Data (tabular), DataCite (publication-level), domain-agnostic JSON-LD via schema.org.
- **Auto-overlay generation:** once the data type is classified, Glimmer emits the appropriate sidecars (BIDS JSON for neuroimaging, Frictionless `datapackage.json` for tabular, etc.) plus the cross-standard Glimmer index.
- **Conflict resolution:** when a dataset partly conforms to multiple standards (a BIDS dataset with embedded genomic side-data), Glimmer's index records which standard governs which subtree; per-subtree validation runs independently.

This is what mrinit was reaching for but didn't reach. At v0.4 it lands as a first-class capability.

## v0.5 — Agent SDK

At this point the reference agent (`glimmer/tools/agent.py`) has been the minimal QC agent. v0.4 promotes the agent's primitives into a reusable SDK:

- `glimmer.agent.Tools` — class with `load_index`, `read_node`, `walk_edge`, `rerun_method`, `emit_finding` methods, parameterized over arbitrary LLM clients.
- `glimmer.agent.Reasoning` — base class for project-specific agents (trace verification, finding synthesis, literature review, meta-analysis summarization). Authors of project agents subclass this and only fill in domain-specific reasoning.
- `glimmer.agent.Trajectory` — explicit trace object that records every node read and every edge walked, so outputs are auditable in a structured way.

## v0.6 — Federation and shared schemas

When two research groups maintain Glimmer projects on the same dataset, they should be able to publish their schemas, agents, and verification baselines as a shared registry. v0.6 specifies:

- A schema-registry format for cross-institution publication of Glimmer extensions.
- A reputation / provenance model for who proposed which schema extension.
- A federated-query mechanism: agent at site A can issue a query, the local graph + remote schema permit reasoning, the response is signed by the agent's identity.

This is also the natural junction with decentralized-science infrastructure (Opscientia, OpenNeuro, Holonym-style verifiable researcher identity).

## Beyond v0.5 — Open questions

- **Temporal edges as first-class.** Wave 1 → Wave 2 → Wave 3 of a longitudinal study is currently encoded by date fields and informal naming. Should temporal sequence become an edge type?
- **Hypothesis nodes vs. concept nodes.** A hypothesis is a falsifiable, dated claim; a concept is a broader theme. v0.3's `concept` is intentionally vague. Should hypotheses split off as their own type?
- **Citation as a typed edge, not generic `cites`.** PROV-CITO has ~50 citation predicates (`disagrees-with`, `extends`, `uses-method-in`, etc.). Worth adopting?
- **Anti-claims and retractions.** A research-graph needs to encode that a result was retracted, contradicted, or superseded. Current schema does not model this. Probably needs a `supersedes` / `retracts` / `disputes` edge family.
- **What if the agent disagrees with itself.** An agent run at time T₁ may produce a different output than the same agent at T₂ (different model version, different graph state). The graph should record both outputs as separate `finding` nodes; the schema already supports this. We should document the pattern.
- **Privacy as a node-level property.** A `dataset` node referring to participant data needs an access policy. v0.6+ should add `data-use-agreement` as a node type or as a constraint edge.

## How to contribute to the roadmap

Open an issue with `roadmap:` prefix, naming the version. Discussion happens in the issue; consensus changes update this document.

The roadmap is a moving target. Versions are aspirational, not contractual. Real adoption by downstream projects determines what's in scope.
