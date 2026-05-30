# Glimmer Agent Protocol

> Every scientific output an AI agent produces in a Glimmer graph must be **verifiable**: the evidence it accessed, the standards it applied, and the reasoning it followed must be inspectable after the fact.
>
> This document specifies the protocol every Glimmer agent must follow when it issues an output that enters the graph as a `qc-artifact`, `derivative`, or `publication` node.

## The problem this protocol solves

A frontier LLM can produce a confident-sounding rating on a scan it never saw. Without protocol-level discipline, the rating enters the graph and downstream consumers cannot tell whether it was grounded in actual evidence or in priors from training data. This is the irreproducibility crisis at the AI-output layer.

Glimmer's response: **declare your evidence chain or you are not a valid contributor.** Outputs that don't conform to the protocol are not loaded by downstream agents and are flagged by the validator.

## The five requirements

A Glimmer agent issuing an output to the graph MUST:

1. **Declare its identity.** The agent registers as a `rater` node with `role: agent`, `model-identifier: <stable model name + version>`, `glimmer-version: <schema version>`.

2. **Emit a structured `reasoning-trace`** on every `qc-artifact`, `derivative`, or `publication` node it produces. The trace must include:
   - `nodes-accessed`: list of every Glimmer node id the agent read during the decision.
   - `metrics-weighted`: which numeric or categorical evidence the agent treated as load-bearing, with rationale.
   - `standard-anchor`: which anchor of the rating scale (or other applicable standard) the evidence matched.
   - `evidence-summary`: a one-paragraph free-text justification, citing node ids inline.
   - `timestamp`: when the verdict was issued.

3. **Cite only evidence the protocol grants access to.** An agent operating in `blind` mode may not read peer QC artifacts. An agent operating in `informed` mode may. The mode is recorded on every output and must be consistent with what `nodes-accessed` actually lists.

4. **Distinguish derivation from inference.** A `derivative` node produced by deterministic computation (a Nipype pipeline running on raw data) is different from a `derivative` produced by LLM inference over graph context. The two MUST NOT be conflated. `derivative.output-kind` must include a `provenance-mode` field with value `deterministic` or `agent-inferred`.

5. **Decline when evidence is insufficient.** If the agent's traversal did not reach evidence sufficient to render a decision, the protocol-conforming output is:
   ```yaml
   decision: needs-review
   reasoning-trace:
     evidence-summary: "Insufficient evidence in graph. Specifically, no visual-report nodes were available for the per-category anatomical inspection that the rating-scale standard requires."
   ```
   This is a feature, not a failure. An agent that fabricates a confident output in this regime violates the protocol.

## What this looks like in practice

A conforming agent's `qc-artifact` sidecar:

```yaml
---
id: qc-agent-001-on-subject-002-pial
type: qc-artifact
artifact-kind: ordinal-rating
ratings:
  pial: 3
edges:
  - {type: attests-to-quality-of, target: subject-002}
  - {type: issued-by, target: rater-agent-claude-opus-4.7}
  - {type: conforms-to, target: ads-qc-scale-v1}
reasoning-trace:
  mode: blind
  nodes-accessed:
    - subject-002
    - method-recon-all-fs6
    - ads-qc-scale-v1
  metrics-weighted:
    euler-lh: "weighted heavily; -246 indicates significant topological defects"
    euler-rh: "weighted heavily; -200 in the same direction"
    talQC: "weighted lightly; 0.98 is in the acceptable range"
    CNR: "weighted lightly; 1.29 is borderline acceptable"
  standard-anchor: "3 (local errors with editing required)"
  evidence-summary: "Euler numbers (lh:-246, rh:-200) on subject-002 indicate widespread topological defects that the rating-scale anchor at level 3 describes as 'local errors with editing required.' CNR and talQC are within acceptable ranges so the defects are localized rather than global. The agent did NOT have visual-report nodes available for category-specific inspection of pial surface accuracy; this is the architectural limitation diagnosed in the parent paper."
  model-identifier: anthropic/claude-opus-4
  timestamp: 2026-05-28T22:30:00Z
---
```

A non-conforming output (the kind the protocol exists to prevent) would look like:

```yaml
---
id: qc-agent-001-on-subject-002-pial
type: qc-artifact
ratings:
  pial: 3
edges:
  - {type: attests-to-quality-of, target: subject-002}
  - {type: issued-by, target: rater-agent}
# no reasoning-trace
# no mode declaration
# no model-identifier
---
```

This sidecar would fail validation. The validator (`glimmer validate`) refuses to mark the graph valid if any agent-issued `qc-artifact` is missing `reasoning-trace`.

## Why the protocol matters for the CAISC 2026 demonstration

The empirical results reported in the parent paper depend on this protocol. The blind-condition agent produced per-subject-uniform ratings because the graph's evidence was metric-only — and the agent's reasoning traces show exactly this: every category cites the same Euler-number evidence, because no category-specific evidence existed in the graph to cite. The trace makes the failure mode auditable. The informed-condition agent's improved κ is attributable specifically to the peer-rating evidence it accessed, again audited by the trace.

Without the protocol, the same agent producing the same numbers could be interpreted in many ways. With the protocol, the interpretation is fixed: the agent issued these ratings on the basis of this evidence, and no other.

## What this protocol does not solve

- **The agent's reasoning may still be wrong**, even when grounded in real evidence. Glimmer's audit makes errors traceable; it does not eliminate them.
- **The agent's evidence selection may be biased** by what the graph happens to contain. Sparse graphs invite over-weighting of the available signals (see the blind-condition failure).
- **The protocol does not specify decision quality** — it specifies verifiability of decisions. Quality is the agent's responsibility, audited by the human review process the verdicts feed into.

## Relationship to other protocols

- **PROV-O** specifies provenance vocabulary; Glimmer's `reasoning-trace` is one PROV-O-conformant instantiation.
- **NIDM-Results** specifies neuroimaging-specific statistical provenance; Glimmer's `derivative.provenance-mode` distinguishes deterministic NIDM-Results-compatible outputs from agent-inferred outputs.
- **Anthropic's Constitutional AI** and similar constitutional-alignment frameworks operate at the model-training layer. The Glimmer protocol operates at the output layer: it enforces verifiable evidence trails on whatever model is producing outputs.

## Open questions for v0.2

- Should the `reasoning-trace` field be cryptographically signed by the agent's identity (e.g., via a decentralized-identifier scheme like the Holonym-style verifiable researcher identity)? This would let downstream consumers verify that a given verdict was genuinely produced by the claimed agent, not forged.
- Should the protocol require a confidence interval on agent ratings (`rating-confidence: 0..1`)? Useful for downstream prioritization of human review.
- How should the protocol handle multi-step agent reasoning, where the agent traverses the graph, produces an intermediate finding, and then traverses again on the basis of that finding? Current trace is flat; a richer structure would record the traversal trajectory.
