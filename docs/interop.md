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

## Cross-reading BIDS sidecars

A BIDS-conformant project contains JSON sidecars per scan (e.g., `sub-01/anat/sub-01_T1w.json`). To make these legible as Glimmer nodes, two paths exist:

1. **In-place augmentation.** Add a `_x-glimmer` block to the existing BIDS sidecar:
   ```json
   {
     "RepetitionTime": 2.4,
     "EchoTime": 0.003,
     "_x-glimmer": {
       "id": "sub-01-T1w",
       "type": "dataset",
       "edges": [
         {"type": "produced-by", "target": "method-recon-all-fs6"},
         {"type": "conforms-to", "target": "bids-spec-1.8.0"}
       ]
     }
   }
   ```
   Tools that don't understand the `_x-glimmer` block ignore it; tools that do understand it index it as a Glimmer node.

2. **Companion Markdown sidecar.** Place a `sub-01_T1w.glimmer.md` alongside the BIDS sidecar:
   ```yaml
   ---
   id: sub-01-T1w
   type: dataset
   bids-sidecar: sub-01_T1w.json
   edges: ...
   ---
   ```
   The companion sidecar references the BIDS JSON via its `bids-sidecar` field. Useful when the BIDS sidecar is owned by a tool you do not control.

## Validating across both layers

The Glimmer validator (`glimmer validate <path>`) checks the Glimmer graph for internal consistency. To also validate BIDS conformance, run them in sequence:

```bash
bids-validator <path>                # BIDS spec conformance
glimmer validate <path>              # Glimmer graph conformance
```

The two validators are independent by design. A future `glimmer validate --include-bids` flag (v0.2) will invoke the BIDS validator as a subprocess and merge the results.

## Importing an existing BIDS dataset

For a BIDS-conformant project that doesn't yet have a Glimmer overlay:

```bash
glimmer import-bids /path/to/bids/dataset --output /path/to/rokb
```

This is **not yet implemented in v0.1.** The plan for v0.2:

1. Walk the BIDS file tree.
2. Create a `dataset` node per scan and per subject.
3. Read the `dataset_description.json` and create `publication` nodes for any `ReferencesAndLinks` entries.
4. Read any existing MRIQC, fMRIPrep, or QSIPrep reports and create `qc-artifact` and `derivative` nodes pointing to them.
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
standard           ←→  DefinedTerm / CreativeWork  ←→  (none — out-of-scope for PROV)
qc-artifact        ←→  Comment / Review        ←→  prov:Entity
rater              ←→  Person                  ←→  prov:Agent
publication        ←→  ScholarlyArticle        ←→  prov:Entity
```

Edge mappings:
```
produced-by            ←→  schema:creator    /  prov:wasGeneratedBy
derives-from           ←→  schema:isBasedOn  /  prov:wasDerivedFrom
conforms-to            ←→  schema:conformsTo
attests-to-quality-of  ←→  schema:reviews
issued-by              ←→  schema:author     /  prov:wasAttributedTo
cites-*                ←→  schema:citation   /  cito:cites
```

## Open question: graph-of-graphs

A research project may have multiple Glimmer-conformant sub-graphs (one per cohort, one per analysis stream). The current schema does not formally specify cross-graph references. The candidate v0.2 mechanism is: edges with targets of the form `<external-graph-id>#<node-id>` resolve to nodes in a sibling graph. See `docs/roadmap.md` for the meta-graph extension.
