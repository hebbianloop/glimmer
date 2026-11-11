"""Synthetic arithmetic and observable container-boundary probes, not research results."""
import argparse
import json
import math
import os
from pathlib import Path
import socket
import time

from check_values import load_values


def boundaries(input_path):
    checks = {'nonroot': os.geteuid() != 0,
              'other_project_absent': not Path('/var/lib/glimmer-other-project/marker.txt').exists(),
              'docker_socket_absent': not Path('/var/run/docker.sock').exists(),
              'expected_baseline_absent': not Path('/work/expected/summary.json').exists()}
    for name, path in [('root_readonly', Path('/glimmer-write-probe')),
                       ('input_readonly', input_path.parent / 'glimmer-write-probe'),
                       ('code_readonly', Path('/work/code/glimmer-write-probe'))]:
        try:
            path.write_text('probe')
            checks[name] = False
            path.unlink()
        except OSError:
            checks[name] = True
    try:
        with socket.create_connection(('198.51.100.1', 443), timeout=0.5):
            checks['external_connect_denied'] = False
    except OSError:
        checks['external_connect_denied'] = True
    print(json.dumps({'checks': checks, 'uid': os.geteuid()}, sort_keys=True), flush=True)
    if not all(checks.values()):
        raise RuntimeError('a fixture isolation check failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--mode', choices=['ok', 'fail', 'missing', 'timeout'], default='ok')
    args = parser.parse_args()
    boundaries(args.input)
    if args.mode == 'fail': raise SystemExit(23)
    if args.mode == 'timeout': time.sleep(300)
    values = load_values(args.input)
    total = math.fsum(values)
    data = {'count': len(values), 'mean': total / len(values), 'sum': total}
    payload = json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n'
    args.output.mkdir(exist_ok=True)
    (args.output / 'raw.json').write_text(payload)
    if args.mode != 'missing': (args.output / 'numeric.json').write_text(payload)


if __name__ == '__main__': main()
