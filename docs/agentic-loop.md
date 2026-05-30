# The Agentic Loop in a Glimmer Project

> Applying the **plans-as-issues** pattern to scientific research, using Glimmer as the substrate. This is the operational model for autonomous and semi-autonomous research workflows over a Glimmer graph.

## The mapping

| Holonym / agents-baseline term | Glimmer-native equivalent |
|---|---|
| Plan (a multi-step intent) | A `concept` node + a tracked issue |
| Issue (a unit of execution) | A `concept` node's sub-task list, OR a separate issue in the project tracker |
| Autoresearch loop | An agent run that traverses Glimmer + literature + data, producing `derivative` and `publication` nodes |
| Mode of operation (Perimeter / Core) | The agent protocol's `mode: blind` or `mode: informed`, plus access constraints (see `docs/agent-protocol.md`) |
| TAP approval | Required for any agent output that becomes an external `publication` or a destructive `qc-artifact`; advisory for internal `derivative` nodes |

## The state machine

```
                      ┌─────────────────┐
                      │  research idea  │
                      └────────┬────────┘
                               │ author writes the idea down
                               ▼
                  ┌────────────────────────────┐
                  │  concept node (v0.3)       │
                  │  + issue tracking the work │
                  └─────────────┬──────────────┘
                                │ decompose
                                ▼
              ┌────────────────────────────────────┐
              │  sub-concepts / hypotheses         │
              │  (specific falsifiable claims)     │
              └─────────────┬──────────────────────┘
                            │ for each sub-concept,
                            │ launch an autoresearch agent
                            ▼
          ┌─────────────────────────────────────────────┐
          │  agent loop (one per sub-concept):          │
          │                                             │
          │  1. walk literature graph (publication      │
          │     nodes + their citation edges)           │
          │  2. walk data graph (dataset, derivative,   │
          │     qc-artifact nodes)                      │
          │  3. emit a `derivative` summary node with   │
          │     reasoning-trace per the agent protocol  │
          │  4. emit a draft `publication` node if      │
          │     the evidence supports a claim           │
          │  5. emit `needs-review` if evidence is      │
          │     insufficient                            │
          └─────────────────┬───────────────────────────┘
                            │ outputs route to human review
                            ▼
              ┌─────────────────────────────┐
              │  human reviews:             │
              │    - approve → publication  │
              │    - revise → loop back     │
              │    - reject → close concept │
              └─────────────────────────────┘
```

## The four agent roles

A Glimmer project typically uses four distinct agent roles, each operating with a different protocol mode and access scope.

1. **Literature scout.** Traverses external literature (PubMed, OpenAlex, Semantic Scholar) plus the project's existing `publication` nodes. Emits new `publication` nodes for relevant prior work. Read-only on the local graph; cannot issue verdicts on local data.

2. **QC agent.** Operates on `dataset` nodes and their derivatives. Produces `qc-artifact` nodes with full `reasoning-trace` per the agent protocol. Two modes (blind / informed) as documented.

3. **Analysis agent.** Runs deterministic computation (Nipype pipelines, statistical models). Emits `derivative` nodes with `provenance-mode: deterministic`. Distinct from agents that produce inferred outputs — see the agent protocol.

4. **Synthesis agent.** Walks the graph after the prior three roles have populated it. Produces draft `publication` nodes by composing `derivative` + `qc-artifact` + cited `publication` nodes into a coherent argument. Outputs require human review before they become external publications.

The same underlying frontier LLM may serve all four roles; the role is defined by the protocol mode and access scope, not by which model is used.

## A worked example: drafting the CLAD Wave 4 paper

The ADS / CLAD project (the parent dataset of the CAISC 2026 paper) has five priority-7 dormant papers. As a worked example of the agentic loop:

1. **Author creates a `concept` node** named `concept-emofilm-violence-outcome` with a corresponding issue: *"Naturalistic emotional-film fMRI in adolescence prospectively predicts violence outcomes in emerging adulthood."*

2. **Decompose the concept** into hypotheses:
   - H1: Wave 1-3 EmoFilm BOLD response amplitude in amygdala predicts Wave 4 CDC-VPC violence outcome.
   - H2: Wave 3 prefrontal-amygdala functional connectivity during EmoFilm modulates the H1 prediction.
   - H3: Sex moderates H1 and H2.

3. **Launch agent runs**:
   - Literature scout pulls the prior literature on EmoFilm-class naturalistic paradigms and violence outcome (publishing each relevant prior work as a `publication` node in the local graph).
   - QC agent walks the Wave 1-3 EmoFilm data, producing per-subject `qc-artifact` nodes with the verifiability protocol — these gate which subjects enter the analysis.
   - Analysis agent runs the BOLD-amplitude extraction (Nipype, `provenance-mode: deterministic`), producing per-subject `derivative` nodes.
   - Synthesis agent walks H1's evidence chain — qualifying subjects from QC, their derived BOLD amplitudes, the Wave 4 violence outcomes — and drafts a result paragraph as a `publication` node.

4. **Human review** of the synthesis agent's output:
   - The `reasoning-trace` enumerates which subjects entered the analysis and why.
   - The reviewer can drill into any `qc-artifact` or `derivative` and inspect the evidence chain.
   - Approve → the synthesis becomes the paper draft; revise → the agent re-runs with a constrained protocol; reject → the concept gets a `superseded-by` edge to a refined replacement.

## Why this matters beyond the immediate project

The agentic loop applied to research is structurally identical to the agentic loop applied to software engineering, customer support, or any other multi-step knowledge work. Glimmer is the substrate that makes it scientific: typed entities, versioned edges, evidence traces, standards conformance. The loop produces verifiable scientific outputs because the substrate enforces verifiability.

The CAISC 2026 paper demonstrates one node of this loop (QC agent) on one dataset. The broader vision is that the entire research workflow — from research-question to published paper — can be expressed as Glimmer graph operations executed by collaborating agents, with humans operating at the review-and-approve layer.

## Relationship to OpenAlex / Semantic Scholar / PubMed

The literature scout agent treats external publication databases as remote graph extensions. It does not import the entire database; it imports only the `publication` nodes that the project's concepts have edges to. The project's local Glimmer graph therefore stays bounded; the literature it depends on is fully traceable; new relevant work can be added incrementally as the concept evolves.

## Relationship to autoresearch systems

Systems like OpenScholar, FutureHouse, AutoML, and the AI Scientist series (Sakana, Lange, Anthropic's Coscientist) operate end-to-end on a fixed pipeline. The Glimmer agentic loop is the same idea decomposed into typed roles + an explicit graph substrate, so that:

- Different agents can specialize per node type.
- Decisions are verifiable per the agent protocol.
- The graph survives independently of any specific autoresearch system.
- Multiple autoresearch systems can co-operate on the same graph.

## What this requires from v0.3+

The agentic loop requires schema additions over the current v0.1:

- `concept` node type (v0.3 roadmap)
- `persona` node type (v0.3 roadmap)
- `experiment` node type (v0.3 roadmap) — for Experiment Factory containers
- Cross-cutting edges: `authored-by`, `extends-concept`, `tests-hypothesis` (v0.3)
- Optional: cryptographic signing of agent outputs (v0.5 — federated identity)

This document specifies the operational pattern; the schema additions to fully support it land in v0.3.
