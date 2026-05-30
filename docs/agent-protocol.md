# Glimmer Agent Protocol

> Every scientific output an AI agent produces in a Glimmer graph must be **verifiable**: the evidence it accessed, the standards it applied, and the reasoning it followed must be inspectable after the fact.
>
> This document specifies the protocol every Glimmer agent must follow when it issues an output that enters the graph as a `finding`, `derivative`, or `publication` node.

## The problem this protocol solves

A frontier LLM can produce a confident-sounding finding on a dataset it never saw or a derivative it never re-computed. Without protocol-level discipline, the output enters the graph and downstream consumers cannot tell whether it was grounded in actual evidence or in priors from training data. This is the reproducibility crisis at the AI-output layer.

Glimmer's response: **declare your evidence chain or you are not a valid contributor.** Outputs that don't conform to the protocol are rejected by the validator and not loaded by downstream agents.

## The five requirements

A Glimmer agent issuing an output to the graph MUST:

1. **Declare its identity.** The `produced-by-agent` field on the emitted node carries a stable identifier (model name + version + system configuration). For deterministic computations (a Nipype workflow, a Python script), the identifier names the script's git SHA, not an LLM.

2. **Emit a structured `reasoning-trace`** on every agent-produced `finding`, `derivative`, or `publication` node. The trace must include:
   - `nodes-accessed`: list of every Glimmer node id the agent read during the decision.
   - `metrics-cited`: which numeric or categorical evidence the agent treated as load-bearing, with rationale.
   - `evidence-summary`: a one-paragraph free-text justification, citing node ids inline.
   - `model-identifier`: the agent's stable identifier.
   - `timestamp`: when the output was issued.

3. **Cite only evidence the protocol grants access to.** When the agent traverses the graph, the trace must list exactly the nodes it read. An agent that claims a finding based on a node it never accessed violates the protocol; the validator flags inconsistencies between the trace and the cited evidence chain.

4. **Distinguish derivation from inference.** A `derivative` node produced by deterministic computation (a Nipype pipeline running on raw data) is different from a `derivative` produced by LLM inference over graph context. The two MUST NOT be conflated. `derivative.provenance-mode` records `deterministic`, `agent-inferred`, or `stochastic`; the verification routine treats them differently.

5. **Decline when evidence is insufficient.** If the agent's traversal did not reach evidence sufficient to render an output, the protocol-conforming response is to emit a `finding` whose interpretation states the insufficiency, with `confidence: low` and a `reasoning-trace` that names the missing evidence. An agent that fabricates a confident output in this regime violates the protocol.

## What this looks like in practice

A conforming agent's `finding` sidecar:

```yaml
---
id: finding-sub-01-brain-volume
type: finding
interpretation: "Subject sub-01 has an estimated brain volume of 1,234,567 mm³"
based-on:
  - derivative-sub-01-T1w-brain
  - derivative-sub-01-fast-pve-0
  - derivative-sub-01-fast-pve-1
  - derivative-sub-01-fast-pve-2
produced-by-agent: anthropic/claude-opus-4
confidence: high
reasoning-trace:
  nodes-accessed:
    - dataset-sub-01-T1w
    - method-fsl-bet
    - method-fsl-fast
    - derivative-sub-01-T1w-brain
    - derivative-sub-01-fast-pve-0
  metrics-cited:
    brain-voxel-count: "weighted heavily; nonzero-voxel count in BET output"
    voxel-volume-mm3: "weighted heavily; from NIfTI header"
    pve-tissue-fractions: "supporting evidence; consistent with healthy adult range"
  evidence-summary: "Brain volume computed by reading [[derivative-sub-01-T1w-brain]] (BET output, deterministic), counting nonzero voxels, and multiplying by voxel spacing from [[dataset-sub-01-T1w]]'s NIfTI header. FAST PVE maps [[derivative-sub-01-fast-pve-*]] used as sanity check on tissue fractions."
  model-identifier: anthropic/claude-opus-4
  timestamp: 2026-05-30T13:00:00Z
edges:
  - {type: based-on, target: derivative-sub-01-T1w-brain}
  - {type: based-on, target: derivative-sub-01-fast-pve-0}
---
```

A non-conforming output (the kind the protocol exists to prevent) would look like:

```yaml
---
id: finding-sub-01-brain-volume
type: finding
interpretation: "Subject sub-01 has an estimated brain volume of 1,234,567 mm³"
produced-by-agent: anthropic/claude-opus-4
# no based-on
# no reasoning-trace
---
```

This sidecar would fail validation. The validator refuses to mark the graph valid if any agent-issued node is missing `reasoning-trace` or `based-on`.

## Sanity-checking against source

A discipline borrowed from the `mrinit` project: when an agent's reasoning trace cites a derivative whose method version drifted from upstream source, the verification routine should rebuild the method from source rather than trusting the cached binary. This catches the common failure mode where a container or local binary diverges silently from the published toolchain. Methods carry `workflow-definition-sha` and may optionally carry `source-checkout-url` plus `source-build-instructions` so an agent can fall back to source-rebuild when verification flags drift.

This is not a hard requirement at v0.2 — the validator accepts cached-binary verification — but every author who has run a multi-year neuroimaging project will recognize the rebuild-from-source step as the recovery move when a pipeline goes sideways. The schema makes it expressible; downstream agents may choose to enforce it.

## Why the protocol matters

The structure makes audit possible; the audit itself remains a human responsibility. A finding's `reasoning-trace` lets a reviewer walk back through the cited nodes (the input dataset's DataLad SHA, the method's workflow-definition SHA, the derivative's output-hash) and verify that the agent's claim is grounded in evidence that exists, conforms to the standards it cites, and produces the values the agent reports.

For deterministic outputs (a Nipype workflow), verification is exact: re-running from the cited SHAs must produce a byte-identical output. For LLM-inferred outputs, verification is structural: the trace must cite real nodes, the cited nodes must contain the values the trace claims, and the interpretation must be a plausible reading of those values. Neither test guarantees correctness; together they guarantee auditability.

## What this protocol does not solve

- **The agent's reasoning may still be wrong**, even when grounded in real evidence. Glimmer's audit makes errors traceable; it does not eliminate them.
- **The agent's evidence selection may be biased** by what the graph happens to contain. A sparse graph invites over-weighting of the available signals; a dense graph requires the agent to choose what to attend to.
- **The protocol does not specify decision quality** — it specifies verifiability of decisions. Quality remains the agent's (and the reviewing human's) responsibility.

## Relationship to other protocols

- **PROV-O** specifies provenance vocabulary; Glimmer's `reasoning-trace` is one PROV-O-conformant instantiation.
- **NIDM-Results** specifies neuroimaging-specific statistical provenance; Glimmer's `derivative.provenance-mode: deterministic` corresponds to NIDM-Results-compatible computations.
- **Anthropic's Constitutional AI** and similar alignment frameworks operate at the model-training layer. The Glimmer protocol operates at the output layer: it enforces verifiable evidence trails on whatever model is producing outputs.
