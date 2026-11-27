#!/usr/bin/env python3
"""Install the packaged Glimmer Agent Skill (`skills/glimmer/`) into a project or user home.

Compatible with Antigravity / universal `.agents/skills/glimmer`, Claude Code
(`.claude/skills/glimmer`), and Codex (`.codex/skills/glimmer`).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
from typing import Optional


def locate_packaged_skill() -> Path:
    """Locate the canonical `skills/glimmer` directory from a checkout or installed wheel."""
    # 1. Source checkout / editable install: <repo>/skills/glimmer
    repo_candidate = Path(__file__).resolve().parents[2] / "skills" / "glimmer"
    if (repo_candidate / "SKILL.md").is_file():
        return repo_candidate
    # 2. Installed package bundle: glimmer/_skills/glimmer
    pkg_candidate = Path(__file__).resolve().parent.parent / "_skills" / "glimmer"
    if (pkg_candidate / "SKILL.md").is_file():
        return pkg_candidate
    raise FileNotFoundError(
        "Packaged Glimmer skill not found (checked repo `skills/glimmer` and `glimmer/_skills/glimmer`)."
    )


def resolve_target_dir(
    *,
    target: Optional[Path] = None,
    project: Path = Path("."),
    global_install: bool = False,
    claude: bool = False,
    codex: bool = False,
) -> Path:
    if target is not None:
        t = Path(target).expanduser()
        return t if t.name == "glimmer" else t / "glimmer"
    base = Path.home() if global_install else Path(project).resolve()
    if claude:
        return base / ".claude" / "skills" / "glimmer"
    if codex:
        return base / ".codex" / "skills" / "glimmer"
    return base / ".agents" / "skills" / "glimmer"


def install_skill(
    *,
    target: Optional[Path] = None,
    project: Path = Path("."),
    global_install: bool = False,
    claude: bool = False,
    codex: bool = False,
    symlink: bool = False,
    force: bool = False,
) -> Path:
    src = locate_packaged_skill().resolve()
    dest = resolve_target_dir(
        target=target,
        project=project,
        global_install=global_install,
        claude=claude,
        codex=codex,
    )
    if dest.exists() or dest.is_symlink():
        if not force:
            raise FileExistsError(f"Destination already exists: {dest} (pass --force to replace)")
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        else:
            shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if symlink:
        dest.symlink_to(src, target_is_directory=True)
    else:
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
    return dest


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Install the Glimmer Agent Skill into a project or global skills directory.")
    ap.add_argument("--target", type=Path, default=None, help="explicit target directory (e.g. .agents/skills/glimmer)")
    ap.add_argument("--project", type=Path, default=Path("."), help="project root for relative installs (default: current dir)")
    ap.add_argument("--global", dest="global_install", action="store_true", help="install under user home (~/.agents/skills/glimmer, etc.)")
    ap.add_argument("--claude", action="store_true", help="install to .claude/skills/glimmer")
    ap.add_argument("--codex", action="store_true", help="install to .codex/skills/glimmer")
    ap.add_argument("--symlink", action="store_true", help="symlink instead of copying")
    ap.add_argument("--force", action="store_true", help="overwrite an existing installation")
    args = ap.parse_args(argv)
    try:
        dest = install_skill(
            target=args.target,
            project=args.project,
            global_install=args.global_install,
            claude=args.claude,
            codex=args.codex,
            symlink=args.symlink,
            force=args.force,
        )
    except (FileNotFoundError, FileExistsError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    mode = "Symlinked" if args.symlink else "Installed"
    print(f"{mode} Glimmer skill -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
