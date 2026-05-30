# Glimmer Design Rationale

## Why distributed-over-files rather than a central database

The graph could have been a SQLite database, a Neo4j store, or a Datomic instance. We chose distributed-over-files (per-entity YAML-front-matter Markdown / JSON sidecars + a top-level index file) for four reasons:

1. **Survives existing distribution tools.** A Glimmer graph survives `git clone`, `datalad export`, content-addressed publishing, and `rsync` without bespoke serialization or migration scripts. The graph IS the file tree.
2. **No new dependencies.** No graph database to install, configure, version, back up, or migrate when the project moves machines.
3. **Editable in any text editor.** A collaborator without Glimmer tooling can still read and modify a Glimmer node sidecar. The graph degrades gracefully.
4. **Composable with versioning.** Each node's `provenance-hash` field is a SHA-256 of the body content. A Git commit is a snapshot of the entire graph's state.

The cost is query performance: traversing a 10,000-node Glimmer graph requires loading 10,000 sidecars. For working datasets this is fine (sub-second on SSD); for population-scale, build an in-memory cache.

## Why typed entities rather than untyped graph nodes

Typing forces explicit decisions about what each artifact IS. A `dataset` and a `derivative` have different lifecycles: the former is acquired, the latter is computed. A `method` and a `standard` look similar (both reference external definitions) but obey different reasoning rules (a method node has parameters that can vary per-invocation; a standard node is immutable per-version). Typing makes these distinctions actionable for an agent.

We resisted the temptation to add more types. Six entity types (v0.2) is a deliberate ceiling. If a candidate new artifact looks like one of the existing six, it should subclass via convention in the body rather than become a new top-level type.

## Why "edges are properties on source nodes" rather than separate edge nodes

A `derivative` node has a `produced-by` edge in its sidecar, pointing to a `method` node ID. The reverse direction (which derivatives a given method produced) is computed at index load.

We chose this asymmetric storage because:

- It mirrors how BIDS sidecars already work (metadata stored alongside the artifact it describes).
- It avoids edge-node proliferation: separately-stored edges would mean many small files for no semantic gain.
- Indexing bidirectionally at load time is cheap and keeps the storage layer simple.

The cost: an agent cannot answer "which findings cite this derivative" without loading every finding sidecar. In practice, the index file precomputes this lookup at build time.

## Why the agent's tools are minimal

The Glimmer agent has only five primitive operations: `load_index`, `read_node`, `walk_edge`, `rerun_method`, `emit_finding`. We deliberately did not provide:

- Vector search over node bodies (too easy for the agent to skip principled traversal).
- Auto-summarization of large nodes (truncation hides structure; better to let the agent paginate explicitly).
- "Find similar nodes" by content (induces collapse to averages; the architectural claim depends on graph traversal, not nearest-neighbor lookup).

These can be added by downstream forks for project-specific work. The core stays minimal so the architectural claim — that agent QC performance is driven by graph content rather than tool sophistication — remains testable.

## Why we did not adopt RDF or JSON-LD

We considered both. They are mature, semantically rigorous, and have query tooling (SPARQL). We did not adopt them because:

1. Researchers do not write RDF by hand. Markdown front-matter, by contrast, is the standard format for personal note-taking tools that researchers already use.
2. The agent reasons more reliably over key-value structures than over predicate-object triples in our testing. (We do not claim this is permanent; LLM tool-use over SPARQL is an active area.)

A Glimmer sidecar can be losslessly serialized to JSON-LD (the front-matter is a flat key-value tree). A future version of the schema may include an optional `@context` field per node to enable JSON-LD interop.

## What we got wrong and might revisit

- **The line between `method` and `derivative`.** A pipeline can be both: applied as a method, instantiated as a derivative when its outputs become inputs to a downstream method. We treat the same Python module as a `method` node when it's actively running and as a `derivative` node when it's referenced as a static artifact. Cleaner would be a `tool-invocation` node type that bridges them.
- **No first-class temporal edges.** A scan acquired at Wave 2 vs Wave 3 currently relies on a date field in the sidecar; the longitudinal structure is implicit. Future schema versions should make temporal sequence explicit via edges.
- **Provenance hashes are body-only.** They do not include the sidecar metadata in the hash, so editing the description without editing the body doesn't change the hash. This is convenient for human edits but admits provenance drift. May change.
