# Proactive Provenance: Making the Research-Object Graph Executable for AI-Native Reproducibility

**Shady El Damaty**
*Working draft — v0.6.0 (2026). Successor to "Reproducibility as Knowledge Graph Navigation" (CAISc 2026).*

> This is a working manuscript, not a journal submission: no anonymization, length
> targets, or venue formatting. It states the architecture and the v0.6 contribution
> plainly so the design can be reviewed against the implementation in this repository.

---

## Abstract

Reproducible-pipeline tooling (BIDS, DataLad, Nipype, containers) made the *bytes* of a
computational analysis recoverable, and provenance standards (W3C PROV, RO-Crate, CWL)
made its *structure* describable. Yet "this result reproduces" remains a claim a reader
must take on trust: the description of a run and the *act* of re-running it are separate
artifacts, and nothing in the typed record forces them to agree. The gap widens under
AI-native workflows, where an autonomous agent analyzing a dataset re-derives the same
numbers inconsistently, re-makes settled data-processing errors, and loses prior findings
across sessions — each a reproducibility failure in miniature, because the agent has no
executable contract to anchor to.

We introduce **proactive provenance**: a typed research-object graph whose runs are
first-class, **executable, standard-gated, and self-verifying** nodes. We add to Glimmer —
a per-entity-sidecar research-object knowledge base — a single core node type, the
**`run-record`** (one concrete, replayable invocation, in the sense of a PROV `Activity`),
and a **node runner** (`glimmer run` / `glimmer rerun`) that, for each run-record: gates
its inputs (they must be both content-pinned *and* valid against their declared standards,
with validation delegated to standard-specific validators), replays the recorded command
in a pinned container, and verifies the outputs at one of three fidelity tiers —
*byte-identical* (with header normalization so two correct re-runs are not falsely
flagged), *numeric-within-tolerance* (re-deriving a reported number from source), and
*structural* (for agent/LLM outputs, the analogue of byte-equality). The run-record is the
executable unit of the agentic research loop: a hypothesis decomposes into planned runs,
running them emits derivatives and findings with recorded verdicts, and those verdicts —
not memory — are what the next planning step reads. We describe the design, a reference
implementation, and a worked example that exercises all three tiers, the standards gate,
and runtime-certified method equivalence on a laptop with no specialized dependencies.

---

## 1. Introduction

The 2010s solved a narrow version of reproducibility: with versioned data (DataLad /
git-annex), versioned code, and pinned environments (containers), the *bytes* an analysis
consumed and produced can be recovered later. The 2020s added a *description* layer —
W3C PROV activities, RO-Crate manifests, CWL tool/workflow descriptions — so the
*structure* of a computation is machine-readable. Glimmer's prior contribution sat above
both: a typed-entity graph (datasets, methods, derivatives, findings, standards,
publications, concepts) distributed across per-entity sidecars, so an agent could
*navigate* provenance and render auditable decisions.

But all of this is **descriptive**. A `derivative` node records an `output-hash`; a
`method` records a tool version and a workflow SHA; PROV records that activity *A* used
entity *E* and generated entity *O*. None of it re-runs *A* and checks that *O* still
results. The description of the run and the run itself are different objects, maintained
by hand, and free to drift. In practice the gap is filled by a human re-running things ad
hoc, or — increasingly — not at all.

AI-native workflows make the gap acute. An autonomous or semi-autonomous agent operating
over a dataset, with no executable contract to anchor to, exhibits a characteristic
failure pattern: it re-derives the same quantity by different routes and gets different
answers, repeats data-processing mistakes that were already diagnosed, and forgets
findings established earlier in the same project. Each is a reproducibility failure, and
each is a direct consequence of the substrate being a *ledger of claims* rather than a
*set of runnable, self-checking contracts*.

**Thesis.** Reproducibility should be an *executable property of the graph*, not a
property of a separate pipeline a reader is invited to trust. We call this **proactive
provenance**: the research-object graph not only records what an output is, but can
re-run the act that produced it and verify the result — at a fidelity appropriate to the
computation's nature. We realize it with one new node type and one tool, and argue this is
the missing primitive that makes the agentic research loop self-sustaining.

**Contributions.**
1. The **`run-record`** node type: a first-class, lifecycle-bearing PROV `Activity` that
   binds a method, pinned and standard-validated inputs, expected outputs, the exact
   command, and a pinned environment — the executable unit of the agentic loop (§4, §5).
2. A **node runner** with a pre-run **standards gate** and **three verification tiers**,
   including a faithful byte-identical tier that normalizes non-semantic header bytes (§4).
3. **Standards as a runtime gate**: the run-record *references* the standards its inputs
   must satisfy; the runner *enforces*; validators are *delegated* — so conformance is an
   enforced, recorded fact without coupling the record to validator internals (§4.3).
4. **Runtime-certified method equivalence**: two implementations are `equivalent-to` only
   if the runner confirms they produce matching outputs on shared inputs — turning a
   convention into a check, and giving a method a semantic identity that outlives one
   project (§4.5).
5. A reference implementation and a dependency-light worked example demonstrating all of
   the above (§6).

---

## 2. Background and related work

**Reproducible pipelines.** BIDS standardizes neuroimaging data layout; DataLad/git-annex
version data and pin content by hash; Nipype and container images (Docker/Singularity,
BIDS-Apps) pin the toolchain. These guarantee *re-fetch* and *re-execution capability* but
not *verification*: nothing asserts that re-execution reproduces the recorded result.
Glimmer reuses this layer wholesale — DataLad coordinates live on every node — and adds the
act of checking.

**Provenance description.** W3C PROV models entities/activities/agents; RO-Crate packages a
dataset with typed metadata; CWL and `cwlprov` describe and record tool/workflow runs;
WorkflowHub publishes workflows. Glimmer's `run-record` is deliberately PROV-shaped (an
Activity that `consumes` entities and `regenerates` derivatives), but it is *executable in
place*: the same node a reader inspects is the node the runner replays and stamps with a
verdict. The contribution is not a new description format but closing the loop between
description and execution inside one typed object.

**Workflow re-execution.** `datalad run` / `datalad containers-run` record a command with
its inputs/outputs and can re-run it; `repro` tools and CI harnesses re-execute pipelines.
The node runner builds directly on `datalad containers-run` for replay. What Glimmer adds
is (a) re-execution as a *graph operation* over typed nodes rather than a shell convention,
(b) a *standards gate* before execution, and (c) *tiered* verification spanning
deterministic, stochastic, and agent-produced outputs — not only byte-equality.

**AI-for-science systems.** End-to-end autoresearch systems (the AI-Scientist line,
FutureHouse, OpenScholar, Coscientist) run fixed internal pipelines. Glimmer is
complementary substrate: the run-record gives such systems a typed, replayable, verifiable
unit of work that survives independently of any one system, so multiple agents can
cooperate on, and audit, the same graph.

---

## 3. The Glimmer graph (recap)

Glimmer represents a research project as a graph of typed nodes, each a Markdown file with
YAML front-matter ("sidecar"), enumerated by a root index. Core node types include
`dataset`, `method`, `derivative`, `finding`, `standard`, `publication`, `concept`,
`experiment`, `instrument`, `persona`, `organization`, and `program`; edges are properties
on the source node. Domain-specific vocabulary lives in *profiles* (e.g. neuroimaging/BIDS)
that augment core types without forking the core. Every node carries a content hash and its
DataLad re-fetch coordinates; an agent that produces a node must attach a `reasoning-trace`
citing the nodes it read. The graph is plain files, so it survives `git clone`,
`datalad export`, and `rsync` with no bespoke database.

This much was descriptive. Section 4 makes it executable.

## 4. Proactive provenance: the `run-record`

### 4.1 The node

A `method` is a *reusable* tool (one skull-strip, applied to many subjects); a `derivative`
is a *product* (a file and its hash). Neither captures *the act*. The `run-record` is that
act — one concrete invocation: **this** command, on **these** content-pinned inputs, in
**this** container, testing **this** hypothesis, on **this** date. Its required core is a
`method`, a `command`, a `provenance-mode` (which selects the default verification tier), a
`status`, a list of pinned `inputs`, and a list of expected `outputs`; edges
(`reruns`/`consumes`/`regenerates`/`emits`, plus `tests-hypothesis`/`addresses-concept`)
make it navigable.

It carries a **lifecycle**: `planned` (written when a hypothesis is decomposed; inputs may
be a *specification* rather than a pin) → `ready` (inputs pinned and standard-valid: the
gate passed) → `running` → `executed` (outputs hashed, verdict written) / `failed` /
`superseded`. The runner advances the lifecycle and writes two blocks back into the node:
`validation-gate` (the pre-run check) and `replay-verdict` (the per-output result).

### 4.2 The node runner

One engine, two modes. **`glimmer run`** is *forward execution* — gate, replay, hash and
record outputs, advance `ready → executed`. **`glimmer rerun`** is *reproduction* —
re-execute an already-recorded run and compare its outputs to what was recorded. The runner
is for running; reproduction is the special case of re-running something already recorded.

Per run-record the engine (i) resolves and pins inputs (materializing via `datalad get`,
matching the recorded annex-key/commit-sha; unreachable inputs short-circuit to an
`inputs-unavailable` verdict that records data liveness — never a false pass), (ii) enforces
the standards gate (§4.3), (iii) replays the command pinned to the container digest via
`datalad containers-run`, falling back to `datalad run` and then a host subprocess flagged
as a dirty environment, (iv) verifies outputs per tier (§4.4), and (v) emits a provenance
manifest and, optionally, writes the verdict back into the graph.

### 4.3 Standards as a runtime gate (referenced, enforced, delegated)

A run-record only **references** the standards its inputs must satisfy (an input-pin's
`conforms-to`, the `requires-standard` edge). The runner **enforces** that each input is
both *pinned* and *valid* before any command runs; a failure yields a `gate-failed` verdict
and no execution. The check itself is **delegated** to the standard's `validator` hint
(e.g. `bids-validator {path}`), or falls back to graph-level validation, recording
`unchecked` honestly when no validator is available. The run-record thus never reimplements
validation, yet "ran on standard-valid data" becomes an enforced, recorded fact — moving
standards from passive metadata into the runtime.

### 4.4 Three verification tiers

Reproducibility is not one thing, and a single notion of "match" is wrong for most science.
The tier is selected by `provenance-mode` and overridable per output.

- **Byte-identical** (deterministic). Re-execute; the output hash must match exactly —
  *after normalization*, because two correct re-runs of an FSL/Nipype step differ in
  volatile header bytes (timestamps, descrip fields) that carry no scientific content. The
  runner zeroes those fields for NIfTI (keeping affine, dtype, and voxels exactly), strips
  GIFTI metadata, and canonicalizes JSON, recording which normalization was applied; if the
  imaging library is unavailable it falls back to a raw compare, recorded as such — never a
  silent pass. (This realizes a normalization that prior tooling promised in a comment but
  never implemented.)
- **Numeric-within-tolerance** (stochastic). Re-derive a number from source and assert
  `|observed − expected| ≤ max(abs, rel·|expected|)`. This is the honest guarantee for
  stochastic analyses, and the mechanism for **reproducing a paper's reported numbers from
  source** within a declared tolerance.
- **Structural** (agent-inferred). LLM/agent prose is not hash-reproducible. Verification
  is structural: the node's `reasoning-trace` must cite real graph nodes, those nodes must
  contain the values the trace claims, and any retriever manifest must be self-consistent —
  the analogue of byte-equality for the stochastic/inferential regime.

Each verdict is recorded with its tier and degradations, so a "verified" verdict is never
silently weaker than its claim (a host-fallback run is marked as such; a tampered expected
hash yields `mismatch`).

### 4.5 Method equivalence and a cross-project registry

A method is a reusable function over pinned data, and its *semantic pattern* — "compute the
mean of a series", "skull-strip a T1w" — is not unique to one project. We separate the
pattern from the implementation with a `registry-ref` (a cross-project namespaced pattern
id) and the edges `implements`, `equivalent-to`, and `refines`. Crucially, `equivalent-to`
is **certified, not asserted**: the runner runs both implementations on the same pinned
inputs and confirms their outputs match (byte-identically or within tolerance). This makes
"an equivalent, cleaner, or faster implementation is acceptable" a checkable statement, and
lets a method's identity — and the verification baseline attached to it — outlive a single
graph. (A dedicated abstract `method-pattern` node type and a published cross-institution
registry are future work; §8.)

## 5. The agentic loop, made executable

Glimmer previously specified a plan→run→feedback→replan research loop — a `concept`
decomposed into hypotheses, agents producing derivatives and findings, a human reviewing —
but it had no runtime primitive; the "run" step left only a derivative behind. The
run-record *is* that primitive. A hypothesis acquires one or more `planned` run-records
(`tests-hypothesis → concept`); running them gates, executes, and emits `derivative`s
(`regenerates`) and a `finding` (`emits`) whose `addresses-concept` edge closes the loop
back onto the question. The feedback the next iteration reads is the recorded verdict plus
the emitted finding — not the agent's memory. This is precisely why the loop becomes
self-sustaining and why the agent failure modes of §1 are structurally suppressed: a
finding cannot be silently lost (it is a node addressing the concept), and a settled
mistake cannot be silently repeated (the prior run's verdict is in the graph and a re-run
must reproduce it).

## 6. Implementation and worked example

The implementation is ~600 lines of dependency-light Python (PyYAML only; DataLad, a
container runtime, the imaging library, and external validators are all feature-detected
and degrade with the degradation recorded). The schema change is additive and
backward-compatible; existing graphs validate unchanged.

The worked example (`examples/synthetic-provenance/`) is the smallest artifact that
exercises the whole design with no real data and no specialized dependencies. A `concept`
is decomposed into four planned runs over a fixed synthetic signal whose input declares
conformance to a toy standard with an executable validator:

| run | provenance-mode | tier | reproduce verdict |
|---|---|---|---|
| `run-synth-mean` | deterministic | byte-identical | `verified` |
| `run-synth-mean-fast` | deterministic | byte-identical | `verified` (certified `equivalent-to` the above) |
| `run-synth-classifier` | stochastic | numeric-within-tolerance (±0.02) | `reproduced-within-tolerance` |
| `run-synth-agent-summary` | agent-inferred | structural | `structurally-valid` |

Forward `glimmer run` advances the planned runs to executed and emits a finding that
addresses the concept; `glimmer rerun` reproduces all four at 100%. Negative controls
behave as designed: a malformed input is caught by the standards gate before execution
(`gate-failed`); a tampered expected hash yields `mismatch`; an unreachable input under
`--offline` yields `inputs-unavailable`; bypassing the gate is recorded as a dirty run; and
`certify_equivalence` confirms the two mean implementations produce identical output. Each
maps to a non-zero exit, so the example doubles as a CI check.

## 7. Discussion

Proactive provenance reframes reproducibility from a property a reader audits by hand to a
property the substrate enforces and re-checks. Three design choices carry the weight.
*First*, tiered verification: insisting on byte-equality for everything is both too strong
(stochastic analyses fail it) and too weak (it ignores agent outputs entirely); matching
the check to the computation's nature is what lets one mechanism span a deterministic
pipeline, a reported statistic, and an LLM interpretation. *Second*, delegated gating:
standards become runtime-enforceable without the runner knowing any standard's internals,
so the design rides the existing validator ecosystem rather than reimplementing it.
*Third*, certified equivalence: it converts the social convention "use an equivalent
method" into a machine-checked relation, which is the seed of a shared verification baseline
across institutions. Together these make the claim "AI-native reproducibility" concrete: an
agent's unit of work is now a contract it can execute and that others can re-execute, with a
verdict that is legible to both machines and reviewers.

## 8. Limitations and future work

The runner replays a recorded command; it does not yet *generate* a reproduction path for
an arbitrary external paper. The planned-run-record with specified (unpinned, possibly
surrogate) inputs is the affordance for **minimal-path reproduction** — synthesizing a
minimal runnable graph to test a published claim even when the original data is unavailable
— which is the principal next step. The method registry currently ships as lightweight
edges plus runtime-certified equivalence; a dedicated abstract `method-pattern` type and a
published, cross-institution registry (with a reputation/provenance model for who
contributed which pattern or baseline) are deferred. Container replay requires DataLad and a
runtime; on a bare host the runner degrades and records the weaker environment, but does not
reconstruct it. Structural verification establishes that an agent cited real values, not
that its interpretation is correct — it guarantees auditability, not truth. Finally, the
worked example is synthetic by design; validating the byte-identical and numeric tiers on a
full neuroimaging pipeline and on a dissertation's reported numbers is in progress in a
downstream project that imports the runner as a dependency.

## 9. Conclusion

We argued that reproducibility belongs *inside* the typed research object as an executable
property, and we realized it with a single node type and one tool. The `run-record` makes a
run a first-class, lifecycle-bearing, standard-gated, self-verifying graph node; the node
runner enforces the gate and verifies outputs at a fidelity matched to the computation. The
result turns the agentic research loop from a description into a running system whose
feedback is recorded verdicts rather than recollection — a concrete substrate for AI-native
science in which "this reproduces" is something the machine demonstrates, not something the
reader is asked to believe.

---

## References (informal)

- BIDS — Brain Imaging Data Structure. Gorgolewski et al., 2016.
- DataLad / git-annex — Halchenko et al., 2021.
- Nipype — Gorgolewski et al., 2011.
- W3C PROV-DM, 2013; RO-Crate — Soiland-Reyes et al., 2022; CWL / cwlprov — Crusoe et al., 2022.
- El Damaty, S. *Reproducibility as Knowledge Graph Navigation: Glimmer …* CAISc 2026.
- Repository: https://github.com/hebbianloop/glimmer ; spec: `docs/proactive-provenance.md`.
