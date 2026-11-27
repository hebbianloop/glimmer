#!/usr/bin/env python3
"""Live query, search, summary, and multi-hop traversal for Glimmer RO-KBs.

Zero heavy dependencies (Python stdlib + PyYAML). Operates directly over live
RO-KB Markdown/JSON sidecars — using enriched `_glimmer-index.json` entries as a
fast path for metadata-only queries — OR over a compiled workspace `graph.json`
via `--graph`.

Metadata-only by default (`--no-body`) so star hubs like `program-*` never blow
up an agent's context window; pass `--include-body` (or `--body-chars N`) when
full prose is needed.
"""

from __future__ import annotations

import argparse
from collections import Counter, deque
import json
from pathlib import Path
import re
import sys
from typing import Any, Optional

from glimmer.tools.retrieval import Bm25Retriever, finding_from_retrieval
from glimmer.tools.validate import iter_sidecar_paths, read_sidecar


STATUS_KEYS = ("evidence-status", "design-status", "status", "pub-status")
SUBTYPE_KEYS = ("concept-kind", "ref-kind", "program-kind", "org-kind", "persona-kind", "instrument-kind", "standard-class")
SUMMARY_KEYS = ("statement", "interpretation", "description")
STAR_HUB_THRESHOLD = 10


def extract_summary(fm: dict, body: str = "", max_chars: int = 180) -> str:
    """Produce a compact single-line summary from frontmatter or lead body prose."""
    for key in SUMMARY_KEYS:
        val = fm.get(key)
        if isinstance(val, str) and val.strip():
            text = re.sub(r"\s+", " ", val).strip()
            return text if len(text) <= max_chars else text[: max_chars - 1].rstrip() + "…"
    for line in (body or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("<!--"):
            continue
        text = re.sub(r"\s+", " ", s)
        return text if len(text) <= max_chars else text[: max_chars - 1].rstrip() + "…"
    return ""


def extract_status(fm: dict) -> Optional[str]:
    for key in ("status", "pub-status", "design-status", "evidence-status"):
        val = fm.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return None


def extract_subtype(fm: dict) -> Optional[str]:
    for key in SUBTYPE_KEYS:
        val = fm.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return None


def _normalize_edges(edges: Any) -> list[dict]:
    out = []
    for e in (edges or []):
        if isinstance(e, dict) and e.get("type") and e.get("target"):
            out.append({"type": str(e["type"]), "target": str(e["target"])})
    return out


class LoadedGraph:
    """In-memory view of a Glimmer RO-KB or compiled workspace graph.json."""

    def __init__(
        self,
        *,
        source: str,
        nodes: dict[str, dict],
        edges: list[dict],
        meta: dict,
        enriched_index: bool = False,
        rokb_path: Optional[Path] = None,
    ):
        self.source = source
        self.nodes = nodes
        self.edges = edges
        self.meta = meta
        self.enriched_index = enriched_index
        self.rokb_path = rokb_path
        self.outgoing: dict[str, list[dict]] = {nid: [] for nid in nodes}
        self.incoming: dict[str, list[dict]] = {nid: [] for nid in nodes}
        for e in edges:
            src, tgt = e["source"], e["target"]
            if src in self.outgoing:
                self.outgoing[src].append(e)
            if tgt in self.incoming:
                self.incoming[tgt].append(e)

    def degree(self, node_id: str) -> int:
        return len(self.outgoing.get(node_id, ())) + len(self.incoming.get(node_id, ()))

    def ensure_sidecar(self, node_id: str) -> dict:
        """Lazily load full frontmatter + body for a node if it came from index fast-path."""
        node = self.nodes[node_id]
        if node.get("_full_loaded") or not self.rokb_path or not node.get("path"):
            return node
        path = self.rokb_path / node["path"]
        if not path.is_file():
            node["_full_loaded"] = True
            return node
        fm, body = read_sidecar(path)
        node["fields"] = fm
        node["body"] = body
        node["name"] = fm.get("name") or node.get("name") or node_id
        node["status"] = extract_status(fm) or node.get("status")
        node["subtype"] = extract_subtype(fm) or node.get("subtype")
        node["role"] = fm.get("role") or node.get("role")
        node["claim-kind"] = fm.get("claim-kind") or node.get("claim-kind")
        node["modified"] = str(fm["modified"]) if fm.get("modified") is not None else node.get("modified")
        node["provenance-hash"] = fm.get("provenance-hash") or node.get("provenance-hash")
        node["summary"] = extract_summary(fm, body) or node.get("summary") or ""
        node["_full_loaded"] = True
        return node


def _is_index_enriched(index: dict) -> bool:
    rows = index.get("nodes") or []
    if not rows:
        return True
    return all(isinstance(r, dict) and "name" in r and "edges" in r for r in rows)


def load_graph(target: Path, *, from_graph_json: bool = False, need_full: bool = False) -> LoadedGraph:
    """Load a live RO-KB directory or a compiled `graph.json`."""
    target = Path(target)
    if from_graph_json or (target.is_file() and target.suffix == ".json" and target.name != "_glimmer-index.json"):
        data = json.loads(target.read_text(encoding="utf-8"))
        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        raw_edges = data.get("edges") or []
        by_source: dict[str, list[dict]] = {}
        for e in raw_edges:
            rel = e.get("rel") or e.get("type")
            src, tgt = e.get("source"), e.get("target")
            if src and tgt and rel:
                norm = {"source": src, "type": rel, "target": tgt}
                edges.append(norm)
                by_source.setdefault(src, []).append({"type": rel, "target": tgt})
        for n in data.get("nodes") or []:
            nid = n["id"]
            fields = dict(n.get("fields") or {})
            fields.setdefault("id", nid)
            fields.setdefault("type", n.get("type"))
            fields.setdefault("name", n.get("name"))
            body = n.get("body") or ""
            nodes[nid] = {
                "id": nid,
                "type": n.get("type", ""),
                "path": n.get("path", ""),
                "name": n.get("name", nid),
                "status": extract_status(fields),
                "subtype": extract_subtype(fields),
                "claim-kind": fields.get("claim-kind"),
                "role": fields.get("role"),
                "modified": str(fields["modified"]) if fields.get("modified") is not None else None,
                "provenance-hash": fields.get("provenance-hash"),
                "summary": extract_summary(fields, body),
                "edges": by_source.get(nid, []),
                "fields": fields,
                "body": body,
                "_full_loaded": True,
            }
        proj = data.get("project") or {}
        meta = {
            "schema": (proj.get("glimmer") or {}).get("schema_version") or data.get("schema") or "graph.json",
            "dataset-name": proj.get("id") or proj.get("title") or target.stem,
            "default-domain": (proj.get("glimmer") or {}).get("profile"),
            "root-node": proj.get("root_node"),
            "entrypoints": proj.get("entrypoints") or [],
            "generated-at": None,
        }
        return LoadedGraph(source=str(target), nodes=nodes, edges=edges, meta=meta, enriched_index=True)

    rokb = target.parent if target.name == "_glimmer-index.json" else target
    index_path = rokb / "_glimmer-index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else {}
    enriched = _is_index_enriched(index)

    nodes = {}
    edges = []

    if index and enriched and not need_full:
        for row in index.get("nodes") or []:
            nid = row["id"]
            row_edges = _normalize_edges(row.get("edges"))
            fields = {
                "id": nid,
                "type": row.get("type", ""),
                "name": row.get("name", nid),
            }
            for k in ("status", "pub-status", "design-status", "evidence-status", "subtype", "concept-kind", "claim-kind", "role", "modified", "provenance-hash", "summary"):
                if k in row and row[k] is not None:
                    fields[k] = row[k]
            nodes[nid] = {
                "id": nid,
                "type": row.get("type", ""),
                "path": row.get("path", ""),
                "name": row.get("name", nid),
                "status": row.get("status"),
                "subtype": row.get("subtype"),
                "claim-kind": row.get("claim-kind"),
                "role": row.get("role"),
                "modified": row.get("modified"),
                "provenance-hash": row.get("provenance-hash"),
                "summary": row.get("summary") or "",
                "edges": row_edges,
                "fields": fields,
                "body": "",
                "_full_loaded": False,
            }
            for e in row_edges:
                edges.append({"source": nid, "type": e["type"], "target": e["target"]})
    else:
        indexed_paths = {row["id"]: row.get("path", "") for row in (index.get("nodes") or []) if isinstance(row, dict) and row.get("id")}
        for path in iter_sidecar_paths(rokb):
            try:
                fm, body = read_sidecar(path)
            except ValueError:
                continue
            nid = fm.get("id")
            if not nid:
                continue
            rel_path = str(path.relative_to(rokb))
            row_edges = _normalize_edges(fm.get("edges"))
            nodes[nid] = {
                "id": nid,
                "type": fm.get("type", ""),
                "path": indexed_paths.get(nid, rel_path),
                "name": fm.get("name", nid),
                "status": extract_status(fm),
                "subtype": extract_subtype(fm),
                "claim-kind": fm.get("claim-kind"),
                "role": fm.get("role"),
                "modified": str(fm["modified"]) if fm.get("modified") is not None else None,
                "provenance-hash": fm.get("provenance-hash"),
                "summary": extract_summary(fm, body),
                "edges": row_edges,
                "fields": fm,
                "body": body,
                "_full_loaded": True,
            }
            for e in row_edges:
                edges.append({"source": nid, "type": e["type"], "target": e["target"]})

    meta = {
        "schema": index.get("schema", "?"),
        "dataset-name": index.get("dataset-name") or rokb.name,
        "default-domain": index.get("default-domain"),
        "root-node": index.get("root-node"),
        "entrypoints": index.get("entrypoints") or [],
        "generated-at": index.get("generated-at"),
    }
    return LoadedGraph(
        source=str(rokb),
        nodes=nodes,
        edges=edges,
        meta=meta,
        enriched_index=enriched,
        rokb_path=rokb,
    )


def _format_node_record(g: LoadedGraph, nid: str, *, include_body: bool = False, body_chars: int = 0) -> dict:
    n = g.ensure_sidecar(nid) if (include_body or body_chars > 0) else g.nodes[nid]
    rec: dict[str, Any] = {
        "id": n["id"],
        "type": n["type"],
        "name": n["name"],
        "path": n["path"],
    }
    for k in ("status", "subtype", "claim-kind", "role", "modified"):
        if n.get(k) is not None:
            rec[k] = n[k]
    if n.get("summary"):
        rec["summary"] = n["summary"]
    rec["degree"] = {"in": len(g.incoming.get(nid, ())), "out": len(g.outgoing.get(nid, ()))}
    rec["edges"] = n["edges"]
    if include_body or body_chars > 0:
        body = n.get("body") or ""
        if body_chars > 0 and len(body) > body_chars:
            body = body[: body_chars - 1].rstrip() + "…"
        rec["body"] = body
    return rec


def _match_field_expr(node: dict, expr: str) -> bool:
    """Evaluate `--field` expressions: `key=value`, `key~=substr`, or `key?` (exists)."""
    fields = node.get("fields") or {}
    if expr.endswith("?") and "=" not in expr:
        key = expr[:-1].strip()
        val = fields.get(key, node.get(key))
        return val is not None and val != "" and val != []
    if "~=" in expr:
        key, want = expr.split("~=", 1)
        key, want_l = key.strip(), want.strip().lower()
        val = fields.get(key, node.get(key))
        if val is None:
            return False
        if isinstance(val, list):
            return any(want_l in str(item).lower() for item in val)
        return want_l in str(val).lower()
    if "=" in expr:
        key, want = expr.split("=", 1)
        key, want_l = key.strip(), want.strip().lower()
        val = fields.get(key, node.get(key))
        if val is None:
            return False
        if isinstance(val, bool):
            return str(val).lower() == want_l
        if isinstance(val, list):
            return any(str(item).lower() == want_l for item in val)
        return str(val).lower() == want_l
    raise ValueError(f"Invalid --field expression {expr!r}; expected key=value, key~=substr, or key?")


def summarize_rokb(target: Path, *, from_graph_json: bool = False) -> dict:
    g = load_graph(target, from_graph_json=from_graph_json, need_full=False)
    by_type = Counter(n["type"] for n in g.nodes.values())
    by_status = Counter((n.get("status") or "unspecified") for n in g.nodes.values())
    by_pub_role = Counter(
        (n.get("role") or "unannotated") for n in g.nodes.values() if n["type"] == "publication"
    )
    edge_types = Counter(e["type"] for e in g.edges)
    hubs = sorted(
        (
            {
                "id": nid,
                "type": n["type"],
                "name": n["name"],
                "in": len(g.incoming.get(nid, ())),
                "out": len(g.outgoing.get(nid, ())),
                "degree": g.degree(nid),
            }
            for nid, n in g.nodes.items()
        ),
        key=lambda x: (-x["degree"], x["id"]),
    )
    star_hubs = [h for h in hubs if h["degree"] >= STAR_HUB_THRESHOLD]
    mod_dates = sorted(str(n["modified"]) for n in g.nodes.values() if n.get("modified"))
    return {
        "source": g.source,
        "dataset-name": g.meta["dataset-name"],
        "schema": g.meta["schema"],
        "default-domain": g.meta["default-domain"],
        "enriched-index": g.enriched_index,
        "generated-at": g.meta["generated-at"],
        "root-node": g.meta["root-node"],
        "entrypoints": g.meta["entrypoints"],
        "node-count": len(g.nodes),
        "edge-count": len(g.edges),
        "by-type": dict(sorted(by_type.items())),
        "by-status": dict(sorted(by_status.items())),
        "publication-roles": dict(sorted(by_pub_role.items())),
        "top-edge-types": dict(edge_types.most_common(12)),
        "top-hubs": hubs[:8],
        "star-hubs": [h["id"] for h in star_hubs],
        "modified-range": {"oldest": mod_dates[0], "newest": mod_dates[-1]} if mod_dates else None,
    }


def query_nodes(
    target: Path,
    *,
    from_graph_json: bool = False,
    node_types: Optional[list[str]] = None,
    field_exprs: Optional[list[str]] = None,
    rel: Optional[str] = None,
    direction: str = "both",
    source_id: Optional[str] = None,
    target_id: Optional[str] = None,
    limit: int = 50,
    include_body: bool = False,
    body_chars: int = 0,
) -> dict:
    index_known_keys = {"id", "type", "name", "status", "subtype", "claim-kind", "role", "modified", "provenance-hash", "summary"}
    need_full = bool(include_body or body_chars > 0)
    if field_exprs:
        for expr in field_exprs:
            k = re.split(r"~=|=", expr, maxsplit=1)[0].rstrip("?").strip()
            if k not in index_known_keys:
                need_full = True
                break

    g = load_graph(target, from_graph_json=from_graph_json, need_full=need_full)
    allowed_types: set[str] = set()
    for t in (node_types or []):
        for part in t.split(","):
            if part.strip():
                allowed_types.add(part.strip())

    matched_ids = []
    for nid in sorted(g.nodes):
        node = g.nodes[nid]
        if allowed_types and node["type"] not in allowed_types:
            continue
        if field_exprs and not all(_match_field_expr(node, expr) for expr in field_exprs):
            continue
        if rel or source_id or target_id:
            edges_to_check = []
            if direction in ("out", "both"):
                edges_to_check.extend(g.outgoing.get(nid, ()))
            if direction in ("in", "both"):
                edges_to_check.extend(g.incoming.get(nid, ()))
            ok = False
            for e in edges_to_check:
                if rel and e["type"] != rel:
                    continue
                if source_id and e["source"] != source_id:
                    continue
                if target_id and e["target"] != target_id:
                    continue
                ok = True
                break
            if not ok:
                continue
        matched_ids.append(nid)

    total = len(matched_ids)
    sliced = matched_ids[:limit] if limit and limit > 0 else matched_ids
    results = [_format_node_record(g, nid, include_body=include_body, body_chars=body_chars) for nid in sliced]
    return {
        "source": g.source,
        "total": total,
        "returned": len(results),
        "truncated": total > len(results),
        "include-body": bool(include_body or body_chars > 0),
        "nodes": results,
    }


def traverse_neighbors(
    target: Path,
    node_id: str,
    *,
    from_graph_json: bool = False,
    hops: int = 1,
    rel: Optional[str] = None,
    direction: str = "both",
    limit: int = 50,
    include_body: bool = False,
    body_chars: int = 0,
) -> dict:
    if hops < 1:
        raise ValueError("--hops must be >= 1")
    g = load_graph(target, from_graph_json=from_graph_json, need_full=bool(include_body or body_chars > 0))
    if node_id not in g.nodes:
        raise KeyError(f"Node `{node_id}` not found in {g.source}")

    rel_filter = {r.strip() for r in rel.split(",") if r.strip()} if rel else None
    visited: dict[str, int] = {node_id: 0}
    queue = deque([(node_id, 0)])
    traversed_edges: list[dict] = []
    seen_edge_keys: set[tuple[str, str, str]] = set()

    while queue:
        cur, dist = queue.popleft()
        if dist >= hops:
            continue
        candidates = []
        if direction in ("out", "both"):
            for e in g.outgoing.get(cur, ()):
                candidates.append((e, e["target"]))
        if direction in ("in", "both"):
            for e in g.incoming.get(cur, ()):
                candidates.append((e, e["source"]))
        for e, other in candidates:
            if rel_filter and e["type"] not in rel_filter:
                continue
            ek = (e["source"], e["type"], e["target"])
            if ek not in seen_edge_keys:
                seen_edge_keys.add(ek)
                traversed_edges.append({"source": e["source"], "type": e["type"], "target": e["target"], "hop": dist + 1})
            if other in g.nodes and other not in visited:
                visited[other] = dist + 1
                queue.append((other, dist + 1))

    neighbor_ids = [nid for nid, _ in sorted(visited.items(), key=lambda kv: (kv[1], kv[0])) if nid != node_id]
    total_neighbors = len(neighbor_ids)
    kept_neighbors = neighbor_ids[:limit] if limit and limit > 0 else neighbor_ids
    kept_set = {node_id} | set(kept_neighbors)
    kept_edges = [e for e in traversed_edges if e["source"] in kept_set and e["target"] in kept_set]

    center = _format_node_record(g, node_id, include_body=include_body, body_chars=body_chars)
    neighbors = []
    for nid in kept_neighbors:
        rec = _format_node_record(g, nid, include_body=include_body, body_chars=body_chars)
        rec["hop"] = visited[nid]
        neighbors.append(rec)

    return {
        "source": g.source,
        "node": center,
        "hops": hops,
        "direction": direction,
        "rel": sorted(rel_filter) if rel_filter else None,
        "total-neighbors": total_neighbors,
        "returned-neighbors": len(neighbors),
        "truncated": total_neighbors > len(neighbors),
        "include-body": bool(include_body or body_chars > 0),
        "neighbors": neighbors,
        "edges": kept_edges,
    }


def search_rokb(
    target: Path,
    query_text: str,
    *,
    from_graph_json: bool = False,
    k: int = 8,
    node_types: Optional[list[str]] = None,
    field_exprs: Optional[list[str]] = None,
    include_body: bool = False,
    body_chars: int = 0,
) -> dict:
    g = load_graph(target, from_graph_json=from_graph_json, need_full=True)
    allowed_types: set[str] = set()
    for t in (node_types or []):
        for part in t.split(","):
            if part.strip():
                allowed_types.add(part.strip())

    corpus = []
    for nid in sorted(g.nodes):
        node = g.nodes[nid]
        if allowed_types and node["type"] not in allowed_types:
            continue
        if field_exprs and not all(_match_field_expr(node, expr) for expr in field_exprs):
            continue
        doc = dict(node["fields"])
        doc["id"] = nid
        doc["body"] = node.get("body") or ""
        corpus.append(doc)

    retriever = Bm25Retriever()
    retriever.index(corpus)
    res = retriever.retrieve(query_text, k=k)

    hits = []
    for p in res.passages:
        n = g.nodes[p.source_node_id]
        hit: dict[str, Any] = {
            "score": round(p.score, 4),
            "id": n["id"],
            "type": n["type"],
            "name": n["name"],
            "path": n["path"],
            "locator": p.locator,
            "snippet": p.text,
        }
        if n.get("status"):
            hit["status"] = n["status"]
        if n.get("role"):
            hit["role"] = n["role"]
        if include_body or body_chars > 0:
            body = n.get("body") or ""
            if body_chars > 0 and len(body) > body_chars:
                body = body[: body_chars - 1].rstrip() + "…"
            hit["body"] = body
        hits.append(hit)

    return {
        "source": g.source,
        "query": query_text,
        "k": k,
        "returned": len(hits),
        "retriever-manifest": res.retriever_manifest,
        "hits": hits,
        "_retrieval_result": res,
    }


def _print_summary_text(s: dict) -> None:
    print(f"Dataset:  {s['dataset-name']} ({s['source']})")
    print(f"Schema:   {s['schema']}  |  Domain: {s['default-domain'] or 'default'}  |  Index enriched: {'yes' if s['enriched-index'] else 'no (run glimmer sync)'}")
    if s.get("root-node"):
        print(f"Root:     {s['root-node']}")
    if s.get("entrypoints"):
        print(f"Entries:  {', '.join(str(e) for e in s['entrypoints'])}")
    print(f"Graph:    {s['node-count']} nodes, {s['edge-count']} edges")
    if s.get("modified-range"):
        mr = s["modified-range"]
        print(f"Modified: {mr['oldest']} .. {mr['newest']}")
    print("\nNodes by type:")
    for t, c in s["by-type"].items():
        extra = ""
        if t == "publication" and s["publication-roles"]:
            roles = ", ".join(f"{k}={v}" for k, v in s["publication-roles"].items())
            extra = f"  ({roles})"
        print(f"  {t:14s} {c:4d}{extra}")
    if s["top-hubs"]:
        print("\nTop hubs (use --no-body / --limit when traversing star hubs):")
        for h in s["top-hubs"]:
            flag = " [star-hub]" if h["degree"] >= STAR_HUB_THRESHOLD else ""
            print(f"  {h['id']:38s} deg={h['degree']:3d} (in={h['in']}, out={h['out']})  {h['type']}{flag}")


def _print_query_table(res: dict) -> None:
    print(f"Matched {res['total']} node(s) (showing {res['returned']}{', truncated' if res['truncated'] else ''}):")
    for n in res["nodes"]:
        tags = [n["type"]]
        if n.get("role"):
            tags.append(n["role"])
        if n.get("subtype"):
            tags.append(n["subtype"])
        if n.get("claim-kind") and n.get("claim-kind") != n.get("subtype"):
            tags.append(n["claim-kind"])
        if n.get("status"):
            tags.append(n["status"])
        deg = n["degree"]
        print(f"  {n['id']}  [{' | '.join(tags)}]  deg={deg['in']}+{deg['out']}  ({n['path']})")
        print(f"    {n['name']}")
        if n.get("summary") and n["summary"] != n["name"]:
            print(f"    > {n['summary']}")
        if "body" in n and n["body"]:
            print("    --- body ---")
            for ln in n["body"].splitlines():
                print(f"    {ln}")


def _print_neighbors_table(res: dict) -> None:
    c = res["node"]
    print(f"Center: {c['id']} [{c['type']}] — {c['name']}")
    print(f"Neighbors (hops={res['hops']}, dir={res['direction']}): {res['returned-neighbors']}/{res['total-neighbors']}{' (truncated)' if res['truncated'] else ''}")
    for n in res["neighbors"]:
        status = f" | {n['status']}" if n.get("status") else ""
        print(f"  [hop {n['hop']}] {n['id']} [{n['type']}{status}] — {n['name']} ({n['path']})")
    if res["edges"]:
        print("\nEdges:")
        for e in res["edges"]:
            print(f"  {e['source']} --{e['type']}--> {e['target']}")


def _print_search_table(res: dict) -> None:
    print(f"Search {res['query']!r} ({res['returned']} hit(s), corpus={res['retriever-manifest']['corpus-size']}):")
    for i, h in enumerate(res["hits"], start=1):
        role = f" | {h['role']}" if h.get("role") else ""
        print(f"  {i}. [{h['score']:.4f}] {h['id']} [{h['type']}{role}] ({h['path']} @ {h['locator']})")
        print(f"     {h['name']}")
        if h.get("snippet"):
            print(f"     {h['snippet']}")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Query, search, summarize, and traverse a Glimmer RO-KB.")
    sub = ap.add_subparsers(dest="op", required=True)

    p_sum = sub.add_parser("summary", help="summarize a Glimmer RO-KB")
    p_sum.add_argument("rokb", help="path to RO-KB directory (or graph.json with --graph)")
    p_sum.add_argument("--graph", action="store_true", help="treat input path as compiled workspace graph.json")
    p_sum.add_argument("--format", choices=["table", "json"], default="table")

    p_q = sub.add_parser("query", help="filter nodes by type, frontmatter fields, and edge relations")
    p_q.add_argument("rokb", help="path to RO-KB directory (or graph.json with --graph)")
    p_q.add_argument("--graph", action="store_true", help="treat input path as compiled workspace graph.json")
    p_q.add_argument("--type", action="append", dest="types", help="filter by node type (repeatable or comma-separated)")
    p_q.add_argument("--field", action="append", dest="fields", help="frontmatter filter: key=value, key~=substr, or key?")
    p_q.add_argument("--rel", default=None, help="filter nodes participating in edge type")
    p_q.add_argument("--direction", choices=["out", "in", "both"], default="both")
    p_q.add_argument("--source", default=None, help="filter edges by source node id")
    p_q.add_argument("--target", default=None, help="filter edges by target node id")
    p_q.add_argument("--limit", type=int, default=50, help="max results (0 = unlimited)")
    p_q.add_argument("--no-body", action="store_true", help="omit markdown bodies (default)")
    p_q.add_argument("--include-body", action="store_true", help="include full markdown bodies")
    p_q.add_argument("--body-chars", type=int, default=0, help="include body truncated to N chars")
    p_q.add_argument("--format", choices=["table", "json", "paths", "ids"], default="table")

    p_n = sub.add_parser("neighbors", help="traverse N-hop neighborhood around a node (metadata-only by default)")
    p_n.add_argument("rokb", help="path to RO-KB directory (or graph.json with --graph)")
    p_n.add_argument("node_id", help="starting node ID")
    p_n.add_argument("--graph", action="store_true", help="treat input path as compiled workspace graph.json")
    p_n.add_argument("--hops", type=int, default=1, help="traversal depth (default: 1)")
    p_n.add_argument("--rel", default=None, help="comma-separated edge types to follow")
    p_n.add_argument("--direction", choices=["out", "in", "both"], default="both")
    p_n.add_argument("--limit", type=int, default=50, help="max neighbor nodes (default: 50)")
    p_n.add_argument("--no-body", action="store_true", help="omit markdown bodies (default)")
    p_n.add_argument("--include-body", action="store_true", help="include full markdown bodies")
    p_n.add_argument("--body-chars", type=int, default=0, help="include body truncated to N chars")
    p_n.add_argument("--format", choices=["table", "json"], default="table")

    p_s = sub.add_parser("search", help="BM25 search across node sidecars and Markdown bodies")
    p_s.add_argument("rokb", help="path to RO-KB directory (or graph.json with --graph)")
    p_s.add_argument("query", help="search query string")
    p_s.add_argument("--graph", action="store_true", help="treat input path as compiled workspace graph.json")
    p_s.add_argument("-k", "--k", type=int, default=8, help="max hits (default: 8)")
    p_s.add_argument("--type", action="append", dest="types", help="filter corpus by node type")
    p_s.add_argument("--field", action="append", dest="fields", help="filter corpus by frontmatter field")
    p_s.add_argument("--no-body", action="store_true", help="omit full bodies (default)")
    p_s.add_argument("--include-body", action="store_true", help="include full bodies in output")
    p_s.add_argument("--body-chars", type=int, default=0, help="include body truncated to N chars")
    p_s.add_argument("--emit-finding", default=None, help="emit a protocol-conformant finding JSON with this finding id")
    p_s.add_argument("--concept-id", default=None, help="concept id to attach when using --emit-finding")
    p_s.add_argument("--model", default="glimmer-bm25-cli", help="model-identifier when using --emit-finding")
    p_s.add_argument("--format", choices=["table", "json"], default="table")

    args = ap.parse_args(argv)
    try:
        if args.op == "summary":
            res = summarize_rokb(Path(args.rokb), from_graph_json=args.graph)
            if args.format == "json":
                print(json.dumps(res, indent=2, ensure_ascii=False))
            else:
                _print_summary_text(res)
            return 0

        if args.op == "query":
            include_body = bool(args.include_body and not args.no_body)
            res = query_nodes(
                Path(args.rokb),
                from_graph_json=args.graph,
                node_types=args.types,
                field_exprs=args.fields,
                rel=args.rel,
                direction=args.direction,
                source_id=args.source,
                target_id=args.target,
                limit=args.limit,
                include_body=include_body,
                body_chars=args.body_chars,
            )
            if args.format == "json":
                print(json.dumps(res, indent=2, ensure_ascii=False))
            elif args.format == "paths":
                for n in res["nodes"]:
                    print(n["path"])
            elif args.format == "ids":
                for n in res["nodes"]:
                    print(n["id"])
            else:
                _print_query_table(res)
            return 0

        if args.op == "neighbors":
            include_body = bool(args.include_body and not args.no_body)
            res = traverse_neighbors(
                Path(args.rokb),
                args.node_id,
                from_graph_json=args.graph,
                hops=args.hops,
                rel=args.rel,
                direction=args.direction,
                limit=args.limit,
                include_body=include_body,
                body_chars=args.body_chars,
            )
            if args.format == "json":
                print(json.dumps(res, indent=2, ensure_ascii=False))
            else:
                _print_neighbors_table(res)
            return 0

        if args.op == "search":
            include_body = bool(args.include_body and not args.no_body)
            res = search_rokb(
                Path(args.rokb),
                args.query,
                from_graph_json=args.graph,
                k=args.k,
                node_types=args.types,
                field_exprs=args.fields,
                include_body=include_body,
                body_chars=args.body_chars,
            )
            retrieval_result = res.pop("_retrieval_result")
            if args.emit_finding:
                from datetime import datetime, timezone
                finding = finding_from_retrieval(
                    finding_id=args.emit_finding,
                    interpretation=f"BM25 retrieval results for query {args.query!r}.",
                    result=retrieval_result,
                    model_identifier=args.model,
                    timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    concept_id=args.concept_id,
                )
                print(json.dumps(finding, indent=2, ensure_ascii=False))
            elif args.format == "json":
                print(json.dumps(res, indent=2, ensure_ascii=False))
            else:
                _print_search_table(res)
            return 0
    except (ValueError, KeyError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
