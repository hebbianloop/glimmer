#!/usr/bin/env python3
"""Build the Training-FSQC RO-KB from the raw CSV.

Output: a Glimmer-format research-object knowledge base under demo/training-fsqc-rokb/
- subjects/   : 3 subject sidecars (one per scan)
- raters/     : 7 rater sidecars
- standards/  : 1 rating-scale standard
- methods/    : 1 recon-all method node
- qc-artifacts/: 7 raters × 3 subjects = 21 rating sidecars
- _glimmer-index.json : the master index the agent loads
"""

import csv, json, os, hashlib, datetime, io, sys
from pathlib import Path
import yaml

# Default output: examples/training-fsqc/rokb/ relative to the template root.
# Override with --output if calling from a different layout.
ROOT = Path(__file__).parent.parent.parent / "examples" / "training-fsqc" / "rokb"
CSV_INPUT = ROOT.parent / "raw" / "training-fsqc-raw.csv"

# Hardcoded from the Training-FSQC Spreadsheet body. Schema:
# (subject, rater, recon_all_success, talQC, lh_CNR, rh_CNR, total_CNR, euler_lh, euler_rh,
#  pial, skull_strip, wm_seg, wm_mask, gm_seg, intensity_norm, subcortical, notes)
RAW = [
    # subject 001
    ("001", "Shady",   1,    0.9809,  1.207, 1.208, 1.207, -88,  -180, 4, 0, 3, 2, 0, 2, 2, "*estimated time due to non-continuous workflow"),
    ("001", "Melissa", None, None,    None,  None,  None,  None, None, 4, 4, 3, 1, 0, None, None, ""),
    ("001", "Jackie",  None, None,    None,  None,  None,  None, None, 4, "4-but skull stripping didn't work, so erased dura", 3, 1, 0, 2, None, ""),
    ("001", "Kelly",   None, None,    None,  None,  None,  None, None, 4, 4, "added control points to slides 145, 147, 149, 151, 153 sagittal view", 1, 1, 0, "aseg did not load correctly", "recon-all -make all -s 001"),
    ("001", "Rachel",  None, None,    None,  None,  None,  None, None, 4, 4, "Lots of dura included in wm", None, None, None, None, ""),
    ("001", "Amanda",  1,    0.98099, 1.207, 1.208, 1.207, -88,  -180, 4, 0, 4, 1, 1, 1, 2, ""),
    ("001", "Flavius", None, None,    None,  None,  None,  None, None, 4, 4, 2, 2, 0, 1, 2, ""),
    # subject 002
    ("002", "Shady",   1, 0.98073, 1.293, 1.28, 1.286, -246, -200, 5, 5, 5, 5, 5, 4, 5, "EDITED WM, BRAINMASK"),
    ("002", "Melissa", None, None, None, None, None, None, None, None, None, None, None, None, None, None, ""),
    ("002", "Jackie",  1, 0.98073, 1.293, 1.28, 1.286, -246, -200, 4, 0, 4, 4, 0, 2, 2, ""),
    ("002", "Kelly",   1, 0.98073, 1.293, 1.28, 1.286, -246, -200, 3, 3, 3, 3, 1, 0, 1, "removed dura and edited wm mask"),
    ("002", "Rachel",  None, None, None, None, None, None, None, 3, 0, 5, 5, None, 0, 5, ""),
    ("002", "Amanda",  1, 0.98073, 1.293, 1.28, 1.286, -246, -200, 4, 0, 5, 5, 4, 2, 5, ""),
    ("002", "Flavius", 1, 0.98073, 1.293, 1.28, 1.286, -246, -200, 4, 4, 4, 5, 4, 3, 3, ""),
    # subject 003
    ("003", "Shady",   1, 0.97818, 1.132, 1.105, 1.118, -236, -242, 3, 0, 4, 1, 4, 2, 5, "posterior surface looks OK - pfc looks a bit jacked up"),
    ("003", "Melissa", None, None, None, None, None, None, None, None, None, None, None, None, None, None, ""),
    ("003", "Jackie",  1, 0.97818, 1.132, 1.105, 1.118, -236, -242, 4, 0, 4, 4, 4, 2, 2, ""),
    ("003", "Kelly",   1, 0.97818, 1.132, 1.105, 1.118, -236, -242, 4, 0, 4, 3, 2, 0, 3, "did not make edits, only rated"),
    ("003", "Rachel",  1, 0.97818, 1.132, 1.105, 1.118, -236, -242, 0, 0, 4, 4, 4, 0, 3, "only edited WM mask"),
    ("003", "Amanda",  None, None, None, None, None, None, None, None, None, None, None, None, None, None, ""),
    ("003", "Flavius", 1, 0.97818, 1.132, 1.105, 1.118, -236, -242, 2, 0, 4, 2, 3, 1, 2, ""),
]

CATEGORIES = ["pial", "skull_strip", "wm_seg", "wm_mask", "gm_seg", "intensity_norm", "subcortical"]
METRIC_FIELDS = ["recon_all_success", "talQC", "lh_CNR", "rh_CNR", "total_CNR", "euler_lh", "euler_rh"]

RATING_SCALE = {
    0: "no edits",
    1: "local errors but no editing",
    2: "widespread errors but no editing required",
    3: "local errors with editing required",
    4: "widespread errors with editing",
    5: "extensive defects and errors",
}

NOW = datetime.datetime.now(datetime.timezone.utc).isoformat()

def hash_body(s: str) -> str:
    return "sha256:" + hashlib.sha256(s.encode()).hexdigest()[:16]

def write_node(rel_path: str, frontmatter: dict, body: str = "") -> str:
    """Write a Glimmer node as a markdown file with YAML front-matter. Returns the node id."""
    full_path = ROOT / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    # Compute provenance hash over the body alone (front-matter excluded)
    frontmatter["provenance-hash"] = hash_body(body)
    # Emit valid YAML so a standard parser can read it back. default_flow_style=False
    # produces block style; sort_keys=False preserves field order.
    fm_yaml = "---\n" + yaml.dump(frontmatter, sort_keys=False, default_flow_style=False, allow_unicode=True) + "---\n\n"
    full_path.write_text(fm_yaml + body)
    return frontmatter["id"]

def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    nodes_index = []

    # -- standard: ADS QC rating scale --
    std_id = "ads-qc-scale-v1"
    scale_body = (
        "ADS QC ordinal rating scale, used by all raters in the Training-FSQC corpus.\n\n"
        + "\n".join(f"- **{k}**: {v}" for k, v in RATING_SCALE.items())
        + "\n\nApplied independently per anatomical category: "
        + ", ".join(CATEGORIES)
    )
    write_node(f"standards/{std_id}.md", {
        "id": std_id, "type": "standard", "name": "ADS QC Rating Scale (v1)",
        "created": NOW, "modified": NOW,
        "scale-type": "ordinal-0-5",
        "categories": CATEGORIES,
        "scale": RATING_SCALE,
        "edges": [],
        "description": "0=no edits needed; 5=extensive defects. Applied per anatomical category.",
    }, scale_body)
    nodes_index.append({"id": std_id, "type": "standard", "path": f"standards/{std_id}.md"})

    # -- method: recon-all --
    method_id = "method-recon-all-fs6"
    write_node(f"methods/{method_id}.md", {
        "id": method_id, "type": "method", "name": "FreeSurfer recon-all (v6.0)",
        "created": NOW, "modified": NOW,
        "tool": "recon-all", "version": "freesurfer-6.0.0",
        "produces": "T1w-derived cortical reconstruction + segmentation",
        "edges": [{"type": "validates-against", "target": "Fischl-2012-FreeSurfer"}],
        "description": "Standard FreeSurfer cortical reconstruction pipeline. Each subject's recon-all output is the input to the QC ratings.",
    }, "FreeSurfer recon-all v6.0; default parameters.")
    nodes_index.append({"id": method_id, "type": "method", "path": f"methods/{method_id}.md"})

    # -- subjects: 3 datasets --
    subjects_seen = {}
    for row in RAW:
        subj = row[0]
        if subj in subjects_seen: continue
        # Use the first row's metric block as the canonical metric for the subject
        metrics = {}
        for i, field in enumerate(METRIC_FIELDS, start=2):
            v = row[i]
            if v is not None:
                metrics[field] = v
        # Find any row that has metrics if the first one didn't
        if not metrics:
            for r in RAW:
                if r[0] == subj and r[2] is not None:
                    for i, field in enumerate(METRIC_FIELDS, start=2):
                        metrics[field] = r[i]
                    break
        sid = f"subject-{subj}"
        body = (
            f"Training-FSQC subject {subj}. Structural T1w MRI input to FreeSurfer recon-all (v6.0).\n\n"
            f"Underlying QC metrics extracted from recon-all output:\n"
            + "\n".join(f"- `{k}`: {v}" for k, v in metrics.items())
        )
        write_node(f"subjects/{sid}.md", {
            "id": sid, "type": "dataset",
            "name": f"Training-FSQC Subject {subj}",
            "created": "2016-08-15T00:00:00Z", "modified": "2016-08-15T00:00:00Z",
            "subject-id": subj,
            "modality": "anat-T1w",
            "metrics": metrics,
            "edges": [
                {"type": "produced-by", "target": method_id},
                {"type": "conforms-to", "target": std_id},
            ],
            "description": f"Subject {subj}, ADS Training-FSQC corpus. QC metrics are the agent's evidence for rating.",
        }, body)
        nodes_index.append({"id": sid, "type": "dataset", "path": f"subjects/{sid}.md"})
        subjects_seen[subj] = sid

    # -- raters: 7 humans --
    RATERS = ["Shady", "Melissa", "Jackie", "Kelly", "Rachel", "Amanda", "Flavius"]
    for rname in RATERS:
        rid = f"rater-{rname.lower()}"
        write_node(f"raters/{rid}.md", {
            "id": rid, "type": "rater", "name": rname,
            "created": "2016-08-15T00:00:00Z", "modified": "2016-08-15T00:00:00Z",
            "role": "human", "trained-on": std_id,
            "edges": [{"type": "trained-on", "target": std_id}],
            "description": f"Human rater on the ADS Training-FSQC corpus, 2016.",
        }, f"Human QC rater trained on {std_id}.")
        nodes_index.append({"id": rid, "type": "rater", "path": f"raters/{rid}.md"})

    # -- qc-artifacts: 21 ratings, one per (rater, subject) pair --
    for row in RAW:
        subj, rname = row[0], row[1]
        ratings = {}
        for i, cat in enumerate(CATEGORIES, start=9):
            v = row[i]
            if isinstance(v, int) and 0 <= v <= 5:
                ratings[cat] = v
            # Drop string-valued "ratings" (those are notes, not ratings) — they're free-text observations
        notes = row[16]
        if not ratings:
            continue  # skip rater-subject pairs where no actual ratings were issued
        qid = f"qc-{rname.lower()}-on-{subj}"
        write_node(f"qc-artifacts/{qid}.md", {
            "id": qid, "type": "qc-artifact",
            "name": f"QC by {rname} on subject {subj}",
            "created": "2016-08-15T00:00:00Z", "modified": "2016-08-15T00:00:00Z",
            "ratings": ratings, "notes": notes,
            "edges": [
                {"type": "attests-to-quality-of", "target": f"subject-{subj}"},
                {"type": "issued-by", "target": f"rater-{rname.lower()}"},
                {"type": "conforms-to", "target": std_id},
            ],
            "description": f"7-category ordinal QC ratings issued by {rname} on subject {subj}.",
        }, notes or f"QC ratings by {rname} on subject {subj}.")
        nodes_index.append({"id": qid, "type": "qc-artifact", "path": f"qc-artifacts/{qid}.md"})

    # -- write the master index --
    index = {
        "schema": "glimmer/v0.1",
        "dataset-name": "Training-FSQC",
        "created": NOW,
        "node-count": len(nodes_index),
        "nodes": nodes_index,
    }
    (ROOT / "_glimmer-index.json").write_text(json.dumps(index, indent=2))

    # Report
    by_type = {}
    for n in nodes_index:
        by_type[n["type"]] = by_type.get(n["type"], 0) + 1
    print(f"Built RO-KB at {ROOT}")
    print(f"  Total nodes: {len(nodes_index)}")
    for t, n in sorted(by_type.items()):
        print(f"    {t:13s}: {n}")

if __name__ == "__main__":
    main()
