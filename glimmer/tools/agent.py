#!/usr/bin/env python3
"""Glimmer QC agent — reasons over the RO-KB graph and renders QC ratings.

Algorithm:
  1. Load the _glimmer-index.json (mandatory cold-start).
  2. For each (subject, category) decision point:
       a. Read the subject sidecar (`dataset` node) — gets the underlying QC metrics.
       b. Walk `conforms-to` edge → read the `standard` sidecar (rating scale + category defs).
       c. Walk `produced-by` → read the `method` sidecar (what pipeline produced these metrics).
       d. (BLIND CONDITION:) do NOT load other raters' qc-artifacts for this subject.
       e. Send the assembled evidence to the LLM with explicit instructions to return:
            { "rating": <0-5>, "reasoning": <str citing nodes traversed> }
  3. Persist agent verdicts as new qc-artifact sidecars in the RO-KB
     (qc-agent-on-<subject>.md). The agent becomes a `rater` node in the graph.

Usage:
  OPENROUTER_API_KEY=sk-or-... python3 agent.py [--model anthropic/claude-opus-4]
                                                [--informed]  # use other raters' ratings as evidence
"""

import json, os, sys, hashlib, datetime, argparse, urllib.request, urllib.parse
from pathlib import Path
import yaml

ROOT = Path(__file__).parent / "training-fsqc-rokb"
NOW = datetime.datetime.now(datetime.timezone.utc).isoformat()

CATEGORIES = ["pial", "skull_strip", "wm_seg", "wm_mask", "gm_seg", "intensity_norm", "subcortical"]

def load_index():
    with open(ROOT / "_glimmer-index.json") as f:
        return json.load(f)

def read_node(rel_path: str):
    """Read a Glimmer sidecar; return (frontmatter_dict, body_str)."""
    text = (ROOT / rel_path).read_text()
    if not text.startswith("---\n"):
        return {}, text
    _, fm, body = text.split("---\n", 2)
    return yaml.safe_load(fm) or {}, body

def find_node(index, node_id):
    for n in index["nodes"]:
        if n["id"] == node_id:
            return n
    return None

def walk_edge(index, from_fm, edge_type):
    """Return list of target node-paths reachable from this node via edge_type."""
    out = []
    for e in (from_fm.get("edges") or []):
        if e.get("type") == edge_type:
            t = find_node(index, e["target"])
            if t: out.append(t)
    return out

# ---------- LLM call ----------

def call_llm(messages, model, api_key, max_tokens=2000):
    """Call the OpenRouter chat completions endpoint. Returns the assistant message string."""
    req_body = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=req_body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/hebbianloop/glimmer",
            "X-Title": "Glimmer QC Agent (CAISC 2026)",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.loads(r.read())
    return resp["choices"][0]["message"]["content"]

# ---------- Agent ----------

SYSTEM_PROMPT = """You are a structural-MRI quality control rater operating over a Glimmer
research-object knowledge base. You receive evidence collected by traversing the graph:
the subject's underlying QC metrics (CNR, Euler numbers, Talairach registration), the rating
scale definition (the ADS QC ordinal scale 0-5), and the pipeline that produced these metrics.

Your task: render an ordinal rating (0-5) for ONE anatomical category per query, with a
reasoning trace that cites the metric values you weighted most heavily and the rating-scale
anchor that matches the evidence. Your output is a JSON object — nothing else.

Rating scale (CRITICAL — refer to this for every decision):
  0 = no edits needed
  1 = local errors but no editing needed
  2 = widespread errors but no editing required
  3 = local errors with editing required
  4 = widespread errors with editing required
  5 = extensive defects and errors

You are issuing structured ratings; you are NOT estimating subjective preferences. Two raters
applying this scale consistently will agree on most cases. Disagreement is expected only at
boundaries (e.g., 3 vs 4).

Output JSON schema (your entire response):
{
  "rating": <integer 0-5>,
  "reasoning": "<one-paragraph trace: cites which metrics + which rating-scale anchor>"
}
"""

def render_user_prompt(subject_fm, subject_body, standard_fm, standard_body,
                       method_fm, category, peer_qc=None):
    parts = [
        f"# RO-KB EVIDENCE FOR: subject={subject_fm['subject-id']}, category={category}",
        "",
        "## Subject node (dataset)",
        f"ID: {subject_fm['id']}",
        f"Modality: {subject_fm.get('modality')}",
        "Underlying QC metrics (from recon-all output):",
        json.dumps(subject_fm.get("metrics", {}), indent=2),
        "",
        "## Method node (the pipeline that produced the metrics)",
        f"ID: {method_fm['id']}",
        f"Tool: {method_fm.get('tool')} version {method_fm.get('version')}",
        "",
        "## Standard node (rating scale)",
        json.dumps(standard_fm.get("scale", {}), indent=2),
        f"Categories evaluated under this standard: {standard_fm.get('categories')}",
        "",
    ]
    if peer_qc:
        parts.extend([
            "## Peer ratings on this subject (cohort context — same category)",
            json.dumps(peer_qc, indent=2),
            "",
        ])
    parts.extend([
        f"## DECISION REQUIRED",
        f"Render a 0-5 ordinal rating for category `{category}` on subject {subject_fm['subject-id']}.",
        "Output ONLY the JSON object specified in the system prompt.",
    ])
    return "\n".join(parts)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="anthropic/claude-opus-4")
    ap.add_argument("--informed", action="store_true",
                    help="Include peer raters' ratings as evidence (non-blind condition)")
    ap.add_argument("--output", default=str(Path(__file__).parent / "agent-verdicts.json"))
    args = ap.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not set", file=sys.stderr); sys.exit(2)

    index = load_index()

    # Collect verdicts: list of {subject, category, agent_rating, reasoning, condition}
    verdicts = []

    subjects = [n for n in index["nodes"] if n["type"] == "dataset"]
    standard_node = next(n for n in index["nodes"] if n["type"] == "standard")
    method_node = next(n for n in index["nodes"] if n["type"] == "method")
    qc_nodes = [n for n in index["nodes"] if n["type"] == "qc-artifact"]

    standard_fm, standard_body = read_node(standard_node["path"])
    method_fm, _ = read_node(method_node["path"])

    print(f"Glimmer agent: {len(subjects)} subjects × {len(CATEGORIES)} categories = {len(subjects)*len(CATEGORIES)} decisions")
    print(f"Model: {args.model}")
    print(f"Condition: {'INFORMED' if args.informed else 'BLIND'}")
    print()

    for subj_node in subjects:
        subj_fm, subj_body = read_node(subj_node["path"])
        subject_id = subj_fm["subject-id"]
        # Pre-load peer ratings on this subject (for the informed condition + scoring later)
        peer_ratings_by_cat = {c: [] for c in CATEGORIES}
        for q in qc_nodes:
            qfm, _ = read_node(q["path"])
            target = next((e["target"] for e in qfm["edges"] if e["type"] == "attests-to-quality-of"), None)
            if target == subj_node["id"]:
                rater = next((e["target"] for e in qfm["edges"] if e["type"] == "issued-by"), None)
                for cat, val in (qfm.get("ratings") or {}).items():
                    if cat in peer_ratings_by_cat and isinstance(val, int):
                        peer_ratings_by_cat[cat].append({"rater": rater, "rating": val})

        for cat in CATEGORIES:
            peer_qc = peer_ratings_by_cat[cat] if args.informed else None
            user_prompt = render_user_prompt(subj_fm, subj_body, standard_fm, standard_body,
                                             method_fm, cat, peer_qc)
            print(f"  → subject={subject_id} category={cat}", end=" ... ", flush=True)
            try:
                resp = call_llm(
                    [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user",   "content": user_prompt}],
                    model=args.model, api_key=api_key,
                )
                # Parse JSON out of the response
                resp_stripped = resp.strip()
                if resp_stripped.startswith("```"):
                    resp_stripped = "\n".join(resp_stripped.split("\n")[1:-1])
                parsed = json.loads(resp_stripped)
                rating = int(parsed["rating"])
                reasoning = parsed.get("reasoning", "")
                print(f"rating={rating}")
                verdicts.append({
                    "subject": subject_id, "category": cat,
                    "agent_rating": rating, "reasoning": reasoning,
                    "condition": "informed" if args.informed else "blind",
                    "model": args.model,
                })
            except Exception as e:
                print(f"ERROR: {e}")
                verdicts.append({
                    "subject": subject_id, "category": cat,
                    "agent_rating": None, "reasoning": f"ERROR: {e}",
                    "condition": "informed" if args.informed else "blind",
                    "model": args.model,
                })
            # Incremental save after every decision so partial runs are recoverable
            with open(args.output, "w") as f:
                json.dump({
                    "model": args.model,
                    "condition": "informed" if args.informed else "blind",
                    "timestamp": NOW,
                    "verdicts": verdicts,
                }, f, indent=2)

    print(f"\nWrote {len(verdicts)} verdicts to {args.output}")

if __name__ == "__main__":
    main()
