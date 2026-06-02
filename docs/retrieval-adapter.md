# The Retrieval Adapter

> How a Glimmer project plugs a RAG backend (agentic-rag, Haystack, LlamaIndex, BM25, …) into the **literature-scout** role without dragging a vector-DB / embedding stack into the substrate, and without breaking the agent protocol's verifiability contract.

## Why an adapter and not a framework

A retrieval-augmented generation engine solves a real problem Glimmer does not: semantic search over *unstructured* text (papers, PDFs, abstracts) so the literature-scout and synthesis agents can find relevant prior work. Glimmer's own retrieval model is **graph navigation over typed edges** — exact, deterministic, ID-addressed. RAG is **approximate retrieval over embeddings** — fuzzy, non-deterministic, score-ranked. They are complementary, not interchangeable.

Adopting a full RAG framework wholesale fights two of Glimmer's invariants:

1. **Centralized stores vs. file-distributed graph.** Frameworks like agentic-rag persist provenance in a graph DB (Neo4j) and content in vector stores (Chroma/Qdrant). That contradicts Core Principle #1 — *the graph survives `git clone` / `datalad export` / `rsync`*. Two provenance systems would have to be reconciled and the graph would stop being self-describing.
2. **Approximate retrieval vs. exact-SHA verification.** A RAG "result" is a similarity hit plus a reranker score — not a content-hashed node with edges. It can't satisfy `reasoning-trace.nodes-accessed` as written, because it never accessed Glimmer nodes; it accessed a vector index.

The adapter resolves both by inverting the relationship: **the retriever indexes nodes that already exist in the graph, and returns Glimmer node-IDs.** Retrieval never invents evidence — it only *ranks `publication`/`standard` nodes that are already first-class citizens*. The vector index becomes a **rebuildable cache over the sidecars**, not a competing source of truth.

## The contract

Defined in [`glimmer/tools/retrieval.py`](../glimmer/tools/retrieval.py). Core ships only the Protocol plus a trace helper — **zero new dependencies**. Concrete retrievers live in project forks.

```python
@runtime_checkable
class LiteratureRetriever(Protocol):
    def index(self, nodes: list) -> None: ...
    def retrieve(self, query: str, *, k: int = 8) -> RetrievalResult: ...
    def manifest(self) -> dict: ...
```

- `Passage` — a retrieved span carrying its `source_node_id` (a real Glimmer node), `score`, optional `locator` (page/section for human drill-down), and `retriever_id` (which strategy found it).
- `RetrievalResult` — the query, its passages, and a `retriever_manifest` (embedding model + version, chunking, reranker, index SHA).
- `index()` MUST be idempotent on `(id, provenance-hash)` so the cache can always be rebuilt from sidecars.

## Emitting a protocol-conformant finding

`finding_from_retrieval(...)` maps a `RetrievalResult` onto an agent-protocol-conformant `finding`:

| Protocol requirement | How retrieval satisfies it |
|---|---|
| `provenance-mode` | `stochastic` — retrieval is non-deterministic by construction; never faked as `deterministic`. |
| `nodes-accessed` | The distinct `source_node_id`s the passages came from — all real, all in the graph. |
| `metrics-cited` | The per-source retriever scores, explicitly noted as non-load-bearing across retrievers. |
| `based-on` edges | One per distinct source node; plus an optional `addresses-concept` edge closing the loop to the hypothesis (the `concept` node type, shipped in v0.3). |
| Reproducibility | The `retriever-manifest` is embedded, so a same-config re-run is *reproducible-modulo-index* — the honest analogue of SHA re-execution for the stochastic regime. |

No schema change is required: `finding` supports `provenance-mode: stochastic`, `reasoning-trace`, and `based-on`, and `addresses-concept` resolves to a `concept` node (shipped in v0.3) when a `concept_id` is supplied.

## Where it slots into the agentic loop

Extends the **literature scout** role from [`agentic-loop.md`](agentic-loop.md):

```
1. Walk PubMed / OpenAlex / Semantic Scholar  →  emit `publication` nodes   (unchanged; graph stays source of truth)
2. retriever.index(publication_nodes)         →  build the cache over those nodes
3. for each hypothesis query:
       result  = retriever.retrieve(query, k=8)
       finding = finding_from_retrieval(..., result, concept_id=hypothesis_concept)
       write_node(finding)                     →  provenance-mode: stochastic, traceable to real pub nodes
4. Synthesis agent reads those findings        →  drills into any [[publication-node]] the trace cites
```

The retriever is a *consumer* of the graph (it indexes existing publication nodes) and a *producer* of findings that point back into the graph. It is never the authority on what evidence exists.

## A fork-side backend (example, NOT in core)

All the weight is quarantined here. The framework — whatever it is — is reduced to "a thing behind `retrieve()`". A Haystack/agentic-rag binding is roughly:

```python
# myproject/retrievers/agentic_rag_backend.py   (imports torch etc. — fine, it's a fork)
from glimmer.tools.retrieval import Passage, RetrievalResult   # structural match → satisfies the Protocol

class AgenticRagRetriever:
    def __init__(self, haystack_pipeline, embedding_model, reranker):
        self._pipe, self._emb, self._rr = haystack_pipeline, embedding_model, reranker

    def index(self, nodes):
        for n in nodes:                              # n = a publication-node sidecar dict
            text = load_source_text(n)               # fetch the PDF/abstract the node points at
            self._pipe.write(doc_id=n["id"], text=text, meta={"glimmer-node": n["id"]})

    def retrieve(self, query, *, k=8):
        hits = self._pipe.run(query, top_k=k)        # multi-strategy + rerank = agentic-rag's actual strength
        return RetrievalResult(
            query=query,
            passages=tuple(Passage(text=h.content, source_node_id=h.meta["glimmer-node"],
                                   score=h.score, retriever_id=h.meta.get("branch", ""))
                           for h in hits),
            retriever_manifest=self.manifest(),
        )

    def manifest(self):
        return {"embedding": self._emb, "reranker": self._rr,
                "strategies": self._pipe.branch_configs(), "index-sha": self._pipe.index_sha()}
```

## What to borrow from agentic-rag, specifically

agentic-rag's worthwhile idea is **multi-strategy retrieval + reranking**: index the same corpus under several chunking/embedding strategies, retrieve from all in parallel, and let a cross-encoder reranker pick the best passages. That belongs *inside* a backend's `retrieve()` when recall matters. What to leave behind: its Neo4j-centric provenance (conflicts with Principle #1), its vector-store coupling, and the unrelated infra deps (`web3`, `boto3`) it carries for its own product context.

## Invariants the adapter preserves

| Concern | Resolution |
|---|---|
| Centralized store vs. file-distributed graph | Index is a rebuildable cache keyed on `(id, provenance-hash)`; delete and re-`index()` from sidecars. Graph still survives `git clone`. |
| Approximate retrieval vs. exact-SHA verification | `provenance-mode: stochastic` + embedded `retriever-manifest` = reproducible-modulo-index. Not faked as deterministic. |
| `nodes-accessed` can't cite a vector index | It cites the `publication` nodes the passages came from — all real, all in the graph. |
| Dependency footprint | Core gains zero deps. All weight lives in the fork's backend module. |
| Testability | A null or BM25 retriever satisfies the same Protocol, so the agentic loop is testable without infra. |
