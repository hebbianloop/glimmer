#!/usr/bin/env python3
"""An EQUIVALENT implementation of compute_mean — different code, same output.

  python code/compute_mean_fast.py inputs/signal.json out/mean_fast.json

Uses a single-pass accumulator instead of sum()/len(). `certify_equivalence`
runs this and compute_mean.py on the same input and confirms the outputs match,
so `method-numpy-mean-fast` can carry an `equivalent-to` edge that is CHECKED,
not merely asserted. This is the "equivalent f(x), cleaner/faster, tolerated"
case — the semantic pattern links back to the same registry method.
"""
import json, sys
from pathlib import Path

inp, out = Path(sys.argv[1]), Path(sys.argv[2])
total, n = 0.0, 0
for v in json.loads(inp.read_text())["values"]:
    total += v
    n += 1
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"mean-signal": total / n}, indent=2) + "\n")
print(f"mean-signal = {total / n}")
