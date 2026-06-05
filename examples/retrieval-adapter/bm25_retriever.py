#!/usr/bin/env python3
"""Stdlib-only reference implementations of the LiteratureRetriever contract.

These exist to prove the contract is satisfiable with ZERO infrastructure — no
vector DB, no embedding model, no torch. A project that wants real semantic
retrieval swaps in a Haystack/agentic-rag backend (see docs/retrieval-adapter.md);
the agentic loop and its tests run identically against either.

  NullRetriever  - returns nothing; for testing the loop's "insufficient evidence"
                   path (the agent must emit confidence: low per the protocol).
  Bm25Retriever  - Okapi BM25 over whitespace-tokenized node text; good enough to
                   demonstrate ranking + multi-source findings deterministically.

Both index `publication`/`standard` node dicts and return Glimmer node-IDs, so
the vector index is a rebuildable cache over the sidecars, never a source of truth.
"""

import math
import re
from collections import Counter

from glimmer.tools.retrieval import Passage, RetrievalResult


def _node_text(node: dict) -> str:
    """The retrievable text for a node: its name plus its free-text description."""
    return f"{node.get('name', '')} {node.get('description', '')}".strip()


def _tokenize(text: str) -> list:
    return re.findall(r"[a-z0-9]+", text.lower())


class NullRetriever:
    """Indexes nothing, retrieves nothing. Satisfies the Protocol structurally."""

    def index(self, nodes):
        pass

    def retrieve(self, query, *, k=8):
        return RetrievalResult(query=query, passages=(), retriever_manifest=self.manifest())

    def manifest(self):
        return {"retriever": "null", "version": "1"}


class Bm25Retriever:
    """Okapi BM25 over node text. Deterministic — same corpus + query → same ranking."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self._docs = {}          # node_id -> {"text": str, "tf": Counter, "len": int}
        self._df = Counter()     # token -> number of docs containing it
        self._avglen = 0.0

    def index(self, nodes):
        # Idempotent rebuild: re-indexing the same nodes reproduces the same state,
        # so the index is a cache that can always be regenerated from the sidecars.
        for node in nodes:
            node_id = node["id"]
            if node_id in self._docs:
                continue
            tokens = _tokenize(_node_text(node))
            tf = Counter(tokens)
            self._docs[node_id] = {"text": _node_text(node), "tf": tf, "len": len(tokens)}
            for term in tf:
                self._df[term] += 1
        n = len(self._docs)
        self._avglen = (sum(d["len"] for d in self._docs.values()) / n) if n else 0.0

    def _idf(self, term: str) -> float:
        n = len(self._docs)
        df = self._df.get(term, 0)
        # BM25 idf with +0.5 smoothing; clamped at 0 so common terms never go negative.
        return max(0.0, math.log((n - df + 0.5) / (df + 0.5) + 1.0))

    def _score(self, query_tokens, doc) -> float:
        score = 0.0
        for term in query_tokens:
            tf = doc["tf"].get(term, 0)
            if not tf:
                continue
            num = tf * (self.k1 + 1)
            den = tf + self.k1 * (1 - self.b + self.b * doc["len"] / (self._avglen or 1))
            score += self._idf(term) * num / den
        return score

    def retrieve(self, query, *, k=8):
        q = _tokenize(query)
        scored = [(nid, self._score(q, d), d["text"]) for nid, d in self._docs.items()]
        scored = [s for s in scored if s[1] > 0]
        # rank by score desc, node_id asc as a stable deterministic tiebreak
        scored.sort(key=lambda s: (-s[1], s[0]))
        passages = tuple(
            Passage(text=text, source_node_id=nid, score=score, retriever_id="bm25")
            for nid, score, text in scored[:k]
        )
        return RetrievalResult(query=query, passages=passages, retriever_manifest=self.manifest())

    def manifest(self):
        return {
            "retriever": "bm25-okapi",
            "version": "1",
            "k1": self.k1,
            "b": self.b,
            "tokenizer": "lowercase-alnum",
            "corpus-size": len(self._docs),
        }
