# Epistemic Authoring Guide (v0.7.0)

## 1. `reference` vs. `publication`

| Use `type: reference` for… | Use `type: publication` for… |
|---|---|
| External cited papers, books, preprints, reports, dataset papers, or standard docs written by others (or prior external work). | This project's own written outputs: working drafts, essays, preprints, abstracts, submitted or published papers. |
| Never expected to emit local `cites-dataset` / `cites-method` edges. | Expected to connect to local evidence via `cites-*`, `cites-concept`, or `aggregates`. |
| Connects to local concepts/findings via epistemic stance edges (`supports`, `challenges`, `contradicts`, `overlaps-with`, `extends`, `addresses-concept`). | Sets `pub-status` (`draft|submitted|accepted|published|abstract|preprint`) and optional `role: project-output`. |

**Backwards compatibility for v0.6 graphs:** Existing graphs that already store external citations as `type: publication` do not need to break URLs or IDs. Add `role: external-reference` (or run `glimmer migrate-references <rokb> --mode role --apply`) to clear false `publication has no cites-* edges` warnings immediately. Use `--mode type --apply` when ready to convert them to `type: reference`.

### Minimal `reference` template

```yaml
---
id: ref-simon-1964
type: reference
ref-kind: paper
name: "Simon (1964): On the Concept of Organizational Goal"
created: '2026-11-26T00:00:00Z'
modified: '2026-11-26T00:00:00Z'
authors:
  - Herbert A. Simon
year: 1964
venue: Administrative Science Quarterly
doi: 10.2307/2391519
citekey: simon1964organizational
edges:
  - {type: addresses-concept, target: concept-organizational-goals}
  - {type: supports, target: concept-goal-constraints}
  - {type: in-program, target: program-main}
---

Concise summary of what the paper actually establishes and the exact scope limit for this project.
```

## 2. Epistemic Stance Edges

Use typed stance edges whenever the relation is stronger than topical association (`addresses-concept`):

- `supports` — supplies reinforcing empirical evidence, formal derivation, or direct precedent.
- `challenges` — surfaces a boundary condition, scope limit, confound, or tension without full refutation.
- `contradicts` — reports conflicting empirical or formal results.
- `overlaps-with` — shares mechanism or constructs with partial divergence.
- `extends` — generalizes, refines, or builds directly on an earlier concept, method, or paper.
- `superseded-by` — points from a retired concept, publication draft, or reference to its replacement (keep history rather than silently deleting).

Never collapse "cited" or "addresses-concept" into "supports." State scope limits explicitly in the node body.

## 3. `concept-kind` vs. Domain-Profile Subtypes (`claim-kind`)

- **Core `concept-kind`** (`research-question | hypothesis | theme | construct`) defines the structural role in Glimmer's core schema. Set it consistently on every `concept` node.
- **Local profile fields** (such as `claim-kind: design-assumption | theoretical-claim`, `evidence-status: proposed | observed`, `design-status`) live in `<rokb>/_glimmer-profiles/<domain>.yaml` and express project-specific epistemic status. They complement `concept-kind` rather than replacing it.

## 4. Fast-Moving Scratch Drafts vs. Canonical Milestones

Do not turn every exploratory paragraph or daily writing iteration into a new graph node:
- **Keep scratch drafts outside `<rokb>`** (e.g., `writing/`, `drafts/`) while iterating rapidly.
- **Register canonical milestones** into `<rokb>` (updating or creating a `publication` node + registering exported files in `workspace.json` `artifacts`) when a draft reaches a reviewable checkpoint, submission, or shared release.
- **Record method changes explicitly** with `glimmer amend <rokb> <method-id> "<reason>"` so evolving protocols leave an `AMEND-NNN` trail instead of silent drift.
- **Preserve original source bytes:** Never modify `sources/` files or `sources/**/SHA256SUMS`; reference them via `upstream-refs`.
