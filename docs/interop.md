# Interoperability with Existing Standards

> Glimmer is a graph layer above the file-format standards already adopted in neuroimaging. It does not replace them; it makes them legible to AI agents.

## The standards Glimmer interoperates with

| Standard | What it specifies | Glimmer's relationship |
|---|---|---|
| **[BIDS](https://bids.neuroimaging.io)** | File layout for neuroimaging datasets | A Glimmer `dataset` sidecar is a BIDS `.json` sidecar plus a `_x-glimmer` block. Existing BIDS tools continue to work. |
| **[NIDM-Results](https://github.com/incf-nidash/nidm)** | Statistical workflow descriptions | A Glimmer `derivative` node can wrap a NIDM-Results JSON-LD object. The NIDM identifier becomes a field on the Glimmer node. |
| **[DataLad](https://www.datalad.org)** | Distributed version control over data | Glimmer graphs live inside DataLad-managed file trees. The graph survives `datalad export` because it IS the file tree. |
| **[RO-Crate](https://www.researchobject.org/ro-crate/)** | Archive-level packaging of research artifacts | Glimmer is the working-time structure; RO-Crate is the publish-time export. `glimmer export-rocrate` (v0.2) emits a Glimmer graph as an RO-Crate manifest. |
| **[JSON-LD](https://json-ld.org)** | Linked-data serialization | A Glimmer sidecar can be losslessly serialized to JSON-LD by adding an `@context` field; this is the canonical machine-readable export. |
| **[schema.org](https://schema.org)** | Cross-domain semantic vocabulary | Glimmer's entity types align with `schema.org/Dataset`, `schema.org/SoftwareApplication`, `schema.org/ScholarlyArticle`, etc. JSON-LD export uses these where possible. |
| **[ProvONE](https://purl.dataone.org/provone-v1-dev)** / **PROV-O** | Provenance semantics | Glimmer's edge types (`produced-by`, `derives-from`) map to PROV-O predicates (`prov:wasGeneratedBy`, `prov:wasDerivedFrom`). |
| **[FAIR principles](https://www.go-fair.org/fair-principles/)** | Findability, Accessibility, Interoperability, Reusability | Glimmer is FAIR-by-construction: every node has a stable identifier, the graph is machine-readable, edges encode provenance, and the schema is open. |

## BIDS spec version

> **Current state (verified 2026-05-30):** BIDS v1.11.1 (released 2026-02-19). Actual dataset sidecars are **JSON**. The spec source is written in YAML, but that's how the spec maintainers author it — it doesn't change what tools consume in real datasets.

## The format-agnostic position

The schema is the contract. The format is incidental. An AI agent reading or writing a Glimmer graph translates between formats as needed.

What this means in practice:

- **A Glimmer node's structure** (required fields, edge types, validator rules) is the load-bearing contract.
- **A Glimmer node's serialization** (JSON, YAML+Markdown, JSON-LD, TOML, even Org-mode if you like) is a deployment choice, not an architectural one.
- **The agent translates.** If a downstream consumer wants BIDS JSON, the agent emits BIDS JSON. If a human collaborator wants YAML+MD for legibility, the agent emits YAML+MD. The validator checks the structure-after-translation.

The reference implementation in this repo uses YAML-front-matter Markdown for standalone Glimmer entities (method, derivative, finding, standard, publication) because it composes well with personal-knowledge-base tooling researchers already use. It uses BIDS-native JSON when extending an existing BIDS sidecar (see below). These are conventions, not commitments.

## Cross-reading BIDS sidecars

A BIDS-conformant dataset already contains JSON sidecars. To make these legible as Glimmer nodes without breaking BIDS tooling:

```json
{
  "RepetitionTime": 2.4,
  "EchoTime": 0.003,
  "FlipAngle": 8,
  "_x-glimmer": {
    "id": "sub-01-T1w",
    "type": "dataset",
    "modality": "anat-T1w",
    "edges": [
      {"type": "produced-by", "target": "method-recon-all-fs6"},
      {"type": "conforms-to", "target": "bids-spec-1.11.1"}
    ]
  }
}
```

Tools that don't understand `_x-glimmer` ignore it (the BIDS validator continues to pass). Tools that do understand it index the BIDS sidecar as a Glimmer `dataset` node.

When the Glimmer agent emits a new node for a non-BIDS entity (a `method`, `derivative`, `finding`, `standard`, or `publication`), it writes a YAML-front-matter Markdown file. When the agent reads a Glimmer graph for analysis, it translates both formats into an in-memory graph and reasons over the unified structure. Round-tripping between the formats is the agent's responsibility.

## Validating across both layers

The Glimmer validator (`glimmer validate <path>`) checks the Glimmer graph for internal consistency. To also validate BIDS conformance, run them in sequence:

```bash
bids-validator <path>                # BIDS spec conformance (https://bids-validator.readthedocs.io/)
glimmer validate <path>              # Glimmer graph conformance
```

The two validators are independent by design. The unified-output flag `glimmer validate --include-bids` (v0.2) will invoke the BIDS validator as a subprocess and merge the results. The merged report distinguishes:

- **BIDS errors** — file layout, required fields, valid values per the BIDS spec.
- **Glimmer errors** — index consistency, edge integrity, schema conformance.
- **Cross-layer warnings** — e.g., a BIDS sidecar has an `_x-glimmer` block whose `type` doesn't match the BIDS file's expected modality.

This is the model: **BIDS catches "your files are wrong"; Glimmer catches "your project's structure is wrong"; cross-layer catches "your structure and your files disagree."**

## Importing an existing BIDS dataset

For a BIDS-conformant project that doesn't yet have a Glimmer overlay:

```bash
glimmer import-bids /path/to/bids/dataset --output /path/to/rokb
```

This is **not yet implemented in v0.1.** The plan for v0.2:

1. Walk the BIDS file tree.
2. Create a `dataset` node per scan and per subject.
3. Read the `dataset_description.json` and create `publication` nodes for any `ReferencesAndLinks` entries.
4. Read any existing MRIQC, fMRIPrep, or QSIPrep reports and create `derivative` nodes pointing to them; emit `finding` nodes for the QC summary numbers each report produces.
5. Emit the `_glimmer-index.json`.

PRs welcome.

## Exporting to RO-Crate for archive

Once a project ships, the Glimmer working-time graph can be exported as a publication-ready RO-Crate:

```bash
glimmer export-rocrate /path/to/rokb --output /path/to/rocrate
```

This is **not yet implemented in v0.1.** The plan for v0.2:

1. Emit a `ro-crate-metadata.json` at the export root.
2. Translate each Glimmer node to an RO-Crate entity with the matching `@type`.
3. Translate each Glimmer edge to an RO-Crate property (`prov:wasGeneratedBy`, `dc:isPartOf`, etc.).
4. Bundle referenced data files (or, for large files, leave them as external content-addressed references).

PRs welcome.

## JSON-LD export of a single node

A single Glimmer node sidecar maps to a JSON-LD object with the canonical context:

```yaml
# Glimmer source
id: sub-01-T1w
type: dataset
edges:
  - {type: produced-by, target: method-recon-all-fs6}
```

```json
// JSON-LD export
{
  "@context": "https://glimmer.io/context/v0.1.jsonld",
  "@id": "sub-01-T1w",
  "@type": "Dataset",
  "wasGeneratedBy": {"@id": "method-recon-all-fs6"}
}
```

The Glimmer context file (planned at `https://glimmer.io/context/v0.1.jsonld`) maps each Glimmer edge type to its PROV-O / schema.org equivalent.

## Standards mapping summary

```
Glimmer entity     ←→  schema.org              ←→  PROV-O
─────────────────────────────────────────────────────────────
dataset            ←→  Dataset                 ←→  prov:Entity
method             ←→  SoftwareApplication     ←→  prov:Activity
derivative         ←→  Dataset / Result        ←→  prov:Entity (wasGeneratedBy method)
finding            ←→  Claim / Assertion       ←→  prov:Entity (with reasoning-trace)
standard           ←→  DefinedTerm / CreativeWork  ←→  (none — out-of-scope for PROV)
publication        ←→  ScholarlyArticle        ←→  prov:Entity
```

Edge mappings:
```
produced-by            ←→  schema:creator    /  prov:wasGeneratedBy
derives-from           ←→  schema:isBasedOn  /  prov:wasDerivedFrom
conforms-to            ←→  schema:conformsTo
based-on               ←→  schema:isBasedOn  /  prov:wasDerivedFrom
issued-by              ←→  schema:author     /  prov:wasAttributedTo
cites-*                ←→  schema:citation   /  cito:cites
```

## Open question: graph-of-graphs

A research project may have multiple Glimmer-conformant sub-graphs (one per cohort, one per analysis stream). The current schema does not formally specify cross-graph references. The candidate v0.2 mechanism is: edges with targets of the form `<external-graph-id>#<node-id>` resolve to nodes in a sibling graph. See `docs/roadmap.md` for the meta-graph extension.
