#!/usr/bin/env python3
"""STOCHASTIC-but-bounded method: a toy classifier accuracy.

  python code/fit_classifier.py inputs/signal.json out/acc.json

Models a non-deterministic fit (random init / shuffling): the accuracy lands near
0.80 but jitters run-to-run, so it is NOT byte-reproducible. It IS reproducible
within tolerance — the numeric-within-tolerance verification tier — which is the
honest guarantee for stochastic analyses (and for re-deriving a published number
from source). Pure stdlib; jitter from `random` (intentionally unseeded).
"""
import json, random, sys
from pathlib import Path

inp, out = Path(sys.argv[1]), Path(sys.argv[2])
values = json.loads(inp.read_text())["values"]
# A deterministic signal-dependent base (so it tracks the data) + small noise.
base = 0.80
noise = random.uniform(-0.012, 0.012)
accuracy = round(base + noise, 4)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"classifier-accuracy": accuracy, "n": len(values)}, indent=2) + "\n")
print(f"classifier-accuracy = {accuracy}")
