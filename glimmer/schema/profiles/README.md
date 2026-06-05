# Glimmer domain profiles

The core schema (`../frontmatter.yaml`) is **domain-neutral**. A **domain profile**
adds the fields specific to a kind of data (BIDS modality, fMRI design, genomics
assay, …) onto the core node types, so the core stays stable while a library of
domains grows around it.

A node resolves its profile **most-specific-first**:
`domain` field on the node → `default-domain` in the KB's `_glimmer-index.json` →
the core schema's `default-domain`.

## Curated library

| Profile | Standard | Status | Augments |
|---|---|---|---|
| [`neuroimaging`](neuroimaging.yaml) | BIDS | curated | dataset, experiment, method, derivative |

## Using a profile

- **See what's active for a KB:** `glimmer validate <rokb>` prints a `Profiles:` line.
- **Select one:** set `default-domain: <name>` in `_glimmer-index.json` (whole KB),
  or `domain: <name>` on an individual node.

## Adding a profile

This is encouraged — the library grows from researcher contributions.

1. **Draft locally** (no PR, no review): write `<rokb>/_glimmer-profiles/<domain>.yaml`
   with `status: local`. `glimmer validate` picks it up and enforces it.
2. **Propose upstream:** PR a `<domain>.yaml` into this directory with `status: curated`
   and `standard` / `standard-url` / `version` filled in.

Format and constraints: [`_profile.schema.yaml`](_profile.schema.yaml). Full guide:
[`../../../docs/extending-the-schema.md`](../../../docs/extending-the-schema.md) →
*Authoring a profile*. A profile may only **add fields to existing node types** — new
node types or edge types are core changes (the `schema-rfc:` process).
