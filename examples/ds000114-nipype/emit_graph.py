#!/usr/bin/env python3
"""Convert the Nipype workflow's provenance.json into a Glimmer RO-KB.

Reads:    rokb-staging/provenance.json (emitted by workflow.py)
Writes:   rokb/ Glimmer sidecars + _glimmer-index.json

The emitted graph has six node types arranged as:

    dataset (T1w input)
      ↓ produced-by
    method-bet → derivative-bet-brain ←─┐
      ↓ produces                         │
    derivative-bet-brain                 │
      ↓ derives-from                     │ supports-finding
    method-fast → derivative-fast-segs───┤
                                         │
                            finding-brain-volume

Every derivative carries `output-hash` + DataLad coordinates so verify.py can
reproduce. The `finding` is emitted with `provenance-mode: deterministic` and
its `based-on` edges point at the derivatives.
"""

import json, hashlib, datetime, sys
from pathlib import Path
import yaml

ROOT = Path(__file__).parent
STAGING = ROOT / "rokb-staging"
ROKB = ROOT / "rokb"
ROKB.mkdir(exist_ok=True)
for sub in ("datasets", "methods", "derivatives", "findings", "standards"):
    (ROKB / sub).mkdir(exist_ok=True)

PROV = STAGING / "provenance.json"
if not PROV.exists():
    sys.exit(f"ERROR: {PROV} not found. Run workflow.py first.")

provenance = json.loads(PROV.read_text())
NOW = datetime.datetime.now(datetime.timezone.utc).isoformat()

def hash_body(s: str) -> str:
    return "sha256:" + hashlib.sha256(s.encode()).hexdigest()[:16]

def write_node(rel_path: str, frontmatter: dict, body: str = "") -> str:
    full_path = ROKB / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter["provenance-hash"] = hash_body(body)
    fm_yaml = "---\n" + yaml.dump(frontmatter, sort_keys=False, default_flow_style=False, allow_unicode=True) + "---\n\n"
    full_path.write_text(fm_yaml + body)
    return frontmatter["id"]

nodes_index = []

# ─────────────────────────────────────────────────────────────────────────────
# 1. Standard nodes (BIDS spec, FSL release)
# ─────────────────────────────────────────────────────────────────────────────
bids_id = "standard-bids-1.11.1"
write_node(f"standards/{bids_id}.md", {
    "id": bids_id, "type": "standard",
    "name": "BIDS Specification v1.11.1",
    "created": NOW, "modified": NOW,
    "standard-class": "spec",
    "version": "1.11.1",
    "upstream-url": "https://bids-specification.readthedocs.io/en/stable/",
    "edges": [],
    "description": "Brain Imaging Data Structure specification v1.11.1, the file-layout standard the input dataset conforms to.",
}, "BIDS v1.11.1 governs the file layout of the input dataset; verified by bids-validator.")
nodes_index.append({"id": bids_id, "type": "standard", "path": f"standards/{bids_id}.md"})

# ─────────────────────────────────────────────────────────────────────────────
# 2. Dataset node (the input T1w)
# ─────────────────────────────────────────────────────────────────────────────
ds_id = f"dataset-{provenance['subject']}-{provenance['session']}-T1w"
input_meta = provenance["input"]
write_node(f"datasets/{ds_id}.md", {
    "id": ds_id, "type": "dataset",
    "name": f"OpenNeuro ds000114 {provenance['subject']} {provenance['session']} T1w",
    "created": NOW, "modified": NOW,
    "subject-id": provenance["subject"],
    "session": provenance["session"],
    "modality": "anat-T1w",
    "bids-version": "1.11.1",
    "datalad-superdataset": input_meta["datalad-superdataset"],
    "datalad-relative-path": input_meta["datalad-relative-path"],
    "datalad-commit-sha": input_meta["datalad-commit-sha"],
    "datalad-annex-key": input_meta["datalad-annex-key"],
    "edges": [
        {"type": "conforms-to", "target": bids_id},
    ],
    "description": f"Input T1w-weighted anatomical scan from OpenNeuro ds000114, subject {provenance['subject']}, session {provenance['session']}. Self-describing for re-fetch: the DataLad coordinates above are sufficient to retrieve the exact bytes used in this analysis.",
}, f"Input scan retrieved from {input_meta['datalad-superdataset']} at commit `{input_meta['datalad-commit-sha'][:12]}...`.")
nodes_index.append({"id": ds_id, "type": "dataset", "path": f"datasets/{ds_id}.md"})

# ─────────────────────────────────────────────────────────────────────────────
# 3. Method nodes (BET and FAST as Nipype Nodes)
# ─────────────────────────────────────────────────────────────────────────────
fsl_version = provenance["workflow"]["tool-versions"].get("fsl", "fsl-unknown")
nipype_version = provenance["workflow"]["tool-versions"].get("nipype", "nipype-unknown")

bet_id = "method-fsl-bet"
write_node(f"methods/{bet_id}.md", {
    "id": bet_id, "type": "method",
    "name": "FSL BET (Brain Extraction Tool)",
    "created": NOW, "modified": NOW,
    "tool": "fsl.BET",
    "version": fsl_version,
    "nipype-node-type": "Node",
    "parameters": provenance["workflow"]["parameters"]["bet"],
    "workflow-definition-sha": provenance["workflow"]["definition-sha"],
    "edges": [
        {"type": "applies-to", "target": ds_id},
    ],
    "description": "Skull-stripping via FSL BET. Deterministic with `frac=0.5, robust=True`. The workflow-definition-sha pins the exact .py file that orchestrated this invocation.",
}, "BET extracts brain tissue from the raw T1w by fitting a deformable model to image intensity gradients. Output is a brain-extracted T1w plus a binary brain mask.")
nodes_index.append({"id": bet_id, "type": "method", "path": f"methods/{bet_id}.md"})

fast_id = "method-fsl-fast"
write_node(f"methods/{fast_id}.md", {
    "id": fast_id, "type": "method",
    "name": "FSL FAST (FMRIB's Automated Segmentation Tool)",
    "created": NOW, "modified": NOW,
    "tool": "fsl.FAST",
    "version": fsl_version,
    "nipype-node-type": "Node",
    "parameters": provenance["workflow"]["parameters"]["fast"],
    "workflow-definition-sha": provenance["workflow"]["definition-sha"],
    "edges": [],
    "description": "Three-class tissue segmentation (GM, WM, CSF) via FSL FAST. Operates on the BET-extracted brain.",
}, "FAST segments brain tissue into GM, WM, CSF via a hidden Markov random field + EM algorithm. Outputs partial-volume estimate (PVE) maps per tissue class.")
nodes_index.append({"id": fast_id, "type": "method", "path": f"methods/{fast_id}.md"})

# ─────────────────────────────────────────────────────────────────────────────
# 4. Derivative nodes (BET output + FAST PVE maps)
# ─────────────────────────────────────────────────────────────────────────────
outputs = provenance.get("outputs", {})

bet_deriv_id = f"derivative-{provenance['subject']}-T1w-brain"
bet_out = outputs.get("bet_brain", {})
write_node(f"derivatives/{bet_deriv_id}.md", {
    "id": bet_deriv_id, "type": "derivative",
    "name": f"{provenance['subject']} T1w brain (BET output)",
    "created": NOW, "modified": NOW,
    "output-kind": "volume",
    "provenance-mode": "deterministic",
    "output-path": bet_out.get("path"),
    "output-format": "nifti",
    "output-hash": "sha256:" + bet_out.get("sha256", "")[:64] if bet_out.get("sha256") else None,
    "edges": [
        {"type": "produced-by", "target": bet_id},
        {"type": "derives-from", "target": ds_id},
    ],
    "description": f"Brain-extracted T1w. Hash anchors verifiability: re-running `{bet_id}` on `{ds_id}` at the cited DataLad SHA should produce a file with this exact hash.",
}, f"BET output, {bet_out.get('size-bytes', '?')} bytes. The SHA-256 in this sidecar is what verify.py compares against on re-run.")
nodes_index.append({"id": bet_deriv_id, "type": "derivative", "path": f"derivatives/{bet_deriv_id}.md"})

# Each FAST output as its own derivative
fast_deriv_ids = []
for i, fast_out in enumerate(outputs.get("fast_segs", [])):
    fast_deriv_id = f"derivative-{provenance['subject']}-fast-pve-{i}"
    write_node(f"derivatives/{fast_deriv_id}.md", {
        "id": fast_deriv_id, "type": "derivative",
        "name": f"{provenance['subject']} FAST PVE map {i}",
        "created": NOW, "modified": NOW,
        "output-kind": "volume",
        "provenance-mode": "deterministic",
        "output-path": fast_out["path"],
        "output-format": "nifti",
        "output-hash": "sha256:" + fast_out["sha256"][:64],
        "edges": [
            {"type": "produced-by", "target": fast_id},
            {"type": "derives-from", "target": bet_deriv_id},
        ],
        "description": f"FAST partial-volume estimate map (tissue class {i}). Verifiable via output-hash on re-run.",
    }, f"FAST PVE map. {fast_out.get('size-bytes', '?')} bytes.")
    nodes_index.append({"id": fast_deriv_id, "type": "derivative", "path": f"derivatives/{fast_deriv_id}.md"})
    fast_deriv_ids.append(fast_deriv_id)

# ─────────────────────────────────────────────────────────────────────────────
# 5. Finding node — the interpreted assertion grounded in derivatives
# ─────────────────────────────────────────────────────────────────────────────
# A simple deterministic finding: aggregated brain mask volume in mm³
# (computed from the BET output during emit, NOT inferred by an LLM)
brain_volume_mm3 = None
try:
    import nibabel as nib
    import numpy as np
    if bet_out.get("path") and Path(bet_out["path"]).exists():
        img = nib.load(bet_out["path"])
        data = img.get_fdata()
        voxel_volume_mm3 = float(np.prod(img.header.get_zooms()))
        # Brain voxels = nonzero
        brain_voxel_count = int(np.count_nonzero(data))
        brain_volume_mm3 = brain_voxel_count * voxel_volume_mm3
except Exception as e:
    print(f"  ! could not compute brain volume: {e}")

finding_id = f"finding-{provenance['subject']}-brain-volume"
interp = (
    f"Subject {provenance['subject']} has an estimated brain volume of "
    f"{brain_volume_mm3:,.0f} mm³ (derived from BET output)."
    if brain_volume_mm3 else
    f"Subject {provenance['subject']} brain volume computation pending (BET output not available)."
)
write_node(f"findings/{finding_id}.md", {
    "id": finding_id, "type": "finding",
    "name": f"{provenance['subject']} brain volume",
    "created": NOW, "modified": NOW,
    "interpretation": interp,
    "based-on": [bet_deriv_id] + fast_deriv_ids,
    "confidence": "high",
    "produced-by-agent": "scripted-deterministic (emit_graph.py)",
    "reasoning-trace": {
        "nodes-accessed": [bet_deriv_id, bet_id, ds_id],
        "metrics-cited": {"brain-volume-mm3": brain_volume_mm3 if brain_volume_mm3 else "pending"},
        "evidence-summary": (
            f"Volume computed deterministically from the BET output [[{bet_deriv_id}]] "
            f"by counting nonzero voxels and multiplying by voxel size from the NIfTI header. "
            f"The chain is verifiable: [[{ds_id}]] (DataLad-pinned) → [[{bet_id}]] (FSL deterministic) "
            f"→ [[{bet_deriv_id}]] (output-hashed) → this finding."
        ),
        "model-identifier": "emit_graph.py (deterministic; not LLM-inferred)",
        "timestamp": NOW,
    },
    "edges": [
        {"type": "based-on", "target": bet_deriv_id},
        *[{"type": "based-on", "target": fid} for fid in fast_deriv_ids],
    ],
    "description": "An interpreted finding grounded in the BET + FAST derivatives. Aggregates the per-derivative output into a single interpretable quantity (total brain volume).",
}, f"Brain volume: {brain_volume_mm3:,.0f} mm³" if brain_volume_mm3 else "Brain volume: pending.")
nodes_index.append({"id": finding_id, "type": "finding", "path": f"findings/{finding_id}.md"})

# ─────────────────────────────────────────────────────────────────────────────
# 6. Master index
# ─────────────────────────────────────────────────────────────────────────────
index = {
    "schema": "glimmer/v0.3.1",
    "dataset-name": "ds000114-nipype-demo",
    "default-domain": "neuroimaging",   # BIDS profile: subject-id, modality, output-kind, …
    "created": NOW,
    "node-count": len(nodes_index),
    "nodes": nodes_index,
    "upstream-graph": provenance["input"]["datalad-superdataset"],
}
(ROKB / "_glimmer-index.json").write_text(json.dumps(index, indent=2))

# Report
by_type = {}
for n in nodes_index:
    by_type[n["type"]] = by_type.get(n["type"], 0) + 1
print(f"Emitted Glimmer RO-KB at {ROKB}")
print(f"  Total nodes: {len(nodes_index)}")
for t, n in sorted(by_type.items()):
    print(f"    {t:13s}: {n}")
print()
print("Next: glimmer validate rokb/  &&  python verify.py")
