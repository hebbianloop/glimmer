# Extending the Glimmer Schema

> The line between "core" and "project" is the `glimmer/` directory. This document is for changes that go INSIDE it — **but most extension needs are domain profiles, not core changes.** Read the decision tree first.

## First: do you need a core change at all?

Most "I need to attach new information to nodes" needs are met by a **domain profile** — a small YAML file that adds fields to existing node types without touching the core schema. Decide before opening an RFC:

```
Need to attach new structured info to nodes?
├─ New FIELDS on an existing node type (dataset / method / experiment / …)?
│   ├─ Specific to one project / KB?     → LOCAL profile   <rokb>/_glimmer-profiles/<domain>.yaml   (no RFC, no review)
│   └─ Reusable across projects?         → CURATED profile glimmer/schema/profiles/<domain>.yaml   (PR + review, no version bump)
├─ A new NODE TYPE or EDGE TYPE?         → CORE change → the RFC process below
└─ Just free-form notes?                 → put it in the node body (no schema, no profile)
```

A profile may only **add fields to existing node types**. It cannot introduce a new node type or edge type — those change the contract every downstream fork relies on, so they go through the full RFC below. Profile mechanics, metadata, and resolution order are in `glimmer/schema/schema.md → Domain profiles`; the file format is `glimmer/schema/profiles/_profile.schema.yaml`.

### Authoring a profile (the encouraged lifecycle)

1. **Draft it where it's safe.** Write `<rokb>/_glimmer-profiles/<domain>.yaml` in your own knowledge base / fork — the project zone you're free to modify. Set `status: local`.
2. **Use and validate it.** `glimmer validate <rokb>` loads local profiles automatically and enforces their `required` fields; its `Profiles:` line confirms yours is active.
3. **Propose it upstream.** Once it's stable and others would benefit, open a PR moving it to `glimmer/schema/profiles/<domain>.yaml` with `status: curated` and filled-in `standard` / `standard-url` / `version`. **We welcome these** — the curated library grows from researcher contributions, and (per the v0.6 registry in `roadmap.md`) profiles are the unit of cross-institution publication.
4. **Review bar for a curated profile** is intentionally lighter than the node-type RFC below: it must validate against `_profile.schema.yaml`, name a real domain standard (or a clearly-scoped convention), and not duplicate an existing profile's domain.

## When to propose a (core) schema change

Propose a new node type, edge type, or sidecar field if:

- You can name **at least two distinct projects** that would benefit.
- The need cannot be met by adding fields inside an existing node's body (free-text descriptions are flexible).
- You have **a concrete worked example** of how an agent would reason over the new structure.

Don't propose if:

- Your project just needs a custom field on one specific node type. Use the `body` text for free-form annotations; the schema doesn't constrain what goes in the body.
- You want a different file format (JSON vs YAML vs TOML). The schema is format-agnostic at the layer that matters.
- The structure you want is identical to an existing node type with a different name. Cosmetic renames will not be accepted.

## Process

1. **Open a discussion issue** with the prefix `schema-rfc:` describing the proposed change.
2. The issue should answer:
   - What problem does this solve?
   - What does the new node type / edge / field look like?
   - How does an agent reason over it?
   - What at least two example projects benefit?
   - What is the migration path for existing Glimmer instances?
3. If discussion converges, open a PR against `glimmer/schema/schema.md` that:
   - Adds the new structure to the schema spec.
   - Adds a worked example under `examples/`.
   - Bumps the version in `glimmer/schema/glimmer-version` (minor if backward-compatible; major if not).
4. The PR is merged when at least one downstream project has implemented and uses the change.

## What backward compatibility means

Backward compatibility, in Glimmer terms, means: **a sidecar written under schema vN remains valid under schema v(N+0.x).**

Concretely:
- Adding a new node type → minor version bump (existing sidecars still valid).
- Adding a new optional field on an existing node type → minor version bump.
- Renaming a field, or changing its required-ness → major version bump (existing sidecars become invalid).
- Adding a new edge type → minor version bump (existing graphs don't have it, but that's fine).

When you do a major version bump, ship a migration script under `glimmer/tools/migrations/`.

## What's in scope for `glimmer/`

- The schema specification itself.
- Reference utilities for building, validating, and traversing Glimmer graphs.
- The reference QC agent (kept minimal — see `design-rationale.md` on why).
- Migration tools between schema versions.
- Documentation that applies to any Glimmer project.

## What's NOT in scope for `glimmer/`

- Project-specific data, sidecars, or extensions.
- Domain-specific agents (e.g., fMRI QC agent, DWI QC agent — those live in your fork).
- Project-specific bibliography or papers.
- Custom analysis pipelines that consume Glimmer graphs.

If you find yourself wanting to add something domain-specific to `glimmer/`, the answer is almost always: put it in your fork — **with one welcome exception: a domain profile.** A curated profile under `glimmer/schema/profiles/` is exactly how domain-specific *field vocabulary* is meant to enter the shared library. Domain-specific *agents, data, and pipelines* still belong in your fork; domain *fields* belong in a profile you're encouraged to PR upstream.
