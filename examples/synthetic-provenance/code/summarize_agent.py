#!/usr/bin/env python3
"""Scripted structural-verification fixture. This is not an LLM agent.

Copies numeric observations into an explicit evidence trace. The verifier checks
those observations against the pinned input files; it does not validate prose.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

mean_path, accuracy_path, out = map(Path, sys.argv[1:])
mean = json.loads(mean_path.read_text())['mean-signal']
accuracy = json.loads(accuracy_path.read_text())['classifier-accuracy']
trace = {
    'nodes-accessed': ['derivative-synth-mean', 'derivative-synth-accuracy'],
    'metrics-cited': {
        'mean-signal': {'node': 'derivative-synth-mean', 'value': mean},
        'classifier-accuracy': {'node': 'derivative-synth-accuracy', 'value': accuracy},
    },
    'evidence-summary': 'Synthetic mean and jittered accuracy copied from the two input files.',
    'model-identifier': 'synthetic/scripted-summary-1',
    'timestamp': datetime.now(timezone.utc).isoformat(),
}
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({'interpretation': f'Synthetic mean {mean:.3f}; toy accuracy {accuracy:.4f}.',
                           'reasoning-trace': trace}, indent=2) + '\n')
