#!/usr/bin/env python3
"""Glimmer CLI — single entry point for querying, authoring, validating, and verifying RO-KBs.

Install as:
    pip install -e .
or invoke directly:
    python -m glimmer.tools.cli <subcommand> [args]
"""

import argparse
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).parent


def _run(module_relpath, argv):
    """Re-exec the named tool with argv. Avoids re-implementing each tool's CLI."""
    import runpy
    script = TOOLS_DIR / module_relpath
    if not script.exists():
        print(f"error: tool not found: {script}", file=sys.stderr)
        sys.exit(2)
    sys.argv = [str(script)] + argv
    runpy.run_path(str(script), run_name="__main__")


def _planned(cmd, note):
    """Honest stub for a documented-but-not-yet-packaged command."""
    print(f"glimmer {cmd}: not yet available as a packaged command.", file=sys.stderr)
    print(f"  {note}", file=sys.stderr)
    sys.exit(2)


def _forward_module(module_main, argv):
    rc = module_main(argv)
    if rc:
        sys.exit(rc)


def cmd_validate(args):
    """Validate a Glimmer RO-KB against the schema."""
    argv = [args.path]
    if args.strict:
        argv.append("--strict")
    if args.as_json:
        argv.append("--json")
    _run("validate.py", argv)


def cmd_query_passthrough(op, extra_argv):
    from glimmer.tools.query import main as query_main
    _forward_module(query_main, [op] + extra_argv)


def cmd_sync_passthrough(op, extra_argv):
    from glimmer.tools.sync import main as sync_main
    _forward_module(sync_main, [op] + extra_argv)


def cmd_install_skill(extra_argv):
    from glimmer.tools.skill_installer import main as installer_main
    _forward_module(installer_main, extra_argv)


def _run_args(args, mode):
    argv = [args.rokb, args.node_id, "--mode", mode]
    if args.manifest:      argv += ["--manifest", args.manifest]
    if args.write_verdict: argv += ["--write-verdict"]
    if args.offline:       argv += ["--offline"]
    if args.no_container:  argv += ["--no-container"]
    if args.no_gate:       argv += ["--no-gate"]
    if args.run_root:      argv += ["--run-root", args.run_root]
    return argv


def cmd_run(args):
    """Forward-execute a run-record: gate inputs, replay the command, record outputs."""
    _run("run.py", _run_args(args, "run"))


def cmd_rerun(args):
    """Reproduce a run-record: re-execute and verify outputs per its tier."""
    _run("run.py", _run_args(args, "reproduce"))


def _add_run_flags(p):
    p.add_argument("--run-root", help="explicit project working directory")
    p.add_argument("rokb", help="path to an RO-KB directory")
    p.add_argument("node_id", help="run-record id, or 'all'")
    p.add_argument("--manifest", default=None, help="write the provenance manifest JSON here")
    p.add_argument("--write-verdict", action="store_true", help="write gate + verdict back into sidecars")
    p.add_argument("--offline", action="store_true", help="do not datalad-get missing inputs")
    p.add_argument("--no-container", action="store_true", help="run on the host instead of the pinned container")
    p.add_argument("--no-gate", action="store_true", help="skip the standards gate (flagged dirty)")


def cmd_build(args):
    """Build a Glimmer RO-KB from typed source data."""
    _planned("build",
             "Worked examples build with their own emitter — e.g. "
             "`python examples/ds000114-nipype/emit_graph.py`. Use `glimmer init` to bootstrap a new RO-KB.")


def cmd_agent(args):
    """Run the reference QC agent over a Glimmer RO-KB."""
    _planned("agent", "The reference agent SDK is planned (see docs/roadmap.md).")


def cmd_score(args):
    """Score agent verdicts against human ratings (Cohen's κ matrix)."""
    _planned("score", "Verdict scoring ships with the agent SDK (see docs/roadmap.md).")


def cmd_figure(args):
    """Regenerate the schema diagram figure."""
    _run("figure_schema.py", [])


def cmd_import_bids(args):
    """Import an existing BIDS dataset into Glimmer (planned)."""
    _planned("import-bids", "Planned for the interop bridge. See docs/interop.md.")


def cmd_export_rocrate(args):
    """Export a Glimmer RO-KB as RO-Crate for archival (planned)."""
    _planned("export-rocrate", "Planned for the interop bridge. See docs/interop.md.")


def cmd_version(args):
    """Print the Glimmer schema version this checkout implements."""
    version_file = TOOLS_DIR.parent / "schema" / "glimmer-version"
    print(version_file.read_text(encoding="utf-8").strip())


PASSTHROUGH_QUERY = {"summary", "query", "neighbors", "search"}
PASSTHROUGH_SYNC = {"sync", "status", "init", "hash", "amend", "migrate-references"}


def main(argv=None):
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    # Fast passthrough for subcommands with their own full argparse trees so `--help`
    # works cleanly per subcommand without duplicating option definitions.
    if raw_argv:
        cmd = raw_argv[0]
        if cmd in PASSTHROUGH_QUERY:
            cmd_query_passthrough(cmd, raw_argv[1:])
            return
        if cmd in PASSTHROUGH_SYNC:
            cmd_sync_passthrough(cmd, raw_argv[1:])
            return
        if cmd == "install-skill":
            cmd_install_skill(raw_argv[1:])
            return

    ap = argparse.ArgumentParser(
        prog="glimmer",
        description="Glimmer — research-object knowledge base for AI-native scientific workflows.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="<subcommand>")

    # Documented passthrough commands (for top-level `glimmer --help`)
    sub.add_parser("summary", help="summarize an RO-KB (counts, hubs, freshness)")
    sub.add_parser("query", help="filter nodes by type, frontmatter fields, and edges (metadata-only by default)")
    sub.add_parser("neighbors", help="traverse N-hop neighborhood around a node (metadata-only by default)")
    sub.add_parser("search", help="BM25 search over node sidecars and Markdown bodies")
    sub.add_parser("sync", help="refresh body hashes, rebuild enriched _glimmer-index.json, and validate")
    sub.add_parser("status", help="check hash, index, validation, and draft/artifact drift")
    sub.add_parser("init", help="bootstrap a fresh Glimmer RO-KB")
    sub.add_parser("hash", help="print sha256:<hex> for a file")
    sub.add_parser("amend", help="scaffold a dated amendment record for an evolving method node")
    sub.add_parser("migrate-references", help="tag or convert external publication nodes (dry-run by default)")
    sub.add_parser("install-skill", help="install the packaged Glimmer Agent Skill into a project or user home")

    p = sub.add_parser("validate", help="validate a Glimmer RO-KB against the schema")
    p.add_argument("path", help="path to an RO-KB directory")
    p.add_argument("--strict", action="store_true", help="enable extra advisory checks")
    p.add_argument("--json", action="store_true", dest="as_json", help="emit machine-readable JSON")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("run", help="forward-execute a run-record (gate → replay → record)")
    _add_run_flags(p)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("rerun", help="reproduce a run-record (re-execute + verify per tier)")
    _add_run_flags(p)
    p.set_defaults(func=cmd_rerun)

    p = sub.add_parser("figure", help="regenerate the schema diagram figure")
    p.set_defaults(func=cmd_figure)

    p = sub.add_parser("version", help="print the Glimmer schema version")
    p.set_defaults(func=cmd_version)

    p = sub.add_parser("build", help="build a Glimmer RO-KB from typed source data (planned)")
    p.add_argument("--example", help="build the named worked example", default=None)
    p.add_argument("--output", help="output directory for the RO-KB", default=None)
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("agent", help="run the reference QC agent over an RO-KB (planned)")
    p.add_argument("--model", default="anthropic/claude-opus-4", help="LLM identifier")
    p.add_argument("--informed", action="store_true", help="include peer QC artifacts as evidence")
    p.add_argument("--output", help="path to write verdict JSON", default=None)
    p.set_defaults(func=cmd_agent)

    p = sub.add_parser("score", help="score agent verdicts against human ratings (planned)")
    p.add_argument("--verdicts", required=True)
    p.add_argument("--fig-out", default=None)
    p.set_defaults(func=cmd_score)

    p = sub.add_parser("import-bids", help="import a BIDS dataset into Glimmer (planned)")
    p.add_argument("path", help="BIDS dataset root")
    p.set_defaults(func=cmd_import_bids)

    p = sub.add_parser("export-rocrate", help="export a Glimmer RO-KB as RO-Crate (planned)")
    p.add_argument("path", help="RO-KB root")
    p.set_defaults(func=cmd_export_rocrate)

    args = ap.parse_args(raw_argv)
    args.func(args)


if __name__ == "__main__":
    main()
