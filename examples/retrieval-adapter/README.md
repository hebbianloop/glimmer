# Retrieval adapter — worked example

Exercises the `LiteratureRetriever` contract (`glimmer/tools/retrieval.py`) with a
**stdlib-only** BM25 retriever — no vector DB, no embedding model, no torch. It
demonstrates the literature-scout loop step from [`docs/agentic-loop.md`](../../docs/agentic-loop.md):
index existing `publication` nodes → retrieve against a hypothesis query → emit a
protocol-conformant `finding`.

See [`docs/retrieval-adapter.md`](../../docs/retrieval-adapter.md) for the design
rationale and a fork-side agentic-rag/Haystack backend example.

## Run it

```bash
cd examples/retrieval-adapter
python demo.py                                # builds rokb/ (gitignored)
python ../../glimmer/tools/validate.py rokb/  # 0 errors
```

Expected: BM25 ranks the two on-topic publications above the unrelated control
(which scores 0 and is excluded), and the emitted `finding` cites only the
retrieved sources, with `provenance-mode: stochastic` and a `retriever-manifest`
in its `reasoning-trace`.

## Files

- `bm25_retriever.py` — `NullRetriever` + `Bm25Retriever`, two reference
  implementations of the Protocol. `NullRetriever` exercises the protocol's
  "insufficient evidence" path; `Bm25Retriever` is a deterministic Okapi BM25.
- `demo.py` — indexes three `publication` nodes, retrieves, emits a `finding`,
  writes a Glimmer graph, and points you at the validator.

## Swapping in a real backend

Replace `Bm25Retriever` with any object satisfying the `LiteratureRetriever`
Protocol (a Haystack/agentic-rag wrapper, LlamaIndex, etc.). Everything else —
`finding_from_retrieval`, the graph emission, validation — is unchanged. That is
the point of the seam: the substrate never imports the retrieval stack.
