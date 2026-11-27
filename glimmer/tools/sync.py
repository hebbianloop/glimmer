#!/usr/bin/env python3
"""Low-friction RO-KB maintenance: init, sync, status, hash, amend, migrate-references.

Design rules:
  - Zero heavy dependencies (stdlib + PyYAML).
  - Never modifies original source files or `sources/**/SHA256SUMS`.
  - Progressive, non-blocking ergonomics by default; `--check` / `--strict` for CI gates.
  - Emits backwards-compatible enriched `_glimmer-index.json` entries (preserving `{id, type, path}`).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Optional

import yaml

from glimmer.tools.query import extract_status, extract_subtype, extract_summary
from glimmer.tools.validate import (
    iter_sidecar_paths,
    load_schema,
    read_sidecar,
    validate,
)


DEFAULT_WATCH_DIRS = ("writing", "exports", "artifacts", "manuscript", "drafts", "papers")
ARTIFACT_EXTENSIONS = {".pdf", ".docx", ".doc", ".tex", ".md", ".txt", ".csv", ".tsv", ".png", ".svg", ".json", ".bib"}
AMENDMENTS_DIRNAME = "_glimmer-amendments"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_body_hash(body: str) -> str:
    """Exact SHA-256 hex digest of a Markdown sidecar's body string."""
    return hashlib.sha256((body or "").encode("utf-8")).hexdigest()


def _hashes_match(recorded: Any, actual_hex: str) -> bool:
    if not isinstance(recorded, str) or not recorded.strip():
        return False
    rec = recorded.strip()
    if rec.startswith("sha256:"):
        rec = rec[len("sha256:"):]
    return rec == actual_hex


def _write_md_sidecar(path: Path, fm: dict, body: str) -> None:
    dumped = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)
    path.write_text(f"---\n{dumped}---\n{body}", encoding="utf-8")


def _schema_version() -> str:
    vfile = Path(__file__).parent.parent / "schema" / "glimmer-version"
    return vfile.read_text(encoding="utf-8").strip() if vfile.is_file() else "0.7.0"


def _normalize_edges(edges: Any) -> list[dict]:
    out = []
    for e in (edges or []):
        if isinstance(e, dict) and e.get("type") and e.get("target"):
            out.append({"type": str(e["type"]), "target": str(e["target"])})
    return out


def build_index_entry(rokb: Path, path: Path, fm: dict, body: str) -> dict:
    """Build one enriched `_glimmer-index.json` node record (superset of {id, type, path})."""
    entry: dict[str, Any] = {
        "id": fm["id"],
        "type": fm["type"],
        "path": path.relative_to(rokb).as_posix(),
        "name": fm.get("name", fm["id"]),
    }
    status = extract_status(fm)
    if status:
        entry["status"] = status
    subtype = extract_subtype(fm)
    if subtype:
        entry["subtype"] = subtype
    if fm.get("claim-kind"):
        entry["claim-kind"] = str(fm["claim-kind"])
    if fm.get("role"):
        entry["role"] = str(fm["role"])
    if fm.get("modified") is not None:
        entry["modified"] = str(fm["modified"])
    if fm.get("provenance-hash"):
        entry["provenance-hash"] = str(fm["provenance-hash"])
    summary = extract_summary(fm, body)
    if summary:
        entry["summary"] = summary
    entry["edges"] = _normalize_edges(fm.get("edges"))
    return entry


def build_enriched_index(rokb: Path, existing: Optional[dict] = None, *, generated_at: Optional[str] = None) -> dict:
    rokb = Path(rokb)
    existing = existing or {}
    entries = []
    program_ids = []
    for path in iter_sidecar_paths(rokb):
        try:
            fm, body = read_sidecar(path)
        except ValueError:
            continue
        if not fm.get("id") or not fm.get("type"):
            continue
        entries.append(build_index_entry(rokb, path, fm, body))
        if fm["type"] == "program":
            program_ids.append(fm["id"])

    entries.sort(key=lambda r: (r["path"], r["id"]))
    ver = _schema_version()
    index: dict[str, Any] = {
        "schema": f"glimmer/v{ver}",
        "dataset-name": existing.get("dataset-name") or rokb.resolve().name,
    }
    if existing.get("default-domain"):
        index["default-domain"] = existing["default-domain"]
    if existing.get("description"):
        index["description"] = existing["description"]
    if existing.get("upstream-graph"):
        index["upstream-graph"] = existing["upstream-graph"]
    if existing.get("created"):
        index["created"] = existing["created"]
    root_node = existing.get("root-node") or (program_ids[0] if len(program_ids) == 1 else None)
    if root_node and any(e["id"] == root_node for e in entries):
        index["root-node"] = root_node
    if existing.get("entrypoints"):
        valid_ids = {e["id"] for e in entries}
        kept_eps = [
            ep for ep in existing["entrypoints"]
            if (ep.get("id") if isinstance(ep, dict) else ep) in valid_ids
        ]
        if kept_eps:
            index["entrypoints"] = kept_eps
    index["generated-at"] = generated_at or _utc_now_iso()
    index["node-count"] = len(entries)
    index["nodes"] = entries
    return index


def _project_root_for(rokb: Path) -> Path:
    rokb = Path(rokb).resolve()
    if (rokb / "workspace.json").is_file():
        return rokb
    if rokb.parent != rokb and (
        (rokb.parent / "workspace.json").is_file()
        or any((rokb.parent / d).is_dir() for d in DEFAULT_WATCH_DIRS)
        or (rokb.parent / ".git").exists()
    ):
        return rokb.parent
    return rokb


def _parse_iso_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _detect_workspace_drift(
    rokb: Path,
    *,
    watch_dirs: Optional[list[str]] = None,
    workspace_manifest: Optional[Path] = None,
    newest_node_dt: Optional[datetime] = None,
    referenced_paths: Optional[set[str]] = None,
) -> dict:
    project_root = _project_root_for(rokb)
    rokb_resolved = rokb.resolve()
    index_path = rokb_resolved / "_glimmer-index.json"
    baseline_dt = newest_node_dt
    if index_path.is_file():
        idx_dt = datetime.fromtimestamp(index_path.stat().st_mtime, tz=timezone.utc)
        if baseline_dt is None or idx_dt > baseline_dt:
            baseline_dt = idx_dt

    manifest_path = workspace_manifest or (project_root / "workspace.json")
    registered_artifacts: set[str] = set()
    if manifest_path.is_file():
        try:
            ws = json.loads(manifest_path.read_text(encoding="utf-8"))
            for art in ws.get("artifacts") or []:
                if isinstance(art, dict) and art.get("path"):
                    registered_artifacts.add(Path(art["path"]).as_posix())
        except Exception:
            pass

    dirs_to_scan = list(watch_dirs) if watch_dirs else list(DEFAULT_WATCH_DIRS)
    newer_files: list[dict] = []
    unregistered_artifacts: list[str] = []
    max_drift_days = 0.0
    ref_paths = referenced_paths or set()

    for rel_dir in dirs_to_scan:
        d = (project_root / rel_dir).resolve()
        if not d.is_dir():
            continue
        # Skip scanning inside the RO-KB itself
        if d == rokb_resolved or rokb_resolved in d.parents:
            continue
        for p in sorted(d.rglob("*")):
            if not p.is_file() or p.name.startswith("."):
                continue
            rel = p.relative_to(project_root).as_posix()
            # Skip built workspace bundles (derived output, not authored drafts)
            parts = Path(rel).parts
            if any(seg in ("workspace", "workspace-checks", "node_modules", "__pycache__") for seg in parts):
                continue
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            if baseline_dt is not None and (mtime - baseline_dt).total_seconds() > 3600:
                delta_days = round((mtime - baseline_dt).total_seconds() / 86400.0, 1)
                max_drift_days = max(max_drift_days, delta_days)
                newer_files.append({"path": rel, "modified": mtime.strftime("%Y-%m-%dT%H:%M:%SZ"), "days_newer": delta_days})
            if p.suffix.lower() in ARTIFACT_EXTENSIONS and p.name.lower() != "readme.md":
                if rel not in registered_artifacts and rel not in ref_paths:
                    unregistered_artifacts.append(rel)

    git_dirty: list[str] = []
    try:
        proc = subprocess.run(
            ["git", "-C", str(project_root), "--no-optional-locks", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0:
            git_dirty = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    except (OSError, subprocess.TimeoutExpired):
        pass

    return {
        "project-root": str(project_root),
        "baseline-timestamp": baseline_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if baseline_dt else None,
        "max-drift-days": max_drift_days,
        "newer-files": newer_files,
        "unregistered-artifacts": unregistered_artifacts,
        "workspace-manifest": str(manifest_path) if manifest_path.is_file() else None,
        "git-dirty": git_dirty[:30],
    }


def status_rokb(
    rokb: Path,
    *,
    watch_dirs: Optional[list[str]] = None,
    workspace_manifest: Optional[Path] = None,
    strict: bool = False,
) -> dict:
    rokb = Path(rokb)
    index_path = rokb / "_glimmer-index.json"
    existing_index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else None

    hash_drift: list[dict] = []
    newest_dt: Optional[datetime] = None
    referenced_paths: set[str] = set()
    on_disk_ids: set[str] = set()

    for path in iter_sidecar_paths(rokb):
        try:
            fm, body = read_sidecar(path)
        except ValueError:
            continue
        nid = fm.get("id")
        if nid:
            on_disk_ids.add(nid)
        if path.suffix == ".md":
            actual = compute_body_hash(body)
            recorded = fm.get("provenance-hash")
            if not _hashes_match(recorded, actual):
                hash_drift.append({
                    "id": nid or path.name,
                    "path": path.relative_to(rokb).as_posix(),
                    "recorded": recorded,
                    "actual": actual,
                })
        dt = _parse_iso_dt(fm.get("modified"))
        if dt and (newest_dt is None or dt > newest_dt):
            newest_dt = dt
        for ref in (fm.get("upstream-refs") or []):
            if isinstance(ref, str) and not ref.startswith(("http://", "https://")):
                referenced_paths.add(ref)
        if isinstance(fm.get("output-path"), str):
            referenced_paths.add(fm["output-path"])

    expected_index = build_enriched_index(rokb, existing_index, generated_at="CHECK")
    index_enriched = False
    index_stale = False
    if existing_index and isinstance(existing_index.get("nodes"), list):
        index_enriched = all(isinstance(r, dict) and "name" in r and "edges" in r for r in existing_index["nodes"]) if existing_index["nodes"] else True
        if existing_index.get("nodes") != expected_index["nodes"] or existing_index.get("node-count") != expected_index["node-count"]:
            index_stale = True
    else:
        index_stale = True

    schema = load_schema()
    errors, warnings = validate(rokb, schema, strict=strict)
    drift = _detect_workspace_drift(
        rokb,
        watch_dirs=watch_dirs,
        workspace_manifest=workspace_manifest,
        newest_node_dt=newest_dt,
        referenced_paths=referenced_paths,
    )

    clean = (
        not errors
        and not hash_drift
        and not index_stale
        and not drift["newer-files"]
    )
    return {
        "rokb": str(rokb),
        "node-count": len(on_disk_ids),
        "clean": clean,
        "hash-drift": hash_drift,
        "index": {
            "exists": index_path.is_file(),
            "enriched": index_enriched,
            "stale": index_stale,
        },
        "validation": {
            "error-count": len(errors),
            "warning-count": len(warnings),
            "errors": errors,
            "warnings": warnings,
        },
        "workspace-drift": drift,
    }


def sync_rokb(
    rokb: Path,
    *,
    check: bool = False,
    touch_modified: bool = False,
    build_workspace: bool = False,
    workspace_builder: Optional[Path] = None,
    strict: bool = False,
) -> dict:
    rokb = Path(rokb)
    index_path = rokb / "_glimmer-index.json"
    existing_index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else {}

    updated_hashes: list[str] = []
    now_iso = _utc_now_iso()

    for path in iter_sidecar_paths(rokb):
        if path.suffix != ".md":
            continue
        try:
            fm, body = read_sidecar(path)
        except ValueError:
            continue
        actual = compute_body_hash(body)
        if not _hashes_match(fm.get("provenance-hash"), actual):
            updated_hashes.append(path.relative_to(rokb).as_posix())
            if not check:
                fm["provenance-hash"] = actual
                if touch_modified:
                    fm["modified"] = now_iso
                _write_md_sidecar(path, fm, body)

    new_index = build_enriched_index(rokb, existing_index, generated_at=now_iso)
    old_nodes = existing_index.get("nodes") if isinstance(existing_index, dict) else None
    index_changed = (
        old_nodes != new_index["nodes"]
        or existing_index.get("node-count") != new_index["node-count"]
        or existing_index.get("schema") != new_index["schema"]
        or not index_path.is_file()
    )
    if index_changed and not check:
        index_path.write_text(json.dumps(new_index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    schema = load_schema()
    errors, warnings = validate(rokb, schema, strict=strict)

    workspace_built = None
    if build_workspace and not check and not errors:
        project_root = _project_root_for(rokb)
        if workspace_builder:
            cmd = [sys.executable, str(workspace_builder), "--project", str(project_root / "workspace.json"), "--out", str(project_root / "exports/workspace")]
        elif (project_root / "scripts" / "build_workspace.py").is_file():
            cmd = [sys.executable, str(project_root / "scripts" / "build_workspace.py")]
        else:
            cmd = None
        if cmd:
            proc = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True)
            workspace_built = {
                "command": cmd,
                "returncode": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
            }
        else:
            workspace_built = {"skipped": "no workspace builder or scripts/build_workspace.py found"}

    return {
        "rokb": str(rokb),
        "mode": "check" if check else "sync",
        "updated-hashes": updated_hashes,
        "index-changed": index_changed,
        "node-count": new_index["node-count"],
        "errors": errors,
        "warnings": warnings,
        "workspace-build": workspace_built,
    }


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or "project"


def init_rokb(
    target: Path,
    *,
    dataset_name: Optional[str] = None,
    domain: Optional[str] = None,
    with_profile: bool = False,
    with_agents_snippet: bool = False,
) -> dict:
    rokb = Path(target)
    rokb.mkdir(parents=True, exist_ok=True)
    name = dataset_name or rokb.resolve().name
    slug = _slugify(name)
    now = _utc_now_iso()

    for subdir in ("concepts", "methods", "experiments", "datasets", "publications", "references", "standards", AMENDMENTS_DIRNAME):
        (rokb / subdir).mkdir(parents=True, exist_ok=True)

    created_files: list[str] = []
    program_id = f"program-{slug}"
    program_path = rokb / "index.md"
    if not program_path.exists():
        body = (
            f"\n# {name}\n\n"
            f"Research-object knowledge base initialized with Glimmer v{_schema_version()}.\n\n"
            "Add research questions and hypotheses under `concepts/`, external cited works under "
            "`references/`, project drafts under `publications/`, and methods/experiments under "
            "`methods/` and `experiments/`. Run `glimmer sync .` after authoring edits.\n"
        )
        fm: dict[str, Any] = {
            "id": program_id,
            "type": "program",
            "name": name,
            "created": now,
            "modified": now,
            "program-kind": "initiative",
            "status": "active",
            "edges": [],
            "provenance-hash": compute_body_hash(body),
        }
        _write_md_sidecar(program_path, fm, body)
        created_files.append("index.md")

    profile_name = domain or (slug if with_profile else None)
    if with_profile and profile_name:
        prof_dir = rokb / "_glimmer-profiles"
        prof_dir.mkdir(parents=True, exist_ok=True)
        prof_path = prof_dir / f"{profile_name}.yaml"
        if not prof_path.exists():
            prof_doc = {
                "profile": profile_name,
                "standard": f"{name} local research conventions",
                "version": "0.1",
                "status": "local",
                "description": f"Local domain profile for {name}. Add optional or required fields per core node type.",
                "augments": {
                    "concept": {
                        "optional": {
                            "claim-kind": "string",
                            "evidence-status": "string",
                            "design-status": "string",
                        }
                    }
                },
            }
            prof_path.write_text(yaml.safe_dump(prof_doc, sort_keys=False), encoding="utf-8")
            created_files.append(f"_glimmer-profiles/{profile_name}.yaml")

    existing = {
        "dataset-name": name,
        "created": now,
        "root-node": program_id,
    }
    if profile_name:
        existing["default-domain"] = profile_name
    index = build_enriched_index(rokb, existing, generated_at=now)
    (rokb / "_glimmer-index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    created_files.append("_glimmer-index.json")

    agents_path = None
    if with_agents_snippet:
        agents_path = rokb / "AGENTS.glimmer.md"
        agents_path.write_text(
            "# Glimmer RO-KB Protocol\n\n"
            "1. Orient first: `glimmer summary .` (or read `_glimmer-index.json`).\n"
            "2. Query safely (metadata-only by default): `glimmer query . --type concept` and "
            "`glimmer neighbors . <node-id> --hops 1`.\n"
            "3. Search prose: `glimmer search . \"<terms>\"`.\n"
            "4. Put external cited papers under `references/` (`type: reference`) with epistemic edges "
            "(`supports`, `challenges`, `contradicts`, `overlaps-with`, `extends`, `addresses-concept`).\n"
            "5. Put project outputs under `publications/` (`type: publication`, `role: project-output`).\n"
            "6. After edits, run `glimmer sync .` and check `glimmer status .` for draft/artifact drift.\n",
            encoding="utf-8",
        )
        created_files.append("AGENTS.glimmer.md")

    errors, warnings = validate(rokb, load_schema())
    return {
        "rokb": str(rokb),
        "dataset-name": name,
        "root-node": program_id,
        "default-domain": profile_name,
        "created-files": created_files,
        "errors": errors,
        "warnings": warnings,
    }


def hash_file(path: Path) -> str:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Not a file: {path}")
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def scaffold_amendment(rokb: Path, method_id: str, reason: str) -> dict:
    rokb = Path(rokb)
    index_path = rokb / "_glimmer-index.json"
    if index_path.is_file():
        idx = json.loads(index_path.read_text(encoding="utf-8"))
        known = {n["id"] for n in idx.get("nodes", []) if isinstance(n, dict) and n.get("id")}
        if method_id not in known:
            raise KeyError(f"Node `{method_id}` not found in {index_path}")
    amend_dir = rokb / AMENDMENTS_DIRNAME
    amend_dir.mkdir(parents=True, exist_ok=True)
    existing_nums = []
    for p in amend_dir.glob("AMEND-*.md"):
        m = re.match(r"AMEND-(\d+)", p.name)
        if m:
            existing_nums.append(int(m.group(1)))
    num = (max(existing_nums) + 1) if existing_nums else 1
    code = f"AMEND-{num:03d}"
    slug = _slugify(method_id)[:40]
    out_path = amend_dir / f"{code}-{slug}.md"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path.write_text(
        f"# {code}: Amendment to [[{method_id}]]\n\n"
        f"- **Date:** {today}\n"
        f"- **Target node:** `[[{method_id}]]`\n"
        f"- **Status:** proposed\n"
        f"- **Reason:** {reason}\n\n"
        "## Checklist before approval\n\n"
        f"1. Update `version` and `modified` in `[[{method_id}]]` (or create a superseding node with `refines` / `superseded-by`).\n"
        "2. Record reviewer / PI approval and effective date.\n"
        "3. Run `glimmer sync <rokb>` and `glimmer status <rokb>` to refresh hashes and index.\n",
        encoding="utf-8",
    )
    return {"code": code, "path": str(out_path), "method": method_id, "reason": reason}


def migrate_references(rokb: Path, *, mode: str = "role", apply: bool = False) -> dict:
    """Identify external `publication` nodes lacking local `cites-*`/`aggregates` edges and upgrade them.

    mode='role' (default): add `role: external-reference` (keeps `type: publication`, zero breaking changes).
    mode='type': convert `type: publication` -> `type: reference` (removes `role`).
    """
    if mode not in ("role", "type"):
        raise ValueError(f"Invalid mode {mode!r}; expected 'role' or 'type'")
    rokb = Path(rokb)
    candidates = []
    for path in iter_sidecar_paths(rokb):
        if path.suffix != ".md":
            continue
        try:
            fm, body = read_sidecar(path)
        except ValueError:
            continue
        if fm.get("type") != "publication":
            continue
        if fm.get("role") == "project-output":
            continue
        edges = fm.get("edges") or []
        edge_types = {e.get("type") for e in edges if isinstance(e, dict)}
        has_local_cites = any(t.startswith("cites") or t == "aggregates" for t in edge_types)
        if has_local_cites:
            continue
        if mode == "role" and fm.get("role") == "external-reference":
            continue
        candidates.append({"id": fm.get("id"), "path": path.relative_to(rokb).as_posix(), "action": mode})
        if apply:
            if mode == "role":
                fm["role"] = "external-reference"
            else:
                fm["type"] = "reference"
                fm.pop("role", None)
            fm["provenance-hash"] = compute_body_hash(body)
            _write_md_sidecar(path, fm, body)

    sync_res = sync_rokb(rokb, check=False) if (apply and candidates) else None
    return {
        "rokb": str(rokb),
        "mode": mode,
        "applied": apply,
        "count": len(candidates),
        "candidates": candidates,
        "sync": sync_res,
    }


def _print_status_text(st: dict) -> None:
    print(f"Glimmer status: {st['rokb']} ({st['node-count']} nodes)")
    idx = st["index"]
    print(f"  Index:      {'present' if idx['exists'] else 'MISSING'} | enriched={'yes' if idx['enriched'] else 'no'} | {'STALE (run glimmer sync)' if idx['stale'] else 'up to date'}")
    print(f"  Body hash:  {len(st['hash-drift'])} mismatch(es)")
    for h in st["hash-drift"][:10]:
        print(f"    ! {h['path']} ({h['id']})")
    val = st["validation"]
    print(f"  Validation: {val['error-count']} error(s), {val['warning-count']} warning(s)")
    drift = st["workspace-drift"]
    nf = drift["newer-files"]
    ua = drift["unregistered-artifacts"]
    print(f"  Draft/artifact drift (baseline {drift['baseline-timestamp'] or 'unknown'}):")
    if nf:
        print(f"    ! {len(nf)} file(s) newer than graph (max drift: {drift['max-drift-days']} days):")
        for item in nf[:12]:
            print(f"      - {item['path']} (+{item['days_newer']}d, {item['modified']})")
        if len(nf) > 12:
            print(f"      … and {len(nf) - 12} more")
    else:
        print("    ✓ no watched draft/export files newer than graph")
    if ua:
        print(f"    ! {len(ua)} unregistered file(s) in watched draft/export dirs:")
        for p in ua[:12]:
            print(f"      - {p}")
        if len(ua) > 12:
            print(f"      … and {len(ua) - 12} more")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Glimmer RO-KB authoring & maintenance tools.")
    sub = ap.add_subparsers(dest="op", required=True)

    p_sync = sub.add_parser("sync", help="refresh body hashes, rebuild enriched _glimmer-index.json, and validate")
    p_sync.add_argument("rokb", help="path to RO-KB directory")
    p_sync.add_argument("--check", "--dry-run", dest="check", action="store_true", help="check without writing; exit 1 if drift or errors")
    p_sync.add_argument("--touch-modified", action="store_true", help="update `modified` timestamp on sidecars whose body hash changed")
    p_sync.add_argument("--build-workspace", action="store_true", help="rebuild workspace bundle if configured")
    p_sync.add_argument("--workspace-builder", type=Path, default=None, help="explicit path to build_workspace.py")
    p_sync.add_argument("--strict", action="store_true", help="enable strict validator hints")
    p_sync.add_argument("--json", action="store_true", dest="as_json")

    p_st = sub.add_parser("status", help="check hash, index, validation, and project draft/artifact drift")
    p_st.add_argument("rokb", help="path to RO-KB directory")
    p_st.add_argument("--watch-dir", action="append", dest="watch_dirs", help="extra project-relative dir to scan for unindexed drafts/artifacts")
    p_st.add_argument("--workspace", type=Path, default=None, help="explicit path to workspace.json")
    p_st.add_argument("--strict", action="store_true")
    p_st.add_argument("--json", action="store_true", dest="as_json")

    p_init = sub.add_parser("init", help="bootstrap a fresh Glimmer RO-KB")
    p_init.add_argument("rokb", help="target RO-KB directory")
    p_init.add_argument("--name", default=None, help="dataset / project name")
    p_init.add_argument("--domain", default=None, help="default-domain profile name")
    p_init.add_argument("--with-profile", action="store_true", help="scaffold a local domain profile under _glimmer-profiles/")
    p_init.add_argument("--agents-snippet", action="store_true", help="write a starter AGENTS.glimmer.md protocol snippet")
    p_init.add_argument("--json", action="store_true", dest="as_json")

    p_hash = sub.add_parser("hash", help="print sha256:<hex> for a file")
    p_hash.add_argument("path", help="file to hash")

    p_amend = sub.add_parser("amend", help="scaffold a dated amendment record for an evolving method node")
    p_amend.add_argument("rokb", help="path to RO-KB directory")
    p_amend.add_argument("method_id", help="node id being amended")
    p_amend.add_argument("reason", help="concise rationale for the amendment")

    p_mig = sub.add_parser("migrate-references", help="tag or convert external publication nodes (dry-run by default)")
    p_mig.add_argument("rokb", help="path to RO-KB directory")
    p_mig.add_argument("--mode", choices=["role", "type"], default="role", help="'role' adds role: external-reference; 'type' converts to type: reference")
    p_mig.add_argument("--apply", action="store_true", help="write changes and re-sync index")
    p_mig.add_argument("--json", action="store_true", dest="as_json")

    args = ap.parse_args(argv)
    try:
        if args.op == "sync":
            res = sync_rokb(
                Path(args.rokb),
                check=args.check,
                touch_modified=args.touch_modified,
                build_workspace=args.build_workspace,
                workspace_builder=args.workspace_builder,
                strict=args.strict,
            )
            if args.as_json:
                print(json.dumps(res, indent=2, ensure_ascii=False))
            else:
                verb = "Would update" if args.check else "Updated"
                print(f"Glimmer {res['mode']}: {res['rokb']} ({res['node-count']} nodes)")
                print(f"  {verb} body hashes: {len(res['updated-hashes'])}")
                print(f"  Index {'needs refresh' if args.check and res['index-changed'] else ('updated' if res['index-changed'] else 'unchanged')}")
                print(f"  Validation: {len(res['errors'])} error(s), {len(res['warnings'])} warning(s)")
                for e in res["errors"]:
                    print(f"    ✗ {e}")
                for w in res["warnings"]:
                    print(f"    ! {w}")
                if res["workspace-build"]:
                    print(f"  Workspace build: {res['workspace-build']}")
            if res["errors"]:
                return 1
            if args.check and (res["updated-hashes"] or res["index-changed"]):
                return 1
            if res["warnings"]:
                return 2
            return 0

        if args.op == "status":
            st = status_rokb(
                Path(args.rokb),
                watch_dirs=args.watch_dirs,
                workspace_manifest=args.workspace,
                strict=args.strict,
            )
            if args.as_json:
                print(json.dumps(st, indent=2, ensure_ascii=False))
            else:
                _print_status_text(st)
            if st["validation"]["error-count"] > 0:
                return 1
            if st["hash-drift"] or st["index"]["stale"] or st["workspace-drift"]["newer-files"] or st["validation"]["warning-count"] > 0:
                return 2
            return 0

        if args.op == "init":
            res = init_rokb(
                Path(args.rokb),
                dataset_name=args.name,
                domain=args.domain,
                with_profile=args.with_profile,
                with_agents_snippet=args.agents_snippet,
            )
            if args.as_json:
                print(json.dumps(res, indent=2, ensure_ascii=False))
            else:
                print(f"Initialized Glimmer RO-KB at {res['rokb']} (root={res['root-node']})")
                for f in res["created-files"]:
                    print(f"  + {f}")
                print(f"Validation: {len(res['errors'])} error(s), {len(res['warnings'])} warning(s)")
            return 1 if res["errors"] else 0

        if args.op == "hash":
            print(hash_file(Path(args.path)))
            return 0

        if args.op == "amend":
            res = scaffold_amendment(Path(args.rokb), args.method_id, args.reason)
            print(f"Created {res['code']} at {res['path']}")
            return 0

        if args.op == "migrate-references":
            res = migrate_references(Path(args.rokb), mode=args.mode, apply=args.apply)
            if args.as_json:
                print(json.dumps(res, indent=2, ensure_ascii=False))
            else:
                prefix = "Migrated" if args.apply else "Dry-run: would migrate"
                print(f"{prefix} {res['count']} external publication node(s) using mode={res['mode']}:")
                for c in res["candidates"]:
                    print(f"  - {c['id']} ({c['path']})")
                if not args.apply and res["count"]:
                    print("Re-run with --apply to write changes and re-sync _glimmer-index.json.")
            return 0
    except (ValueError, KeyError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
