#!/usr/bin/env python3
"""Nipype anatomical preprocessing workflow for one subject's T1w.

Workflow:  T1w → BET (skull strip) → FAST (3-class tissue segmentation)

Deterministic with the parameters specified below; running this twice on the
same input should produce byte-identical outputs (modulo timestamps in NIfTI
headers, which the verify script normalizes).
"""

import os, sys, json, hashlib, subprocess
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
T1W_PATH = (DATA_DIR / COORDS["t1w-relative-path"]).resolve()
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

# Locate workflow outputs
bet_out = OUT_DIR / "anat_preproc" / "bet" / "sub-01_ses-test_T1w_brain.nii.gz"
fast_outs = sorted((OUT_DIR / "anat_preproc" / "fast").glob("*_pve_*.nii.gz"))

outputs = {}
if bet_out.exists():
    outputs["bet_brain"] = {
        "path": str(bet_out),
        "sha256": sha256(bet_out),
        "size-bytes": bet_out.stat().st_size,
    }
if fast_outs:
    outputs["fast_segs"] = []
    for f in fast_outs:
        outputs["fast_segs"].append({
            "path": str(f),
            "sha256": sha256(f),
            "size-bytes": f.stat().st_size,
        })

# Compute workflow definition SHA (this very file)
this_file = Path(__file__).resolve()
workflow_def_sha = sha256(this_file)

# Record FSL version
try:
    fsl_version = subprocess.check_output(["bet", "-h"], stderr=subprocess.STDOUT, text=True)
    # bet prints version in first lines; extract
    fsl_version = fsl_version.splitlines()[0] if fsl_version else "fsl-unknown"
except Exception:
    fsl_version = "fsl-unknown"

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
