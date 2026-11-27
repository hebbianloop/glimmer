#!/usr/bin/env python3
"""Nipype anatomical preprocessing workflow for one subject's T1w.

Workflow:  T1w → BET (skull strip) → FAST (3-class tissue segmentation)

The recorded hashes cover the output files as written, including their headers.
"""

import os, sys, json, hashlib
from pathlib import Path

import nipype.pipeline.engine as pe
from nipype.interfaces import fsl

# ─────────────────────────────────────────────────────────────────────────────
# Paths and parameters
# ─────────────────────────────────────────────────────────────────────────────

# Read DataLad coordinates emitted by install.sh
DATA_DIR = Path(os.environ.get("GLIMMER_DATA_DIR", Path.home() / "data" / "ds000114"))
COORDS_FILE = DATA_DIR / ".glimmer-coordinates.json"
if not COORDS_FILE.exists():
    sys.exit(f"ERROR: {COORDS_FILE} not found. Run install.sh first.")

COORDS = json.loads(COORDS_FILE.read_text())
T1W_PATH = DATA_DIR.absolute() / COORDS["t1w-relative-path"]
SUBJECT = COORDS["subject"]
SESSION = COORDS["session"]

# Output directory for the workflow + provenance
OUT_DIR = Path(__file__).parent / "rokb-staging"
OUT_DIR.mkdir(exist_ok=True)

# Fixed BET + FAST parameters — chosen for determinism + reasonable defaults
BET_PARAMS = {"frac": 0.5, "robust": True, "mask": True}
FAST_PARAMS = {"img_type": 1, "number_classes": 3, "no_pve": False}

print(f"Input T1w:   {T1W_PATH}")
print(f"Output dir:  {OUT_DIR}")
print(f"DataLad SHA: {COORDS['datalad-commit-sha']}")
print()

if not T1W_PATH.exists():
    sys.exit(f"ERROR: T1w not found at {T1W_PATH}. Did install.sh succeed?")

# ─────────────────────────────────────────────────────────────────────────────
# Define the workflow
# ─────────────────────────────────────────────────────────────────────────────

wf = pe.Workflow(name="anat_preproc", base_dir=str(OUT_DIR))

# Node 1: BET (skull strip)
bet = pe.Node(fsl.BET(**BET_PARAMS), name="bet")
bet.inputs.in_file = str(T1W_PATH)

# Node 2: FAST (tissue segmentation, runs on BET output)
fast = pe.Node(fsl.FAST(**FAST_PARAMS), name="fast")

wf.connect([(bet, fast, [("out_file", "in_files")])])

# ─────────────────────────────────────────────────────────────────────────────
# Execute
# ─────────────────────────────────────────────────────────────────────────────

print("Running workflow...")
try:
    result = wf.run()
    print("  ✓ workflow complete")
except Exception as e:
    sys.exit(f"ERROR: workflow failed: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# Compute output hashes for provenance
# ─────────────────────────────────────────────────────────────────────────────

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

# Read the outputs reported by this invocation, including when Nipype reuses a cached node.
completed = {node.name: node.result.outputs for node in result.nodes}
brain = Path(completed["bet"].out_file)
segments = [Path(path) for path in completed["fast"].partial_volume_files]
if len(segments) != FAST_PARAMS["number_classes"]:
    sys.exit(f"FAST reported {len(segments)} partial-volume files; expected {FAST_PARAMS['number_classes']}")

def output_record(path):
    return {"path": str(path), "sha256": sha256(path), "size-bytes": path.stat().st_size}

outputs = {"bet_brain": output_record(brain), "fast_segs": [output_record(path) for path in segments]}

# Compute workflow definition SHA (this very file)
this_file = Path(__file__).resolve()
workflow_def_sha = sha256(this_file)

fsl_version = fsl.Info.version() or "fsl-unknown"

provenance = {
    "subject": SUBJECT,
    "session": SESSION,
    "input": {
        "path": str(T1W_PATH),
        "datalad-superdataset": COORDS["datalad-superdataset"],
        "datalad-relative-path": COORDS["t1w-relative-path"],
        "datalad-commit-sha": COORDS["datalad-commit-sha"],
        "datalad-annex-key": COORDS["t1w-annex-key"],
    },
    "workflow": {
        "definition-sha": workflow_def_sha,
        "definition-path": str(this_file),
        "tool-versions": {
            "fsl": fsl_version,
            "nipype": __import__("nipype").__version__,
        },
        "parameters": {
            "bet": BET_PARAMS,
            "fast": FAST_PARAMS,
        },
    },
    "outputs": outputs,
}

prov_path = OUT_DIR / "provenance.json"
prov_path.write_text(json.dumps(provenance, indent=2))
print(f"\n  ✓ provenance written: {prov_path}")
print(f"  ✓ workflow definition SHA: {workflow_def_sha[:16]}...")
if "bet_brain" in outputs:
    print(f"  ✓ BET output SHA:           {outputs['bet_brain']['sha256'][:16]}...")
if outputs.get("fast_segs"):
    print(f"  ✓ FAST outputs:             {len(outputs['fast_segs'])} files")
print()
print("Next: python emit_graph.py")
