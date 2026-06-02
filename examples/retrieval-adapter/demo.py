#!/usr/bin/env python3
"""End-to-end demo of the retrieval adapter, stdlib-only.

Indexes three `publication` nodes, retrieves against a hypothesis query with the
reference Bm25Retriever, emits a protocol-conformant `finding`, writes a Glimmer
graph under rokb/, and validates it.

    cd examples/retrieval-adapter
    python demo.py
    python ../../glimmer/tools/validate.py rokb/

This is the literature-scout loop step from docs/agentic-loop.md, exercised with
no infrastructure. Swap Bm25Retriever for a Haystack/agentic-rag backend and the
rest of this script is unchanged.
"""

import hashlib
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent.parent))

from glimmer.tools.retrieval import finding_from_retrieval  # noqa: E402
from bm25_retriever import Bm25Retriever  # noqa: E402

NOW = "2026-06-02T00:00:00Z"
ROKB = ROOT / "rokb"

# A small literature corpus already present in the graph as `publication` nodes.
# In a real loop these are emitted by the literature scout walking PubMed/OpenAlex.
PUBS = [
    {
        "id": "publication-smith-2021",
        "name": "Amygdala reactivity to emotional film predicts later aggression",
        "description": "Longitudinal fMRI study linking adolescent amygdala BOLD "
        "response during naturalistic emotional film to violence outcomes in "
        "emerging adulthood.",
    },
    {
        "id": "publication-jones-2019",
        "name": "Prefrontal-amygdala connectivity and emotion regulation",
        "description": "Resting-state and task connectivity between prefrontal cortex "
        "and amygdala as a modulator of emotional response.",
    },
    {
        "id": "publication-lee-2020",
        "name": "Cerebellar contributions to motor timing",
        "description": "Unrelated control: cerebellar role in millisecond motor timing "
        "tasks, no emotion or aggression content.",
    },
]

QUERY = "amygdala emotional film predicts violence outcome"


def hash_body(s: str) -> str:
    return "sha256:" + hashlib.sha256(s.encode()).hexdigest()[:16]


def write_node(rel_path: str, frontmatter: dict, body: str = "") -> None:
    path = ROKB / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter["provenance-hash"] = hash_body(body)
    path.write_text("---\n" + yaml.dump(frontmatter, sort_keys=False, allow_unicode=True) + "---\n\n" + body)


def main() -> None:
    (ROKB / "publications").mkdir(parents=True, exist_ok=True)
    (ROKB / "findings").mkdir(parents=True, exist_ok=True)
    index_nodes = []

    for pub in PUBS:
        write_node(
            f"publications/{pub['id']}.md",
            {
                "id": pub["id"], "type": "publication", "name": pub["name"],
                "created": NOW, "modified": NOW, "pub-status": "published", "edges": [],
            },
            pub["description"],
        )
        index_nodes.append({"id": pub["id"], "type": "publication",
                            "path": f"publications/{pub['id']}.md"})

    retriever = Bm25Retriever()
    retriever.index(PUBS)
    result = retriever.retrieve(QUERY, k=8)

    print(f"query: {QUERY!r}")
    for p in result.passages:
        print(f"  {p.score:6.3f}  {p.source_node_id}")

    finding = finding_from_retrieval(
        finding_id="finding-h1-prior-lit",
        interpretation="Prior literature supports an amygdala-emotional-film → "
        "violence-outcome link as a testable hypothesis.",
        result=result,
        model_identifier="anthropic/claude-opus-4",
        timestamp=NOW,
    )
    write_node("findings/finding-h1-prior-lit.md",
               {**finding, "name": "H1 prior-literature finding", "created": NOW, "modified": NOW})
    index_nodes.append({"id": "finding-h1-prior-lit", "type": "finding",
                        "path": "findings/finding-h1-prior-lit.md"})

    (ROKB / "_glimmer-index.json").write_text(json.dumps(
        {"schema": "glimmer/v0.2.0", "dataset-name": "retrieval-adapter-demo",
         "nodes": index_nodes}, indent=2))

    print(f"\nwrote {len(index_nodes)} nodes to {ROKB}")
    print("validate with: python ../../glimmer/tools/validate.py rokb/")


if __name__ == "__main__":
    main()
