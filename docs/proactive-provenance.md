# Executable provenance: supported checks and their limits

The v0.6 runner executes trusted local `run-record` nodes and records bounded
verification results. This branch is a development candidate, not a released
package or an evaluated autonomous scientist. Install it with `pip install .`;
the installed command is `glimmer`. `pip install '.[imaging]'` adds NIfTI support.

## Run and reproduce

```bash
# Build all synthetic sidecars and the index from committed sources.
python examples/synthetic-provenance/emit_graph.py
# Run the complete installed-CLI smoke check, including negative cases.
python examples/synthetic-provenance/smoke.py
```

`glimmer run <rokb> <id>` executes and records products. `glimmer rerun <rokb>
<id>` executes and compares products with previously declared expectations.
IDs can be comma-separated or `all`; `all` includes negative fixtures and any
unprepared downstream runs, so its exit status is not a benchmark score.

A graph in a directory named `rokb` uses its parent as the working directory.
An index directly at the project root uses that directory. Other layouts pass
`--run-root`. `--manifest` saves results; `--write-verdict` updates the run-record.
A failed check never replaces an expected output hash. Failed verdicts set the
record's status to `failed`.

## Inputs and standards

Every executed input needs a resolvable node, available file and content pin.
`planned` records may describe unpinned inputs, but cannot execute until pinned.

- Hash-based `datalad-annex-key` values using SHA256/SHA256E or MD5/MD5E are
  checked against actual file bytes and size, including offline. SHA-256 is
  preferred. Placeholder keys and unsupported backends fail.
- `datalad-commit-sha` requires a full commit identifier and compares the file's
  Git blob at that revision with current bytes. Symlink blobs and unresolved
  repositories fail; use an annex content key for annexed input bytes.
- If both pins are supplied, both must match. `--no-gate` never bypasses pin checks.
- Standards declared by an input pin or its node’s `conforms-to` edges must
  exist and have an available validator that passes. A run’s `requires-standard`
  edges must map to these input declarations; an unbound requirement fails.
  Missing tools or validator declarations fail. `{path}` substitution preserves
  paths with spaces. A `kind: glimmer` validator checks graph schema only; it
  does not establish BIDS or scientific data conformance.
- `--offline` prevents automatic `datalad get`. `--no-gate` skips standards only,
  reports `unchecked`, exits unsuccessfully and cannot count as reproduction.

Commands and validator strings are parsed as argv, without an implicit shell.
Pipelines, expansion and redirection require an explicit shell command. These
records execute code and are for reviewed, trusted local graphs; this is not a
sandbox for downloaded or federated records.
The runner does not independently pin the implementation of a method or its
validator. Include source files as declared pinned inputs when code identity is
part of the check, and review the command and environment configuration.

## Execution environment

Without `--no-container`, the runner requires:

1. `container-image`: a **registered DataLad container name**.
2. `container-digest`: the full raw SHA-256 of that registration's available
   local image file, such as a SIF image.
3. DataLad, its container extension and a working runtime configured by the
   project.

The runner resolves the registration through `datalad -f json containers-list`,
checks the local file hash, and calls `containers-run -n <registered-name>` with
explicit inputs and outputs. It does not substitute an OCI URL/digest for the
registration name. Missing registration, image, extension or runtime fails;
there is no automatic host fallback. OCI registry manifest digests are not
local image-file hashes. The configured execution wrapper must itself be trusted.

An explicit `--no-container` runs on the host and records `pinned: false`.
A matching result in this mode does not establish environment reproducibility.
Regression tests mock the registered-container interface; the portable smoke
example uses the host. Neither is evidence of a successful real container run.
The invocation follows the upstream [containers-run interface](https://docs.datalad.org/projects/container/en/latest/generated/man/datalad-containers-run.html).

Every output must exist as a file and be refreshed by the command. Unchanged
pre-existing outputs cannot substitute for execution. Outputs cannot alias
pinned inputs, and inputs are re-hashed after the command to detect mutation.
File freshness is an accidental-error check, not proof against a malicious
command that deliberately forges its outputs.

## Output verification

Output-pin `tier` is explicit where needed. Defaults are byte identity for
`deterministic`, numeric tolerance for `stochastic`, and structural checks for
`agent-inferred`.

| Tier | Successful verdict | What was checked |
|---|---|---|
| `byte-identical` | `verified` | Raw output bytes match `expected-hash`. |
| `normalized-content` | `normalized-match` | The documented normalized representation matches `expected-hash`; raw bytes may differ. |
| `numeric-tolerance` | `reproduced-within-tolerance` | Each declared `expected-values` quantity passes a finite numeric comparison. |
| `structural` | `structurally-valid` | Fresh JSON outputs contain a nonempty trace and supported numeric citations matching pinned evidence. |

Mixed output tiers report `checks-passed` only if all their respective checks
pass. No result implies another tier. Forward execution reports `executed`,
not reproduced; structural outputs must also pass evidence checks in forward mode.

### Normalized content

JSON is serialized with sorted keys. NIfTI normalization excludes the documented
volatile header fields (`descrip`, `db_name`, `aux_file`, `cal_min`, `cal_max`,
`glmax`, `glmin`) while retaining other header bytes, extensions, shape, affine,
dtype, scaling and exact stored voxel values. GIFTI XML is serialized with metadata retained because metadata can
carry scientific meaning. The verdict records the normalization or raw fallback.
A fallback never establishes normalized equivalence. Names containing multiple
dots are recognized by their final format suffix.

### Numeric agreement

`reproduction-tolerance` supplies `default` and optional per-quantity `{rel, abs}`
limits. The rule is `abs(observed - expected) <= max(abs, rel * abs(expected))`.
An empty tolerance means exact equality. Expectations must be nonempty; values
and tolerances must be finite numbers, not booleans, with nonnegative tolerances.
NaN, infinity, missing quantities and invalid structures fail.

### Structural evidence

The runner checks `reasoning-trace` in the **new output JSON**, not just an old
sidecar. It requires `nodes-accessed`, `metrics-cited`, `evidence-summary`,
`model-identifier` and `timestamp`. Citations must resolve to pinned inputs.
Each `metrics-cited` entry uses this shape:

```json
{
  "mean-signal": {
    "node": "derivative-synth-mean",
    "value": 0.5,
    "tolerance": {"abs": 0.0}
  }
}
```

The named quantity is read from that input's JSON object and compared with the
claimed value. Prose-only metric rationales are descriptive records, not
executable checks. Retriever snapshot verification is not implemented; a trace
claiming a `retriever-manifest` therefore fails rather than passing from a model
name alone. Unsupported evidence formats fail explicitly.

This checks citation/value consistency. It does **not** prove that the narrative
follows from the evidence, that the method is scientifically sound, or that an
agent's reported reasoning is faithful. The synthetic summary is a Python script,
not an LLM evaluation; its noisy “accuracy” is a toy value, not a fitted model.

## Reports, equivalence and migration

Manifests separate forward `execution` counts from `reproduction` counts by
verdict. There is no pooled reproducibility percentage that mixes hash matches,
structural checks, execution or negative controls. Negative cases remain visible;
a benchmark must declare its positive and negative sets separately.

`certify_equivalence` compares nonempty output sets of the same size, using
matching input content. It snapshots A before B can overwrite a shared output
path. Numeric comparison requires matching nonempty key sets and finite values.
This establishes agreement on the observed inputs only, not universal equivalence
of methods. Cyclic dependencies and ambiguous output producers fail ordering.

Migration from the earlier PR implementation:

- Opt in to host execution, or configure a registered, hash-pinned image.
- Replace synthetic placeholder input keys with actual content pins.
- Change normalized-output pins from `byte-identical` to `normalized-content`;
  keep raw SHA-256 expectations only for `byte-identical`.
- Emit structured, checkable evidence in the actual output for structural runs.
- Consumers of `reproducibility-rate-pct` must use the separate verdict counts.

No new core node or edge type is introduced. This hardening does not implement
ADS integration, actual LLM evaluation, public multi-subject benchmarking or
cross-project federation. Those require separate acceptance evidence.
