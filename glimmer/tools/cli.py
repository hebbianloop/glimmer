#!/usr/bin/env python3
"""Glimmer CLI — single entry point for build / validate / agent / score / import.

Install as:
    pip install -e .   # (when packaged)
or invoke directly:
    python -m glimmer.tools.cli <subcommand> [args]
"""

import argparse, sys, os
from pathlib import Path

TOOLS_DIR = Path(__file__).parent


def _run(module_relpath, argv):
    """Re-exec the named tool with argv. Avoids re-implementing each tool's CLI."""
    import runpy
    script = TOOLS_DIR / module_relpath
    if not script.exists():
        print(f"error: tool not found: {script}", file=sys.stderr); sys.exit(2)
    sys.argv = [str(script)] + argv
    runpy.run_path(str(script), run_name="__main__")


def _planned(cmd, note):
    """Honest stub for a documented-but-not-yet-packaged command."""
    print(f"glimmer {cmd}: not yet available as a packaged command.", file=sys.stderr)
    print(f"  {note}", file=sys.stderr)
    sys.exit(2)


def cmd_build(args):
    """Build a Glimmer RO-KB from typed source data."""
    _planned("build",
             "Worked examples build with their own emitter — e.g. "
             "`python examples/ds000114-nipype/emit_graph.py`. A general builder is planned (roadmap v0.4).")


def cmd_validate(args):
    """Validate a Glimmer RO-KB against the schema."""
    _run("validate.py", [args.path])


def cmd_agent(args):
    """Run the reference QC agent over a Glimmer RO-KB."""
    _planned("agent", "The reference agent SDK is planned for roadmap v0.5 (see docs/roadmap.md).")


def cmd_score(args):
    """Score agent verdicts against human ratings (Cohen's κ matrix)."""
    _planned("score", "Verdict scoring ships with the agent SDK (roadmap v0.5).")


def cmd_figure(args):
    """Regenerate the schema diagram figure."""
    _run("figure_schema.py", [])


def cmd_import_bids(args):
    """Import an existing BIDS dataset into Glimmer (planned for v0.2)."""
    _planned("import-bids", "Planned for the interop bridge (roadmap v0.2). See docs/interop.md.")


def cmd_export_rocrate(args):
    """Export a Glimmer RO-KB as RO-Crate for archival (planned for v0.2)."""
    _planned("export-rocrate", "Planned for the interop bridge (roadmap v0.2). See docs/interop.md.")


def cmd_version(args):
    """Print the Glimmer schema version this checkout implements."""
    version_file = TOOLS_DIR.parent / "schema" / "glimmer-version"
    print(version_file.read_text().strip())


def main():
    ap = argparse.ArgumentParser(
        prog="glimmer",
        description="Glimmer — research-object knowledge base for AI-native scientific workflows.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="<subcommand>")

    p = sub.add_parser("build", help="build a Glimmer RO-KB from typed source data")
    p.add_argument("--example", help="build the named worked example", default=None)
    p.add_argument("--output", help="output directory for the RO-KB", default=None)
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("validate", help="validate a Glimmer RO-KB against the schema")
    p.add_argument("path", help="path to an RO-KB directory")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("agent", help="run the reference QC agent over an RO-KB")
    p.add_argument("--model", default="anthropic/claude-opus-4", help="LLM identifier")
    p.add_argument("--informed", action="store_true", help="include peer QC artifacts as evidence")
    p.add_argument("--output", help="path to write verdict JSON", default=None)
    p.set_defaults(func=cmd_agent)

    p = sub.add_parser("score", help="score agent verdicts against human ratings (Cohen's κ)")
    p.add_argument("--verdicts", required=True)
    p.add_argument("--fig-out", default=None)
    p.set_defaults(func=cmd_score)

    p = sub.add_parser("figure", help="regenerate the schema diagram figure")
    p.set_defaults(func=cmd_figure)

    p = sub.add_parser("import-bids", help="import a BIDS dataset into Glimmer (v0.2)")
    p.add_argument("path", help="BIDS dataset root")
    p.set_defaults(func=cmd_import_bids)

    p = sub.add_parser("export-rocrate", help="export a Glimmer RO-KB as RO-Crate (v0.2)")
    p.add_argument("path", help="RO-KB root")
    p.set_defaults(func=cmd_export_rocrate)

    p = sub.add_parser("version", help="print the Glimmer schema version")
    p.set_defaults(func=cmd_version)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
