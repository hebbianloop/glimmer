#!/usr/bin/env python3
"""DETERMINISTIC method: mean of the synthetic signal.

  python code/compute_mean.py inputs/signal.json out/mean.json

Writes {"mean-signal": <mean>}. Running it twice on the same input yields a
matching canonical JSON content — the normalized-content verification tier.
"""
import json, sys
from pathlib import Path

inp, out = Path(sys.argv[1]), Path(sys.argv[2])
values = json.loads(inp.read_text())["values"]
mean = sum(values) / len(values)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"mean-signal": mean}, indent=2) + "\n")
print(f"mean-signal = {mean}")
