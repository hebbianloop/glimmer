# FAQ

### What's the difference between Glimmer and BIDS?

BIDS specifies a file layout for neuroimaging datasets. Glimmer specifies a graph of typed entities sitting on top of that file layout, with explicit edges between datasets, methods, derivatives, and findings.

A Glimmer-conformant project is also BIDS-conformant (Glimmer extends BIDS via a sidecar field; it does not replace BIDS).

### What's the difference between Glimmer and DataLad?

DataLad gives you distributed version control over the data and code in a project. Glimmer gives you the typed-entity graph over those versioned artifacts. They compose: a Glimmer node sidecar lives inside a DataLad-managed file tree.

### What's the difference between Glimmer and RO-Crate?

RO-Crate is an archive-level standard for packaging research artifacts with provenance metadata. It is excellent for publishing finished work. Glimmer is the working-time structure: while you're still acquiring data, running pipelines, emitting findings, and drafting papers, Glimmer is what the AI agent reasons over. When the project ships, the Glimmer graph can be exported as RO-Crate for archive.

### Does Glimmer require a specific AI model?

No. The reference agent uses a frontier large language model via API, but the Glimmer schema is model-agnostic. Any reasoning system that can read sidecar files, walk edges, and emit structured outputs can be a Glimmer agent.

### Do I have to use the reference agent?

No. The reference agent shipped with the canonical example is minimal. Most real projects will want a domain-specific agent (trace verification, finding synthesis, literature review, autoresearch loop) that uses the same Glimmer schema but extends the tool inventory. Build it in your fork.

### Can I use Glimmer outside neuroimaging?

Yes. Glimmer is domain-agnostic by design. The six v0.2 entity types (dataset, method, derivative, finding, standard, publication) describe the structure of any compute-intensive research project. The canonical example happens to be neuroimaging because that's where BIDS + DataLad + Nipype are most developed — but DataLad itself is domain-general, and the Glimmer pattern (typed-entity graph over a versioned-data substrate) applies to genomics pipelines, climate-modeling workflows, particle-physics analyses, and any other compute-intensive domain backed by a mature standards ecosystem.

If you adapt Glimmer to a non-neuroimaging domain, please open an issue describing the entity-type changes — those are candidates for a domain-neutral version of the core.

### How do I cite Glimmer in a paper?

See `docs/paper-citation.md`.

### How do I get write access to send a PR?

Just open the PR. We accept contributions; the core team reviews them.

### What if I'm using Glimmer for confidential or unpublished research?

Use a private fork. The Glimmer core is MIT-licensed; your fork inherits whatever license you put on it. Nothing about Glimmer requires you to publish your sidecars publicly.
