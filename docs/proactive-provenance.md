# Proactive Provenance — the `run-record` and the node runner

> Glimmer v0.6.0. The schema records *what* an output is; proactive provenance makes
> the graph **executable** — so the claim "this output reproduces" is a contract the
> machine can check, not a footnote you trust.

The 2010s gave us reproducible pipelines. Glimmer v0.3–v0.5 gave us a typed graph over
them — datasets, methods, derivatives, findings — each content-hashed. But the graph was
**descriptive**: a `derivative` recorded an `output-hash`, yet nothing could re-execute
the computation and confirm it. The only verification script in the repo
(`examples/ds000114-nipype/verify.py`) re-hashed files already on disk and said so:
*"not a full re-run."* v0.6.0 closes that gap with one new core node type and one tool.

## Why this matters (the failure it fixes)

An agent analyzing a dataset, with no executable contract to anchor to, re-derives the
same numbers different ways, makes the same data-processing mistakes, and forgets prior
findings. Each of those is a reproducibility failure in miniature. A `run-record` makes
the unit of work **replayable, gated, and self-verifying**: the agent (or a human, or CI)
runs it, gets a verdict, and the verdict — not a memory or a hope — is what the next step
reads. This is reproducibility as a property the substrate *enforces*, AI-native by
construction.

## The `run-record`: one concrete, replayable invocation

A `method` is a reusable tool; a `derivative` is a product. Neither is *the act*. The
`run-record` is the PROV `Activity`: **this** command, on **these** pinned inputs, in
**this** container, testing **this** hypothesis, on **this** date — binding a method +
pinned inputs + expected outputs + the environment + a verdict.

It is the **executable unit of the agentic loop** (see [`agentic-loop.md`](agentic-loop.md)).
Authored as part of a plan and advanced through a lifecycle:

```
planned ──gate──▶ ready ──exec──▶ running ──▶ executed
   │                                            │
   │ (inputs may be spec'd/unpinned)            └─▶ failed | superseded
```

- **planned** — written when a `concept` is decomposed into hypotheses; inputs may be a
  *spec* (modality / n / standard) rather than a pin. (The affordance v0.7 minimal-path
  reproduction builds on.)
- **ready** — inputs pinned and standard-valid: the runner's gate passed.
- **running / executed / failed** — the runner advances these and writes the verdict.

Full field list: [`glimmer/schema/schema.md` → run-record](../glimmer/schema/schema.md#run-record).
The required core is `method`, `command`, `provenance-mode`, `status`, `inputs`, `outputs`.

## The runner: `glimmer run` and `glimmer rerun`

Two modes over one engine (`glimmer/tools/run.py`). **The runner is for running, not just
reproducing** — reproduction is the special case of re-running something already recorded.

| command | mode | what it does |
|---|---|---|
| `glimmer run <rokb> <id>` | forward | gate → replay → hash outputs → emit/record products; advance `ready→executed` |
| `glimmer rerun <rokb> <id>` | reproduce | re-execute and **compare** outputs to what was recorded, per tier |

`<id>` is a run-record id, a comma-separated list, or `all` (dependency-ordered so a run
that produces another's input goes first). Flags: `--manifest <path>`, `--write-verdict`,
`--offline`, `--no-container`, `--no-gate`.

The engine, per run-record:

1. **Standards gate.** Each input must be (a) available/pinned (`datalad get` unless
   `--offline`; annex-key / commit-sha match) **and** (b) valid against its declared
   standard. A failed gate ⇒ verdict `gate-failed`, **no execution**.
2. **Execute.** Replay `command` pinned to `container-digest` via `datalad containers-run`;
   fall back to `datalad run`, then a host subprocess (only with `--no-container`, recorded
   as a dirty environment). Cwd is the project root (the rokb's parent — where `code/`,
   `inputs/`, `out/` live).
3. **Verify** (reproduce mode) at the tier selected by `provenance-mode`.
4. **Record.** Write the provenance manifest (JSON); with `--write-verdict`, write the
   `validation-gate` + `replay-verdict` blocks back into the sidecar (and `status`).

## The three verification tiers

Reproducibility is not one thing. The tier is chosen by `provenance-mode` and can be
overridden per output via the output-pin's `tier`.

### byte-identical (`deterministic`)
Re-execute; the output hash must match exactly — **after normalization**, because two
*correct* re-runs of an FSL/Nipype step differ in volatile header bytes. The runner
normalizes before hashing and records how:
- **NIfTI** (`.nii`/`.nii.gz`): blank `descrip`/`db_name`/`aux_file`, zero `cal_*`/`gl*`,
  keep affine + dtype + voxels exactly → `normalization: nifti-header-zeroed`. (Realizes
  the long-promised normalization in `examples/ds000114-nipype/workflow.py`.)
- **GIFTI** (`.gii`): strip the `<MetaData>` block, canonicalize XML.
- **JSON**: canonical re-serialization (sorted keys).
- nibabel absent ⇒ raw compare, recorded as `raw (nibabel unavailable)` — never a silent
  pass.

### numeric-within-tolerance (`stochastic` + `reproduction-tolerance`)
Re-derive a number from source and assert `abs(obs − exp) ≤ max(abs, rel·|exp|)`. The
expected value lives in the output-pin's `expected-values` (the published number); the
tolerance declares how close counts (empty ⇒ exact). This is the honest guarantee for
stochastic analyses **and the mechanism for reproducing a paper's reported numbers from
source.**

### structural (`agent-inferred`)
LLM/agent prose is not hash-reproducible. Verification is structural (per
[`agent-protocol.md`](agent-protocol.md)): the `reasoning-trace` must cite real nodes, those
nodes must hold the claimed values, and the `retriever-manifest` (if any) must be
self-consistent — the analogue of SHA re-execution for the stochastic regime
([`retrieval-adapter.md`](retrieval-adapter.md)).

## Standards as a runtime gate (referenced, runner-enforced, delegated)

A run-record only **references** the standards its inputs must satisfy (input-pin
`conforms-to`, the `requires-standard` edge). It never reimplements validation. The
**runner enforces** the gate; the **check is delegated** to the standard's `validator`
hint:

```yaml
# on a `standard` node
validator: {tool: bids-validator, command: "bids-validator {path}", kind: external}
# or {kind: glimmer} to use `glimmer validate` on the graph
```

`{path}` is the input under test; a zero exit means conformant. Unknown/missing validator
⇒ the gate falls back to `glimmer validate` and records `none (unchecked)` — honest, never
a silent pass. The outcome lands in the verdict's `validation-gate` block, so "ran on
BIDS-valid data" becomes a recorded, enforced fact.

## The provenance manifest

`--manifest <path>` writes a JSON superset of the old `verification-report.json`:

```json
{
  "glimmer-run-version": "glimmer-run 0.6.0",
  "summary": {"verified": 2, "reproduced-within-tolerance": 1, "structurally-valid": 1,
              "total": 4, "reproducibility-rate-pct": 100.0},
  "runs": [ { "node": "...", "verdict": "verified", "tier": "byte-identical",
              "validation-gate": {...}, "environment": {...}, "outputs": [...],
              "numeric-checks": [...], "structural-checks": [...], "exit-code": 0 } ]
}
```

A tampered `expected-hash` ⇒ `mismatch`; an unreachable input ⇒ `inputs-unavailable`
(recording `data-liveness`); a non-pinned-container run ⇒ `environment.resolved-via: host`.
The verdict is never silently weaker than the claim.

## Method registry affordances (v0.6 lightweight; full program v0.7)

A method is a reusable f(x), and its *semantic pattern* can outlive one project's graph.
v0.6 adds:
- `registry-ref` — a cross-project namespaced id naming the canonical pattern (e.g.
  `glimmer-methods:skullstrip-t1w`); `implements` is its navigable edge.
- `equivalent-to` — two methods that produce the same outputs. **Certified, not asserted:**
  `certify_equivalence(rokb, run_a, run_b)` runs both on the same input and confirms the
  outputs match (byte-identical, or within tolerance). An equivalent-but-faster/cleaner
  implementation is tolerated; the pattern links back.
- `refines` — a tuned / fine-tuned variant.

A dedicated `method-pattern` node type, a published cross-institution registry, and
minimal-path reproduction of arbitrary external papers are **deferred to v0.7**.

## Worked example

[`examples/synthetic-provenance/`](../examples/synthetic-provenance/) exercises the loop +
all three tiers + the standards gate + equivalence certification, with no real data and no
heavy dependencies. Start there.

## Using it downstream (e.g. an ADS dissertation harness)

The runner's public surface is importable, so a domain harness re-uses the audited engine
instead of re-implementing verification:

```python
from glimmer.tools.run import load_graph, run_node, write_manifest, RunVerdict, sha256_file

# one run-record per published number, each with a reproduction-tolerance and a
# tests-hypothesis edge to its concept:
verdicts = [run_node(ROKB, rid, mode="reproduce") for rid in claim_run_ids]
write_manifest(verdicts, "docs/data/provenance_manifest.json")
```

The domain repo supplies only data + command + tolerance + standard references; Glimmer
supplies the gate, the tiers, the normalization, and the verdict.
