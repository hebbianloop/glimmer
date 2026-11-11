#!/usr/bin/env python3
"""Write a small, fixed synthetic signal so the example needs no real data.

Output: inputs/signal.json — a tiny standard-conformant file:
  {"glimmer-signal-format": "v1", "values": [...]}
Deterministic: the values never change, so the downstream mean is reproducible.
"""
import json
from pathlib import Path

# A fixed, hand-chosen series (mean = 0.5 exactly). Pure stdlib, no numpy.
VALUES = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.5]

out = Path(__file__).resolve().parent.parent / "inputs" / "signal.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"glimmer-signal-format": "v1", "values": VALUES}, indent=2) + "\n")
print(f"wrote {out}")
