#!/usr/bin/env python3
"""Portable wrapper for the Glimmer CLI.

Resolves `glimmer` in order:
  1. `glimmer` executable on PATH
  2. `python3 -m glimmer.tools.cli` (when installed in current environment)
  3. Local checkout or vendored `vendor/glimmer/glimmer/tools/cli.py`
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys


def main() -> int:
    args = sys.argv[1:]
    exe = shutil.which("glimmer")
    if exe:
        return subprocess.call([exe, *args])

    probe = subprocess.run(
        [sys.executable, "-c", "import glimmer.tools.cli"],
        capture_output=True,
    )
    if probe.returncode == 0:
        return subprocess.call([sys.executable, "-m", "glimmer.tools.cli", *args])

    cwd = Path.cwd().resolve()
    candidates = [
        cwd / "glimmer" / "tools" / "cli.py",
        cwd / "vendor" / "glimmer" / "glimmer" / "tools" / "cli.py",
        Path(__file__).resolve().parents[3] / "glimmer" / "tools" / "cli.py",
    ]
    for cli in candidates:
        if cli.is_file():
            env = dict(os.environ)
            repo_root = str(cli.parents[2])
            env["PYTHONPATH"] = repo_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
            return subprocess.call([sys.executable, str(cli), *args], env=env)

    print(
        "glimmer CLI not found. Install with `pip install git+https://github.com/hebbianloop/glimmer.git` "
        "or run from a checkout containing `glimmer/tools/cli.py`.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
