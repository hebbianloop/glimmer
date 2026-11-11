#!/usr/bin/env python3
"""Run the installed CLI on a freshly generated fixture, outside the source tree."""
import json
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
rokb = root / 'rokb'


def call(args, expected=(0,)):
    result = subprocess.run(args, cwd=root, capture_output=True, text=True)
    print(result.stdout, end='')
    if result.returncode not in expected:
        raise SystemExit(f'Unexpected exit {result.returncode}: {args}\n{result.stderr}')


call([sys.executable, str(root / 'emit_graph.py')])
call(['glimmer', 'validate', str(rokb)], expected=(0, 2))
positive = 'run-synth-mean,run-synth-mean-fast,run-synth-classifier'
call(['glimmer', 'rerun', str(rokb), positive, '--no-container', '--offline', '--manifest', str(root / 'manifest.json')])
summary = json.loads((root / 'manifest.json').read_text())['summary']
assert summary['reproduction'] == {'normalized-match': 2, 'reproduced-within-tolerance': 1}, summary
call([sys.executable, str(root / 'emit_graph.py'), '--pin-summary-inputs'])
call(['glimmer', 'rerun', str(rokb), 'run-synth-agent-summary', '--no-container', '--offline', '--manifest', str(root / 'summary-manifest.json')])
assert json.loads((root / 'summary-manifest.json').read_text())['summary']['reproduction'] == {'structurally-valid': 1}
call(['glimmer', 'run', str(rokb), 'run-synth-gate-fail', '--no-container', '--offline'], expected=(1,))
assert not (root / 'out/mean_bad.json').exists()
call(['glimmer', 'run', str(rokb), 'run-synth-mean', '--offline'], expected=(1,))
print('PASS: installed CLI, four positive cases, malformed-input rejection and no implicit host fallback.')
