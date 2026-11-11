# Synthetic provenance: portable verifier fixture

This example checks runner behavior with synthetic data. It is not an empirical
neuroimaging result or an agent benchmark. The summary is a Python script; the
“classifier” emits a fixed accuracy plus random jitter, without training a model.

## Fresh checkout

From the repository root, with Python 3.10 or newer:

```bash
python -m venv .venv
. .venv/bin/activate
pip install .
python examples/synthetic-provenance/smoke.py
```

The installed CLI smoke test builds the entire graph from committed
`graph-template.json` and `inputs/`, runs three numeric/hash examples, pins their
observed products for the summary stage, runs the summary, and checks rejection
of malformed input and implicit host fallback. No pre-existing `rokb/` or cached
outputs are required. It reports two normalized matches, one numeric-tolerance
pass and one structural pass. These are distinct guarantees, not “100% scientific
reproducibility.” Validation has two advisory warnings for input datasets without
`produced-by` edges; no schema errors are permitted.

## Individual steps

```bash
python examples/synthetic-provenance/emit_graph.py
glimmer validate examples/synthetic-provenance/rokb
# validate exits 2 for the two advisory input-dataset warnings.

glimmer rerun examples/synthetic-provenance/rokb \
  run-synth-mean,run-synth-mean-fast,run-synth-classifier \
  --no-container --offline --manifest /tmp/glimmer-positive.json

python examples/synthetic-provenance/emit_graph.py --pin-summary-inputs
glimmer rerun examples/synthetic-provenance/rokb run-synth-agent-summary \
  --no-container --offline --manifest /tmp/glimmer-summary.json

# Expected exit 1; no output should be produced.
glimmer run examples/synthetic-provenance/rokb run-synth-gate-fail \
  --no-container --offline
```

`--pin-summary-inputs` records hashes of the actual upstream files. It does not
certify their provenance. Re-running the stochastic stage changes its bytes and
requires explicitly pinning the new products before running the summary. The
initial summary run is `planned` and cannot execute without those pins.

`--no-container` is deliberate: the portable fixture runs on the host and records
an unpinned environment. Real container-runtime validation is separate. `all`
includes the deliberate negative case and unprepared downstream runs; it is not
the positive benchmark set.

## Evidence and tests

```bash
python -m unittest discover -s tests -v
python -c "from glimmer.tools.run import certify_equivalence; print(certify_equivalence('examples/synthetic-provenance/rokb', 'run-synth-mean', 'run-synth-mean-fast', no_container=True).to_dict())"
```

Tests include wrong/missing pins, unavailable validators, missing/stale outputs,
empty and false traces, non-finite numeric values, dependency cycles, container
fallback, equivalence failures and raw-versus-normalized hashing. See
[the runner documentation](../../docs/proactive-provenance.md) for supported
formats and limits.

Generated `rokb/`, `out/` and manifests are ignored. Rebuilding restores the
fixture's authored graph; use a separate project for real research records.
