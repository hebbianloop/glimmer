# Example: DataLad → Nipype → Verifiable Trace on OpenNeuro ds000114

This is the canonical Glimmer worked example. It demonstrates how a real reproducible-neuroimaging analysis — clone a public DataLad-distributed BIDS dataset, run a deterministic Nipype workflow, capture provenance — fits into a Glimmer research-object knowledge base, and how a downstream agent can verify the trace.

## What's here

- **`install.sh`** — clones [ds000114](https://openneuro.org/datasets/ds000114/versions/1.0.2) via DataLad and fetches a single subject's T1w (~30 MB, full dataset is 4.3 GB).
- **`workflow.py`** — minimal Nipype anatomical preprocessing workflow: `fsl.BET` (skull strip) → `fsl.FAST` (3-class tissue segmentation). Deterministic with fixed parameters.
- **`emit_graph.py`** — runs the workflow, captures Nipype's provenance (versions, parameter hashes, output paths), records DataLad commit SHAs and git-annex keys, and emits Glimmer sidecars under `rokb/`.
- **`verify.py`** — reads the emitted Glimmer graph, re-runs each `method` on its cited `dataset` at the pinned SHA, and compares the new derivative hash against the original. Reports verifiability rate.
- **`rokb/`** — generated Glimmer instance after running the steps above.

> *Planned:* an optional `agent.py` — an LLM agent that reads the graph and emits a `finding` with natural-language interpretation whose `reasoning-trace` satisfies the agent protocol — ships with the reference agent SDK (roadmap v0.5). It is not included in this example yet.

## What it demonstrates

1. **Reproducibility-by-substrate.** The Glimmer graph alone is sufficient to re-fetch the input data and re-run the analysis: every node carries DataLad coordinates (`datalad-superdataset`, `datalad-commit-sha`, `datalad-annex-key`), the workflow definition SHA, and the derivative output hash.

2. **Verifiable traces.** `verify.py` does not trust the graph's claims — it re-executes them. A trace is "verified" if and only if re-running the cited method on the cited input at the cited SHA produces a derivative whose hash matches the originally recorded `output-hash`.

3. **Findings as the unit between derivative and publication.** The graph distinguishes raw pipeline output (`derivative`: "T1w brain volume in mm³") from an interpreted finding (`finding`: "Subject sub-01 has a brain volume of X mm³, within expected range for healthy adult"). A publication aggregates findings via `aggregates` edges; each finding's `based-on` chain stays auditable.

4. **Agent-as-rater is generic, not QC-specific.** The agent role is just a producer of `finding` nodes. The verifiability protocol applies to any agent output, not just quality-control judgments.

## Run the example

```bash
# 1. Install dependencies
pip install datalad nipype nibabel
# FSL must be available on PATH (or use the nipreps/fmriprep Docker container)

# 2. Clone ds000114 + fetch sub-01 T1w
bash install.sh

# 3. Run the workflow and emit the Glimmer graph
python workflow.py
python emit_graph.py

# 4. Validate the graph against the schema
glimmer validate rokb/

# 5. Verify the trace (re-run the analysis from the graph's pinned SHAs)
python verify.py
```

> Step 6 — having an LLM agent read the graph and emit an interpreted `finding`
> (`OPENROUTER_API_KEY=... python agent.py`) — arrives with the reference agent SDK (roadmap v0.5).

## Expected output

`verify.py` should report **verifiability = 100%** for deterministic Nipype/FSL outputs on the demo subject. Any deviations (e.g., FSL versions with non-deterministic behavior, GPU-randomized init) are flagged as verification failures rather than silently passing — which is the architectural property the paper makes.

## Where this fits in the paper

This example is the empirical core of [the CAISC 2026 Glimmer paper](https://github.com/hebbianloop/caisc2026-glimmer-paper). §4 walks through the exact graph this example produces; §4.5 reports the verifiability rate; §4.7 describes the architectural verifiability protocol that an agent-produced `finding` must satisfy.

## Why ds000114

- **Small enough to demo:** 10 subjects, 4.3 GB full; we use 1 subject's T1w (~30 MB).
- **BIDS-conformant and DataLad-installable:** `datalad install ///openneuro/ds000114` works out of the box.
- **Test-retest design:** the dataset's own structure exposes reproducibility questions — perfect for a verifiable-trace demonstration.
- **Public + well-documented:** Pernet et al. published methods + data; cite-able as `dataset` in any downstream paper.
