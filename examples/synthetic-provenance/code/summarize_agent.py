#!/usr/bin/env python3
"""AGENT-INFERRED method: an LLM-style summary over the two derivatives.

  python code/summarize_agent.py out/mean.json out/acc.json out/summary.json

Stands in for an agent that reads the mean + accuracy derivatives and writes an
interpretation. Its output is NOT verified by hashing (an agent's prose is not
byte-reproducible); instead the run-record carries `provenance-mode: agent-inferred`
and a `reasoning-trace`, and the STRUCTURAL tier checks that the cited nodes exist
and hold the claimed values — the honest analogue per docs/agent-protocol.md.
"""
import json, sys
from pathlib import Path

mean_p, acc_p, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
mean = json.loads(mean_p.read_text())["mean-signal"]
acc = json.loads(acc_p.read_text())["classifier-accuracy"]
interp = (f"Mean signal {mean:.3f} exceeds the 0.4 threshold and the classifier "
          f"reaches {acc:.2f} accuracy, jointly supporting the hypothesis.")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"interpretation": interp,
                           "based-on": ["derivative-synth-mean", "derivative-synth-accuracy"]}, indent=2) + "\n")
print(interp)
