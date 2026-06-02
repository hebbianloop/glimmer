#!/usr/bin/env python3
"""Retrieval adapter contract for the literature-scout role.

Glimmer core defines ONLY the contract (a Protocol) plus a helper that maps a
retrieval result onto a protocol-conformant `finding`. It deliberately pulls in
NO heavy dependencies — no vector DB, no torch, no embedding stack. Concrete
retrievers (Haystack/agentic-rag, LlamaIndex, plain BM25, ...) live in project
forks behind this seam, so the substrate never imports an ML toolchain and the
graph stays file-distributed.

The design rule that keeps this protocol-conformant: a retriever indexes
`publication`/`standard` nodes that ALREADY EXIST in the graph. Retrieval never
invents evidence — it only ranks node-IDs that are already first-class citizens.
So `nodes-accessed` in the emitted trace is grounded in real Glimmer IDs, and the
vector index is a rebuildable cache over the sidecars, not a competing source of
truth. See docs/retrieval-adapter.md for the full rationale.
"""

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class Passage:
    """A retrieved span of text, tagged with the Glimmer node it came from."""

    text: str
    source_node_id: str        # MUST be an existing publication/standard node id
    score: float               # retriever-native; comparable within a retriever, not across
    locator: str = ""          # page/section/char-span within the source, for human drill-down
    retriever_id: str = ""     # which strategy produced it (multi-strategy audit)


@dataclass(frozen=True)
class RetrievalResult:
    """The output of one `retrieve()` call."""

    query: str
    passages: tuple = ()                       # tuple[Passage, ...]
    retriever_manifest: dict = field(default_factory=dict)  # embedding+ver, chunking, reranker, index sha


@runtime_checkable
class LiteratureRetriever(Protocol):
    """The seam between Glimmer's literature-scout role and any RAG backend.

    Implementations live OUTSIDE Glimmer core. Core only defines this contract
    and `finding_from_retrieval`, so the substrate stays dep-free and never
    imports torch. A 15-line BM25 or null implementation satisfies the same
    Protocol, which makes the agentic loop testable without standing up infra.
    """

    def index(self, nodes: list) -> None:
        """Index publication/standard node sidecars (each a dict). Each node's
        `id` becomes a retrievable `source_node_id`. MUST be idempotent on
        (id, provenance-hash) — the index is a rebuildable cache, never
        authoritative."""

    def retrieve(self, query: str, *, k: int = 8) -> RetrievalResult:
        """Return up to `k` passages, each tagged with its source Glimmer node."""

    def manifest(self) -> dict:
        """Stable description of the retrieval configuration. Embedded verbatim
        into the finding's reasoning-trace so a reviewer can see the embedding
        model, chunking strategy, reranker, and index version."""


def finding_from_retrieval(
    *,
    finding_id: str,
    interpretation: str,
    result: RetrievalResult,
    model_identifier: str,
    timestamp: str,
    concept_id: Optional[str] = None,
    confidence: str = "medium",
) -> dict:
    """Build a protocol-conformant `finding` sidecar dict from a RetrievalResult.

    Honest mapping of RAG retrieval onto Glimmer's verifiability contract:

      provenance-mode: stochastic   - retrieval is non-deterministic by construction
      nodes-accessed = the distinct source nodes the passages came from (real IDs)
      metrics-cited  = retriever scores, explicitly marked non-load-bearing
      based-on edges = one per distinct source node

    The `retriever_manifest` is embedded so a re-run with the same config is
    "reproducible-modulo-index" — the honest analogue of SHA re-execution for the
    stochastic regime. The result satisfies docs/agent-protocol.md: `finding`
    supports `provenance-mode: stochastic`, `reasoning-trace`, and `based-on`.
    When a `concept_id` is given, an `addresses-concept` edge links the finding to
    the research question it bears on (the `concept` node type shipped in v0.3).
    """
    sources = sorted({p.source_node_id for p in result.passages})
    edges = [{"type": "based-on", "target": s} for s in sources]
    # `based-on` and `reasoning-trace.nodes-accessed` are the same list of IDs but
    # MUST be distinct objects, else yaml.dump emits an anchor/alias (&id/*id) that
    # is valid YAML yet inconsistent with every other sidecar in the repo.
    if concept_id:  # closes the loop back to the research question (concept node)
        edges.append({"type": "addresses-concept", "target": concept_id})

    return {
        "id": finding_id,
        "type": "finding",
        "interpretation": interpretation,
        "based-on": list(sources),
        "produced-by-agent": model_identifier,
        "provenance-mode": "stochastic",
        "confidence": confidence,
        "reasoning-trace": {
            "nodes-accessed": list(sources),
            "metrics-cited": {
                "retrieval-scores": {
                    p.source_node_id: round(p.score, 4) for p in result.passages
                },
                "_note": "retriever-native scores; comparable within a retriever_id, not across",
            },
            "evidence-summary": (
                f"Retrieved {len(result.passages)} passages over {len(sources)} "
                f"source nodes for query {result.query!r}. "
                + " ".join(f"[[{s}]]" for s in sources)
            ),
            "model-identifier": model_identifier,
            "timestamp": timestamp,
            "retriever-manifest": result.retriever_manifest,
        },
        "edges": edges,
    }
