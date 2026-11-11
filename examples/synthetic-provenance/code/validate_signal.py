#!/usr/bin/env python3
"""Delegated validator for `standard-synth-signal-v1`.

The runner's standards gate calls this (via the standard's `validator` hint) on
each input that declares `conforms-to: standard-synth-signal-v1`. It is a STUB
standing in for a real domain validator (e.g. bids-validator): exit 0 ⇒ conformant,
non-zero ⇒ the run-record's gate fails and the command never executes.

Conformance rule (v1): the file is JSON with `glimmer-signal-format == "v1"` and a
non-empty numeric `values` list.
"""
import json, sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    doc = json.loads(path.read_text())
except Exception as e:
    print(f"INVALID: not JSON: {e}"); sys.exit(1)

if doc.get("glimmer-signal-format") != "v1":
    print("INVALID: missing/!= `glimmer-signal-format: v1`"); sys.exit(1)
vals = doc.get("values")
if not isinstance(vals, list) or not vals or not all(isinstance(v, (int, float)) for v in vals):
    print("INVALID: `values` must be a non-empty numeric list"); sys.exit(1)
print("VALID: conforms to standard-synth-signal-v1")
sys.exit(0)
