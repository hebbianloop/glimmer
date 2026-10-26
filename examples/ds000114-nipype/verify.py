#!/usr/bin/env python3
"""Check existing derivative files against hashes recorded in their sidecars.

This script does not fetch or verify input pins, inspect method implementations,
or execute BET/FAST. Run workflow.py separately to generate new artifacts, and
retain an independent baseline when comparing runs. A match here establishes
artifact/sidecar consistency only. Legacy report field names are retained for
compatibility and must not be interpreted as a reproduction experiment.
"""

import json, hashlib, sys, subprocess
from pathlib import Path
import yaml

ROOT = Path(__file__).parent
ROKB = ROOT / "rokb"
INDEX = ROKB / "_glimmer-index.json"

if not INDEX.exists():
    sys.exit(f"ERROR: {INDEX} not found. Run emit_graph.py first.")

def read_sidecar(path):
    text = path.read_text()
    if not text.startswith("---\n"):
        return {}
    _, fm, _ = text.split("---\n", 2)
    return yaml.safe_load(fm) or {}

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

# Load the graph
index = json.loads(INDEX.read_text())
nodes_by_id = {}
for entry in index["nodes"]:
    nodes_by_id[entry["id"]] = read_sidecar(ROKB / entry["path"])

derivatives = [(nid, fm) for nid, fm in nodes_by_id.items() if fm.get("type") == "derivative"]

print(f"Glimmer artifact hash check — {len(derivatives)} derivatives to check\n")

results = []
for did, dfm in derivatives:
    recorded_hash = dfm.get("output-hash", "")
    recorded_hash = recorded_hash.replace("sha256:", "")[:64]
    out_path = dfm.get("output-path")
    if not out_path or not Path(out_path).exists():
        results.append((did, "missing", recorded_hash, None))
        print(f"  ✗ {did}: output file not on disk at {out_path}")
        continue
    # Re-hash the EXISTING output (idempotent check; not a full re-run)
    # A true re-run would re-execute the workflow; for v0.2 demo we
    # verify the cited hash matches the file on disk — proving the
    # graph's claim about the artifact is accurate.
    current_hash = sha256(Path(out_path))
    if current_hash == recorded_hash:
        results.append((did, "verified", recorded_hash, current_hash))
        print(f"  ✓ {did}")
        print(f"      hash: {current_hash[:16]}... (matches recorded)")
    else:
        results.append((did, "mismatch", recorded_hash, current_hash))
        print(f"  ✗ {did}: HASH MISMATCH")
        print(f"      recorded: {recorded_hash[:16]}...")
        print(f"      observed: {current_hash[:16]}...")

# Summary
verified = sum(1 for _, status, _, _ in results if status == "verified")
mismatch = sum(1 for _, status, _, _ in results if status == "mismatch")
missing = sum(1 for _, status, _, _ in results if status == "missing")
total = len(results)
rate = (verified / total * 100) if total else 0

print()
print(f"━━━ Existing-artifact hash summary ━━━")
print(f"  total derivatives:  {total}")
print(f"  verified:           {verified}")
print(f"  hash mismatches:    {mismatch}")
print(f"  missing on disk:    {missing}")
print(f"  artifact match rate: {rate:.1f}%")

# Write a verification report
report = {
    "check-type": "existing-artifact-hash-consistency",
    "total": total,
    "verified": verified,
    "mismatch": mismatch,
    "missing": missing,
    "verifiability-rate-pct": rate,
    "per-derivative": [
        {"id": did, "status": status, "recorded-hash": rh, "observed-hash": oh}
        for did, status, rh, oh in results
    ],
}
report_path = ROOT / "verification-report.json"
report_path.write_text(json.dumps(report, indent=2))
print(f"\nReport written: {report_path}")

sys.exit(0 if mismatch == 0 and missing == 0 else 1)
