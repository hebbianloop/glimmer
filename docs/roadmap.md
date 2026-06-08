# Glimmer Roadmap

> v0.3.1 (current) extends the architecture beyond a single dataset: ten entity types (`dataset`, `method`, `experiment`, `derivative`, `finding`, `concept`, `standard`, `publication`, `persona`, `organization`), the universal `contributed-by` attribution edge plus the in-graph attribution layer (`authored-by`, `affiliated-with`, `funded-by`, `mentors`, `leads`, `part-of`), the `ds000114-nipype` worked example, and the retrieval adapter for the literature-scout role. This document tracks the work that takes Glimmer from "single-project RO-KB" to "the substrate for AI-native science."

## v0.2 — Interop and BIDS Bridge

Targeted improvements that lower adoption friction without changing the core schema.

- [ ] `glimmer import-bids` — walk a BIDS-conformant project and emit a Glimmer overlay.
- [ ] `glimmer export-rocrate` — emit an RO-Crate manifest from a Glimmer RO-KB.
- [ ] JSON-LD context file at `https://glimmer.io/context/v0.1.jsonld`.
- [ ] Cross-tool report adapters: import MRIQC, fMRIPrep, QSIPrep outputs as `derivative` + `finding` nodes.
- [ ] `glimmer validate --include-bids` invokes the BIDS validator and merges results.

The throughline is **meet existing tools where they are.** A lab that already has a BIDS project, MRIQC reports, and an RO-Crate export pipeline should get a Glimmer overlay without rewriting anything — adoption is a one-way import that adds the graph on top, not a migration that asks them to abandon their stack. Everything here is read-side (import) or projection-side (export); none of it changes the core schema.

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

> This is the **meta-graph** cross-cutting layer. The core *structural* edges (`produced-by`, `derives-from`, `applies-to`, `produces`, `conforms-to`, `cites-*`, and the method pipeline DAG `composes` / `upstream-of` / `downstream-of`) are part of the base schema and catalogued in `schema.md` — they are intentionally not repeated here.

Shipped in v0.3.0:

- `addresses-concept`: `finding → concept` and `publication → concept` (the claim is about this concept)
- `tests-hypothesis`: `experiment → concept` (the paradigm is designed to test this concept), with the inverse `tested-by-experiment`: `concept → experiment`
- `extends-concept`: `concept → concept` (theory inheritance / specialization)
- `subsumed-by`: `concept → concept` (one concept becomes a special case of another over time)
- `competes-with`: `concept → concept` (rival hypotheses)
- `superseded-by`: `concept → concept` (a refined replacement supersedes this one)
- `decomposes-into`: `concept → concept` (a question decomposed into sub-hypotheses)
- the **evidence-relation layer**: `supports` / `contradicts` (`concept → finding | publication | concept`) and `supports` / `challenged-by` (`finding → finding | publication`) — reinforcing vs. contradictory evidence
- `aggregates`: `publication → finding` (this paper pools these findings)
- `contributed-by`: any node → out-of-graph contributor id (lightweight attribution, see schema.md)

Shipped in v0.3.1 (the in-graph attribution + research-program layer):

- `authored-by`: `publication → persona` or `concept → persona`
- `affiliated-with`: `persona → organization`
- `funded-by`: `concept → organization`
- `mentors`: `persona → persona`
- `leads`: `persona → concept | organization | experiment`
- `part-of`: `organization → organization`
- `depends-on-method`: `experiment → method` (the paradigm depends on this analysis method)
- `co-acquired-with`: `experiment → experiment | dataset` (acquired in the same session)

Planned (await `meta-analysis`):

- `meta-analyzes`: `meta-analysis → publication` — **still worth keeping.** It is *not* a duplicate of the shipped `aggregates`: `aggregates` points a publication at the `finding` nodes it pools, whereas `meta-analyzes` points at the primary *publications* a meta-analysis reviews (citation with meta-analysis intent). Both are needed once `meta-analysis` lands.
- `requires-experiment`: `dataset → experiment` — **kept, but demoted to low priority.** It is the index-time inverse of `realized-by`; only justified if reverse traversal from a dataset back to its paradigm becomes a common query. No consumer needs it yet.

> **Dropped from the plan:** `produces-data-for` (`experiment → dataset`) — redundant with the shipped `realized-by` edge, which already encodes an experiment's data outputs. Removed rather than carried as dead direction.

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

> **Status: not yet shipped.** `experiment`, `persona`, and `organization` ship in the schema (v0.3.0–v0.3.1) but have **no worked instances** in `examples/` yet, and `examples/experiment-contribution/` is currently README-only (its `rokb/` is missing). Building these example RO-KBs is tracked for a follow-up PR.

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
- **Standards beyond BIDS:** GA4GH (genomics), MIAME / MINSEQE (microarray / sequencing), CIF (crystallography), Frictionless Data (tabular), DataCite (publication-level), domain-agnostic JSON-LD via schema.org. The mechanism for these already shipped in v0.3.1 as **domain profiles** (`glimmer/schema/profiles/`, see `schema.md → Domain profiles`); v0.4 adds the autodetection that *selects or scaffolds* the right profile for dropped-in data, and grows the curated library to the standards above.
- **Auto-overlay generation:** once the data type is classified, Glimmer emits the appropriate sidecars (BIDS JSON for neuroimaging, Frictionless `datapackage.json` for tabular, etc.) plus the cross-standard Glimmer index.
- **Conflict resolution:** when a dataset partly conforms to multiple standards (a BIDS dataset with embedded genomic side-data), Glimmer's index records which standard governs which subtree; per-subtree validation runs independently.

This is what mrinit was reaching for but didn't reach. At v0.4 it lands as a first-class capability.

## v0.5 — Agent SDK

The reference agent (`glimmer/tools/agent.py`) lands as a minimal QC agent, then v0.5 promotes its primitives into a reusable SDK:

- `glimmer.agent.Tools` — class with `load_index`, `read_node`, `walk_edge`, `rerun_method`, `emit_finding` methods, parameterized over arbitrary LLM clients.
- `glimmer.agent.Reasoning` — base class for project-specific agents (trace verification, finding synthesis, literature review, meta-analysis summarization). Authors of project agents subclass this and only fill in domain-specific reasoning.
- `glimmer.agent.Trajectory` — explicit trace object that records every node read and every edge walked, so outputs are auditable in a structured way.

The payoff: a project-specific agent becomes a small amount of domain reasoning over a shared, audited tool surface, and every run emits a `Trajectory` that the verifiability contract (see `docs/agent-protocol.md`) can check after the fact. The reference QC agent stops being the ceiling and becomes the smallest example of the SDK.

## v0.6 — Federation and shared schemas

When two research groups maintain Glimmer projects on the same dataset, they should be able to publish their schemas, agents, and verification baselines as a shared registry. v0.6 specifies:

- A schema-registry format for cross-institution publication of Glimmer extensions. **Domain profiles are the unit of publication here** — a curated profile (`status: curated`) lives in this repo; a profile published through the registry carries `status: community`. The `_profile.schema.yaml` metadata (`standard`, `version`, `status`) is the registry record.
- A reputation / provenance model for who proposed which schema extension.
- A federated-query mechanism: agent at site A can issue a query, the local graph + remote schema permit reasoning, the response is signed by the agent's identity.

This is also the natural junction with decentralized-science infrastructure (Opscientia, OpenNeuro, Holonym-style verifiable researcher identity).

## v0.7 — Storage, durability & the multi-tenant platform

The **service architecture rewrite** (tracked in #7): the work that takes Glimmer from a post-hoc documentation ledger to a node-driven model where storage durability is *part of the research object*, and where users provision their own hosted backing resources. It is the platform the hosted CLI (v0.8) sits on.

**Why this belongs in the model.** Glimmer v0.3 records *what* an output is plus its content-hash, but delegates *where* it lives and *how many copies* exist to the datalad/git-annex layer — invisible in the typed research object. An output you cannot locate, or that has a single copy, is not reproducible, so durability belongs inside the model rather than only in ops config. The motivating near-miss: a multi-day, compute-expensive output that sat only in `/tmp`, discoverable only because someone asked where it was.

Three layers, smallest-first:

- **Typed storage fields (additive — lands first).** `derivative` and `dataset` nodes gain `stored-at` (`[{remote, uuid}]`), `copies`, `numcopies-required`, `verified`, and `storage-class` (`irreplaceable | generated`). This slice is additive to the v0.3.1 schema and can ship ahead of the platform.
- **Archive-on-emit + enforcement.** `GlimmerGraph.derivative()` / `.dataset()` — the chokepoint every step already calls — annex-adds the output, `git annex copy --to` the durable remotes, then fills the storage fields from `git annex whereis`. **Creating a node *is* durably storing it;** `/tmp` / outside-annex paths are refused, making the near-miss structurally impossible. Enforcement lives in config + hooks — tiered `annex.numcopies` in `.gitattributes` (3 irreplaceable / 2 generated), a committed `pre-push` hook, `glimmer validate` in CI, and a teardown gate — not per-analysis scripts. A generic `glimmer report` / `glimmer status` prints every artifact's copy-count and locations (recorded-vs-live drift included) — storage is never hidden in output.
- **Commit-tracking bares + multi-tenant self-provisioning.** A durable copy ≝ a `--bare` git+annex repo that tracks full commit history; object-only stores (sftp/rsync boxes that can't run git) are adjuncts, not durable copies. The platform lets users provision their own tenants **and** their own bares at dataset init. `ads-glimmer` is the first consumer and migrates onto this model once it lands.

Design record: #6, #7, and `ads-glimmer/docs/data/INFORMATION-ARCHITECTURE.md` (status: design, implementation deferred to this version).

## v0.8 — Hosted service: CLI ↔ glimmer.science

Today the CLI is local-only — it builds, validates, and traverses a file-tree RO-KB on disk. Once the **v0.7 platform** is in place, the CLI becomes the client to a hosted research-object service:

- **`glimmer auth login`** — authenticate the CLI to glimmer.science and bind to a project the user created there.
- **Resource provisioning** — request and manage a project's backing resources from the CLI: **storage** (dataset hosting / DataLad remotes, provisioned per the v0.7 tenant model) and **compute** (run a `method` / pipeline remotely rather than locally).
- **Remote research-object operations** — modify / update / query the hosted RO-KB through the CLI: push new nodes and edges, fetch a subgraph, run a query against the project's graph.
- **Identity & provenance** — operations are signed by the authenticated researcher identity, tying into the v0.6 federation model and Holonym-style verifiable identity.

Dependency: **builds on the v0.7 platform rewrite** (#7). Captured here so the CLI surface is designed against the service rather than retrofitted later.

## Beyond v0.8 — Open questions

Each of these is a candidate edge or field family that doesn't yet have a consumer pushing on it. The leaning is recorded so the discussion starts from a proposal, not a blank page.

- **Temporal edges as first-class.** Wave 1 → Wave 2 → Wave 3 of a longitudinal study is currently encoded by date fields and informal naming. *Proposal:* add a `precedes` / `succeeds` edge family (with an optional `wave` / `timepoint` label) between existing `dataset` / `experiment` nodes rather than a new node type — sequence is a relation, not a thing — and populate the inverse at index time. *Leaning:* adopt narrowly, once a second longitudinal consumer needs it.
- **Hypothesis nodes vs. concept nodes.** A hypothesis is a falsifiable, dated claim; a concept is a broader theme. v0.3's `concept` is intentionally vague. *Proposal:* keep one `concept` type but add a `kind: question | hypothesis | theme` discriminator plus optional `falsifiable-by` / `stated-on` fields, instead of forking a new node type — a hard split fragments the `addresses-concept` / `decomposes-into` edges that already work. *Leaning:* discriminator now, revisit a split only if hypothesis-specific edges accumulate.
- **Relationship-typed citation.** Citation is *already* typed by **target** — `cites-dataset` / `cites-method` / `cites-derivative` / `cites-finding`, plus generic `cites` and `validates-against`. What's missing is typing by **relationship**: CiTO / PROV has ~50 predicates (`disagrees-with`, `extends`, `uses-method-in`, …). *Proposal:* don't adopt all of them — add a small, high-signal subset (`extends`, `uses-method-in`, `disagrees-with`, `confirms`) as typed `publication → publication` edges layered over the existing by-target `cites-*`. The planned `meta-analyzes` edge is the first member of this family. *Leaning:* adopt the subset alongside `meta-analysis`.
- **Retractions.** The evidence-relation layer already ships — `contradicts` and `competes-with` (concept), `challenged-by` (finding), `superseded-by` (concept) — so contradiction and supersession *are* modeled. What's **not** modeled is a formal, dated **retraction**: a withdrawal of a result by its own authors. *Proposal:* add a narrow `retracts` / `disputes` edge on `finding` / `publication`, extending the existing `superseded-by` pattern. A retraction is a first-class edge, **not a deletion** — the original node and the withdrawal both remain in the graph, which is exactly the auditability the substrate promises. *Leaning:* adopt the two missing edges; the rest of this is done.
- **What if the agent disagrees with itself.** An agent run at time T₁ may produce a different output than the same agent at T₂ (different model version, different graph state). *Resolution (no schema change):* record both as separate `finding` nodes, each carrying its `agent` / `model` / `run-at` provenance — the schema already supports this. The work is to *document the pattern* and have the v0.5 agent SDK emit the disambiguating provenance by default.
- **Privacy as a node-level property.** A `dataset` node referring to participant data needs an access policy. *Proposal:* the **v0.7 platform** adds a `data-use-agreement` reference (a node type or a constraint edge) and an `access-class` field on `dataset`; identified data stays out of the committed graph regardless, with the access policy governing `datalad get` against the provisioned remotes. *Leaning:* fold into v0.7, since it rides on the same storage/provisioning layer and v0.8 signed identity.

## How to contribute to the roadmap

Open an issue with `roadmap:` prefix, naming the version. Discussion happens in the issue; consensus changes update this document.

The roadmap is a moving target. Versions are aspirational, not contractual. Real adoption by downstream projects determines what's in scope.
