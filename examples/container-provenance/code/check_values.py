"""The fixture's explicit input standard; run by the trusted host-side gate."""
import json
import math
from pathlib import Path
import sys


def load_values(path):
    raw = Path(path).read_bytes()
    if len(raw) > 65536:
        raise ValueError('input exceeds the fixture size limit')
    obj = json.loads(raw)
    if not isinstance(obj, dict) or set(obj) != {'values'}:
        raise ValueError('expected exactly one values field')
    values = obj['values']
    if not isinstance(values, list) or not 1 <= len(values) <= 100:
        raise ValueError('expected 1–100 values')
    if any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1e6 for v in values):
        raise ValueError('values must be finite bounded numbers')
    return values


if __name__ == '__main__':
    load_values(sys.argv[1])
