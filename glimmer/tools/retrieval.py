#!/usr/bin/env python3
"""Retrieval adapter contract + built-in stdlib BM25 retriever.

Glimmer core defines the `LiteratureRetriever` Protocol, the `finding_from_retrieval`
mapping helper, and lightweight zero-heavy-dependency default retrievers
(`Bm25Retriever` and `NullRetriever`). Heavy RAG backends (Haystack/agentic-rag,
LlamaIndex, dense vector stores) remain optional project-side implementations
behind the same Protocol, so the substrate stays dependency-light and the graph
stays file-distributed.

The design rule that keeps retrieval protocol-conformant: a retriever indexes
nodes that ALREADY EXIST in the graph. Retrieval never invents evidence — it only
ranks real Glimmer node IDs, and any index is a rebuildable cache over sidecars.
See docs/retrieval-adapter.md for the full rationale.
"""

from collections import Counter
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Iterable, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class Passage:
    """A retrieved span of text, tagged with the Glimmer node it came from."""

    text: str
    source_node_id: str        # MUST be an existing Glimmer node id
    score: float               # retriever-native; comparable within a retriever, not across
    locator: str = ""          # section/line/char-span within the source, for human drill-down
    retriever_id: str = ""     # which strategy produced it (multi-strategy audit)


@dataclass(frozen=True)
class RetrievalResult:
    """The output of one `retrieve()` call."""

    query: str
    passages: tuple = ()                       # tuple[Passage, ...]
    retriever_manifest: dict = field(default_factory=dict)  # model/params, tokenizer, index sha


@runtime_checkable
class LiteratureRetriever(Protocol):
    """The seam between Glimmer's literature-scout / search tools and any RAG backend.

    Core ships stdlib-only `Bm25Retriever` and `NullRetriever`; heavier semantic
    backends implement the same Protocol outside core without adding ML deps.
    """

    def index(self, nodes: list) -> None:
        """Index node sidecar dicts. Each node's `id` becomes a retrievable
        `source_node_id`. MUST be idempotent on (id, provenance-hash) — the index
        is a rebuildable cache, never authoritative."""

    def retrieve(self, query: str, *, k: int = 8) -> RetrievalResult:
        """Return up to `k` passages, each tagged with its source Glimmer node."""

    def manifest(self) -> dict:
        """Stable description of the retrieval configuration. Embedded verbatim
        into the finding's reasoning-trace so a reviewer can inspect parameters
        and the index fingerprint."""


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _stringify_field(val) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, (list, tuple)):
        return " ".join(_stringify_field(v) for v in val)
    if isinstance(val, dict):
        return " ".join(f"{k} {_stringify_field(v)}" for k, v in val.items())
    return str(val)


def _node_parts(node: dict) -> tuple[str, str, str]:
    """Return (title_text, summary_text, body_text) for weighted BM25 indexing."""
    title_text = " ".join(
        part for part in (
            _stringify_field(node.get("id")),
            _stringify_field(node.get("name")),
            _stringify_field(node.get("title")),
            _stringify_field(node.get("citekey")),
        ) if part
    ).strip()
    summary_text = " ".join(
        part for part in (
            _stringify_field(node.get("statement")),
            _stringify_field(node.get("interpretation")),
            _stringify_field(node.get("description")),
            _stringify_field(node.get("authors")),
            _stringify_field(node.get("venue")),
            _stringify_field(node.get("concept-kind")),
            _stringify_field(node.get("claim-kind")),
            _stringify_field(node.get("ref-kind")),
            _stringify_field(node.get("role")),
        ) if part
    ).strip()
    body_text = str(node.get("body") or node.get("_body") or "").strip()
    return title_text, summary_text, body_text


def _doc_fingerprint(node: dict, title: str, summary: str, body: str) -> str:
    prov = node.get("provenance-hash")
    payload = f"{prov or ''}\0{title}\0{summary}\0{body}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _best_snippet(query_tokens: list[str], title: str, summary: str, body: str, max_chars: int = 240) -> tuple[str, str]:
    """Extract the highest-overlap paragraph/section snippet and a human locator."""
    qset = set(query_tokens)
    best_score = -1
    best_text = ""
    best_locator = "frontmatter"

    if summary:
        s_hits = sum(1 for t in _tokenize(summary) if t in qset)
        if s_hits > best_score:
            best_score = s_hits
            best_text = re.sub(r"\s+", " ", summary).strip()
            best_locator = "frontmatter"

    if body:
        lines = body.splitlines()
        heading = ""
        para_lines: list[tuple[int, str]] = []

        def flush():
            nonlocal best_score, best_text, best_locator
            if not para_lines:
                return
            start_ln = para_lines[0][0]
            end_ln = para_lines[-1][0]
            raw = " ".join(ln.strip() for _, ln in para_lines).strip()
            if not raw:
                return
            hits = sum(1 for t in _tokenize(raw) if t in qset)
            if hits > best_score:
                best_score = hits
                best_text = re.sub(r"\s+", " ", raw)
                loc = f"L{start_ln}-L{end_ln}"
                best_locator = f"{heading} ({loc})" if heading else loc

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                flush()
                para_lines = []
                heading = stripped.lstrip("#").strip()
            elif not stripped:
                flush()
                para_lines = []
            else:
                para_lines.append((idx, line))
        flush()

    if not best_text:
        best_text = (summary or title or body).strip()
        best_text = re.sub(r"\s+", " ", best_text)
    if len(best_text) > max_chars:
        best_text = best_text[: max_chars - 1].rstrip() + "…"
    return best_text, best_locator


class NullRetriever:
    """Indexes nothing, retrieves nothing. Satisfies the LiteratureRetriever Protocol."""

    def index(self, nodes: Iterable[dict]) -> None:
        pass

    def retrieve(self, query: str, *, k: int = 8) -> RetrievalResult:
        return RetrievalResult(query=query, passages=(), retriever_manifest=self.manifest())

    def manifest(self) -> dict:
        return {"retriever": "null", "version": "1"}


class Bm25Retriever:
    """Stdlib-only Okapi BM25 over node metadata + Markdown bodies.

    Deterministic (same corpus + query -> same ranking, tie-broken by node id)
    and idempotent on (id, provenance-hash).
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._docs: dict[str, dict] = {}
        self._df: Counter = Counter()
        self._avglen: float = 0.0

    def _rebuild_stats(self) -> None:
        df: Counter = Counter()
        total_len = 0
        for doc in self._docs.values():
            total_len += doc["len"]
            for term in doc["tf"]:
                df[term] += 1
        self._df = df
        n = len(self._docs)
        self._avglen = (total_len / n) if n else 0.0

    def index(self, nodes: Iterable[dict]) -> None:
        changed = False
        for node in nodes:
            node_id = node["id"]
            title, summary, body = _node_parts(node)
            fp = _doc_fingerprint(node, title, summary, body)
            existing = self._docs.get(node_id)
            if existing and existing["fp"] == fp:
                continue
            # Weighted token bag: title/id x3, summary/metadata x2, body x1
            tokens = (
                _tokenize(title) * 3
                + _tokenize(summary) * 2
                + _tokenize(body)
            )
            tf = Counter(tokens)
            self._docs[node_id] = {
                "fp": fp,
                "title": title,
                "summary": summary,
                "body": body,
                "tf": tf,
                "len": len(tokens),
            }
            changed = True
        if changed:
            self._rebuild_stats()

    def _idf(self, term: str) -> float:
        n = len(self._docs)
        df = self._df.get(term, 0)
        return max(0.0, math.log((n - df + 0.5) / (df + 0.5) + 1.0))

    def _score(self, query_tokens: list[str], doc: dict) -> float:
        if doc["len"] == 0:
            return 0.0
        score = 0.0
        avglen = self._avglen or 1.0
        for term in query_tokens:
            tf = doc["tf"].get(term, 0)
            if not tf:
                continue
            num = tf * (self.k1 + 1.0)
            den = tf + self.k1 * (1.0 - self.b + self.b * doc["len"] / avglen)
            score += self._idf(term) * (num / den)
        return score

    def retrieve(self, query: str, *, k: int = 8) -> RetrievalResult:
        q = _tokenize(query)
        if not q or k <= 0:
            return RetrievalResult(query=query, passages=(), retriever_manifest=self.manifest())
        scored = []
        for nid, doc in self._docs.items():
            sc = self._score(q, doc)
            if sc > 0:
                scored.append((nid, sc, doc))
        scored.sort(key=lambda s: (-s[1], s[0]))
        passages = []
        for nid, sc, doc in scored[:k]:
            snippet, locator = _best_snippet(q, doc["title"], doc["summary"], doc["body"])
            passages.append(
                Passage(
                    text=snippet,
                    source_node_id=nid,
                    score=round(sc, 6),
                    locator=locator,
                    retriever_id="bm25-okapi",
                )
            )
        return RetrievalResult(
            query=query,
            passages=tuple(passages),
            retriever_manifest=self.manifest(),
        )

    def _index_sha(self) -> str:
        payload = json.dumps(
            [[nid, d["fp"]] for nid, d in sorted(self._docs.items())],
            separators=(",", ":"),
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(payload).hexdigest()

    def manifest(self) -> dict:
        return {
            "retriever": "bm25-okapi",
            "version": "2",
            "k1": self.k1,
            "b": self.b,
            "tokenizer": "lowercase-alnum",
            "field-weights": {"title": 3, "summary": 2, "body": 1},
            "corpus-size": len(self._docs),
            "index-sha": self._index_sha(),
        }


def load_rokb_documents(rokb_path: Path, *, types: Optional[set[str]] = None) -> list[dict]:
    """Load sidecars from an RO-KB directory as dicts suitable for `LiteratureRetriever.index`."""
    from glimmer.tools.validate import iter_sidecar_paths, read_sidecar

    rokb_path = Path(rokb_path)
    docs = []
    for path in iter_sidecar_paths(rokb_path):
        try:
            fm, body = read_sidecar(path)
        except ValueError:
            continue
        if not fm.get("id"):
            continue
        if types and fm.get("type") not in types:
            continue
        doc = dict(fm)
        doc["body"] = body
        doc["_path"] = str(path.relative_to(rokb_path))
        docs.append(doc)
    return docs


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
