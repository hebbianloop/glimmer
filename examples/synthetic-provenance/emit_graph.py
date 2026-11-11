#!/usr/bin/env python3
"""Generate the entire synthetic graph from committed source, without cached outputs.

--pin-summary-inputs explicitly freezes the observed upstream products for the
next run. It does not certify how those products were generated.
"""
import argparse
import hashlib
import json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent
ROKB = ROOT / 'rokb'


def content_key(path):
    return f'SHA256E-s{path.stat().st_size}--{hashlib.sha256(path.read_bytes()).hexdigest()}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pin-summary-inputs', action='store_true')
    args = parser.parse_args()
    if args.pin_summary_inputs:
        path = ROKB / 'run-records/run-synth-agent-summary.md'
        _, text, body = path.read_text().split('---\n', 2)
        fm = yaml.safe_load(text)
        for pin in fm['inputs']:
            pin['datalad-annex-key'] = content_key(ROOT / pin['path'])
        fm['status'] = 'ready'
        for key in ('validation-gate', 'replay-verdict'):
            fm.pop(key, None)
        path.write_text('---\n' + yaml.safe_dump(fm, sort_keys=False) + '---\n' + body)
        print('Pinned current summary inputs; this does not certify upstream execution.')
        return
    nodes = []
    for entry in json.loads((ROOT / 'graph-template.json').read_text())['nodes']:
        fm = entry['frontmatter']
        if fm['type'] == 'run-record':
            for pin in fm['inputs']:
                if pin['path'].startswith('inputs/'):
                    pin['datalad-annex-key'] = content_key(ROOT / pin['path'])
        path = ROKB / entry['path']
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('---\n' + yaml.safe_dump(fm, sort_keys=False) + '---\n\nSynthetic verifier fixture; not empirical or LLM evaluation.\n')
        nodes.append({'id': fm['id'], 'type': fm['type'], 'path': entry['path']})
    profile = ROKB / '_glimmer-profiles/synthetic.yaml'
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text('profile: synthetic\nstandard: none\nstatus: local\naugments: {}\n')
    index = {'schema': 'glimmer/v0.6.0', 'dataset-name': 'synthetic-provenance',
             'default-domain': 'synthetic', 'node-count': len(nodes), 'nodes': sorted(nodes, key=lambda n: n['id'])}
    (ROKB / '_glimmer-index.json').write_text(json.dumps(index, indent=2) + '\n')
    print(f'Generated {len(nodes)} nodes from committed sources; no outputs executed.')


if __name__ == '__main__':
    main()
