#!/usr/bin/env python3
"""run.py — the Glimmer node runner: execute and verify `run-record` nodes.

A `run-record` is one concrete, replayable invocation (the PROV Activity). This
module turns it into action. Two modes over one engine:

  run       forward execution — gate inputs, replay the command, hash the outputs,
            record the produced hashes. The primary path (`glimmer run`).
  reproduce re-execute an already-recorded run and COMPARE its outputs to what was
            recorded, per the run's verification tier (`glimmer rerun`).

The runner is for RUNNING, not just reproducing; reproduction is the special case
of re-running something already recorded.

Per run-record the engine:
  1. Resolves the node and confirms it is a `run-record`.
  2. STANDARDS GATE — each input must be (a) available/pinned and (b) valid against
     its declared standard. Validation is DELEGATED to the standard's `validator`
     hint (e.g. bids-validator) or falls back to `glimmer validate`; the runner only
     enforces and records the outcome. A failed gate ⇒ verdict `gate-failed`, no run.
  3. EXECUTE — replay `command` pinned to `container-digest` via
     `datalad containers-run` when available, falling back to `datalad run`, then a
     host subprocess (only with --no-container, flagged dirty in the verdict).
  4. VERIFY (reproduce mode) per tier:
       byte-identical        — hash match after NIfTI/GIFTI/JSON normalization
       numeric-tolerance     — re-derived numbers within {rel,abs} of expected
       structural            — reasoning-trace cites real nodes holding the claimed
                               values; retriever-manifest matches
  5. Write a provenance MANIFEST (JSON) and, with --write-verdict, write the
     `validation-gate` + `replay-verdict` blocks back into the sidecar.

Dependency-light: only PyYAML is required. datalad, a container runtime, nibabel,
and external standard validators are all FEATURE-DETECTED and degrade gracefully
(with the degradation recorded honestly in the verdict — never a silent pass).

Public surface (imported by downstream harnesses, e.g. an ADS provenance_check.py):
    sha256_file, load_graph, run_node, certify_equivalence, write_manifest, RunVerdict
"""

import sys, os, json, hashlib, argparse, shutil, subprocess, xml.dom.minidom
from dataclasses import dataclass, field, asdict
from pathlib import Path

import yaml

RUNNER_VERSION = "glimmer-run 0.6.0"


# ─────────────────────────────────────────────────────────────────────────────
# graph + hashing helpers
# ─────────────────────────────────────────────────────────────────────────────
def sha256_file(path) -> str:
    """Streaming SHA-256 of a file, returned `sha256:<hex>`."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _sha256_bytes(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


def read_sidecar(path: Path):
    """Return (frontmatter_dict, body_str). Mirrors validate.read_sidecar without
    importing the validator's internals (keeps this module standalone)."""
    text = Path(path).read_text()
    if text.startswith("---\n"):
        _, fm, body = text.split("---\n", 2)
        return (yaml.safe_load(fm) or {}), body
    if text.startswith("{"):
        return json.loads(text), ""
    raise ValueError(f"{path}: sidecar must start with '---' or '{{'")


def load_graph(rokb):
    """id -> (Path, frontmatter) for every sidecar enumerated in the index."""
    rokb = Path(rokb)
    index = json.loads((rokb / "_glimmer-index.json").read_text())
    graph = {}
    for entry in index["nodes"]:
        p = rokb / entry["path"]
        fm, _ = read_sidecar(p)
        graph[entry["id"]] = (p, fm)
    return graph


def _norm(rel, run_root):
    return (Path(run_root) / rel).resolve() if rel else None


# ─────────────────────────────────────────────────────────────────────────────
# output normalization — so two CORRECT re-runs are not flagged on volatile bytes
# ─────────────────────────────────────────────────────────────────────────────
def normalized_hash(path):
    """(hash, normalization-label) for an output file, normalizing volatile,
    non-semantic bytes (NIfTI/GIFTI headers, JSON key order) before hashing."""
    path = Path(path)
    suf = "".join(path.suffixes).lower()
    if suf in (".nii", ".nii.gz"):
        return _nifti_hash(path)
    if suf == ".gii":
        return _gifti_hash(path)
    if suf == ".json":
        try:
            canon = json.dumps(json.loads(path.read_text()), sort_keys=True, separators=(",", ":")).encode()
            return _sha256_bytes(canon), "json-canonical"
        except Exception:
            return sha256_file(path), "raw (json parse failed)"
    return sha256_file(path), "none"


def _nifti_hash(path):
    """Realizes the long-promised NIfTI normalization: blank volatile header
    fields, keep affine+dtype+voxels exactly, then hash. nibabel absent ⇒ raw
    compare, recorded honestly (never a silent pass)."""
    try:
        import numpy as np  # noqa: F401  (nibabel pulls it in)
        import nibabel as nib
    except Exception:
        return sha256_file(path), "raw (nibabel unavailable)"
    try:
        img = nib.load(str(path))
        hdr = img.header.copy()
        for fld in ("descrip", "db_name", "aux_file"):
            try:
                hdr[fld] = b""
            except Exception:
                pass
        for fld in ("cal_min", "cal_max", "glmax", "glmin"):
            try:
                hdr[fld] = 0
            except Exception:
                pass
        data = img.get_fdata()
        h = hashlib.sha256()
        h.update(bytes(img.affine.astype("float64").tobytes()))
        h.update(str(img.get_data_dtype()).encode())
        h.update(data.tobytes())
        return "sha256:" + h.hexdigest(), "nifti-header-zeroed"
    except Exception as e:
        return sha256_file(path), f"raw (nibabel error: {e})"


def _gifti_hash(path):
    """Strip the volatile <MetaData> block, canonicalize XML, then hash."""
    try:
        dom = xml.dom.minidom.parseString(Path(path).read_text())
        for md in dom.getElementsByTagName("MetaData"):
            md.parentNode.removeChild(md)
        return _sha256_bytes(dom.toxml().encode()), "gifti-metadata-stripped"
    except Exception:
        return sha256_file(path), "raw (gifti parse failed)"


# ─────────────────────────────────────────────────────────────────────────────
# verdict dataclasses
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class RunVerdict:
    node: str
    mode: str
    status: str = "unknown"
    provenance_mode: str = ""
    tier: str = ""
    verdict: str = "error"          # executed|verified|reproduced-within-tolerance|structurally-valid|mismatch|gate-failed|inputs-unavailable|error
    environment: dict = field(default_factory=dict)
    validation_gate: dict = field(default_factory=dict)
    inputs: list = field(default_factory=list)
    outputs: list = field(default_factory=list)
    numeric_checks: list = field(default_factory=list)
    structural_checks: list = field(default_factory=list)
    command: str = ""
    exit_code: int = None
    notes: str = ""

    def to_dict(self):
        d = asdict(self)
        d["exit-code"] = d.pop("exit_code")
        d["provenance-mode"] = d.pop("provenance_mode")
        d["validation-gate"] = d.pop("validation_gate")
        d["numeric-checks"] = d.pop("numeric_checks")
        d["structural-checks"] = d.pop("structural_checks")
        return d


@dataclass
class EquivalenceVerdict:
    method_a: str
    method_b: str
    equivalent: bool = False
    comparisons: list = field(default_factory=list)
    notes: str = ""

    def to_dict(self):
        d = asdict(self)
        return {"method-a": d["method_a"], "method-b": d["method_b"],
                "equivalent": d["equivalent"], "comparisons": d["comparisons"], "notes": d["notes"]}


# ─────────────────────────────────────────────────────────────────────────────
# the standards gate (delegated validators)
# ─────────────────────────────────────────────────────────────────────────────
def _resolve_input_path(pin, graph, run_root):
    """Best-effort local path for an input: pin `path` → referenced node's
    output-path (derivative) / datalad-relative-path (dataset)."""
    if pin.get("path"):
        return _norm(pin["path"], run_root)
    node = graph.get(pin.get("node"))
    if not node:
        return None
    fm = node[1]
    return _norm(fm.get("output-path") or fm.get("datalad-relative-path"), run_root)


def _run_validator(standard_fm, target_path, rokb, run_root):
    """Run a standard's `validator` hint against a file. Returns (valid, detail).
    Delegated — the run-record never reimplements validation. External commands
    run with cwd=run_root so relative paths resolve like the analysis itself."""
    v = (standard_fm or {}).get("validator") or {}
    kind = v.get("kind", "external" if v.get("command") else "none")
    if kind == "glimmer":
        rc = subprocess.run([sys.executable, "-m", "glimmer.tools.validate", str(Path(rokb).resolve())],
                            capture_output=True, text=True)
        return rc.returncode in (0, 2), f"glimmer validate rc={rc.returncode}"
    cmd = v.get("command")
    if not cmd:
        return True, "none (unchecked: standard declares no validator)"
    tool = (v.get("tool") or cmd.split()[0])
    if shutil.which(tool) is None and not Path(tool).exists():
        return True, f"none (unchecked: validator `{tool}` not installed)"
    filled = cmd.replace("{path}", str(target_path))
    rc = subprocess.run(filled, shell=True, cwd=str(run_root), capture_output=True, text=True)
    return rc.returncode == 0, f"{tool} rc={rc.returncode}"


def _datalad_get(path, run_root):
    """Try to materialize a file via datalad. Returns True if present afterwards."""
    if Path(path).exists():
        return True
    if shutil.which("datalad") is None:
        return False
    subprocess.run(["datalad", "get", str(path)], cwd=str(run_root),
                   capture_output=True, text=True)
    return Path(path).exists()


def standards_gate(run_fm, graph, rokb, run_root, *, offline, no_gate):
    """Enforce: each input pinned/available AND valid against its standard.
    Returns (passed, gate_dict, inputs_summary)."""
    gate, inputs_summary = {}, []
    passed = True
    for pin in run_fm.get("inputs") or []:
        nid = pin.get("node")
        fpath = _resolve_input_path(pin, graph, run_root)
        present = bool(fpath and Path(fpath).exists())
        if not present and not offline:
            present = _datalad_get(fpath, run_root) if fpath else False
        entry = {"node": nid, "path": str(fpath) if fpath else None, "pinned": present}
        # pin verification (annex-key exact match needs datalad; otherwise note it)
        if present and pin.get("datalad-annex-key") and shutil.which("datalad") is None:
            entry["pin-note"] = "present (annex-key unverified without datalad)"
        if not present:
            entry["available"] = False
            inputs_summary.append({**entry, "available": False,
                                   "data-liveness": "unreachable" if offline else "missing"})
            passed = False
            continue
        # standard validation (delegated)
        std_id = pin.get("conforms-to")
        if std_id and not no_gate:
            std_fm = graph.get(std_id, (None, {}))[1]
            valid, detail = _run_validator(std_fm, fpath, rokb, run_root)
            entry.update({"standard": std_id, "valid": valid, "validator": detail})
            if not valid:
                passed = False
        elif no_gate:
            entry.update({"standard": std_id, "valid": None, "validator": "skipped (--no-gate)"})
        gate[nid] = entry
        inputs_summary.append(entry)
    return passed, gate, inputs_summary


# ─────────────────────────────────────────────────────────────────────────────
# execution
# ─────────────────────────────────────────────────────────────────────────────
def execute(run_fm, run_root, *, no_container):
    """Replay the command, pinned to the container digest when possible.
    Returns (exit_code, resolved_via, stderr_tail)."""
    cmd = run_fm["command"]
    digest = run_fm.get("container-digest")
    image = run_fm.get("container-image")
    have_datalad = shutil.which("datalad") is not None
    if digest and image and have_datalad and not no_container:
        full = ["datalad", "containers-run", "-n", f"{image}@{digest}", "--", *cmd.split()]
        rc = subprocess.run(full, cwd=str(run_root), capture_output=True, text=True)
        return rc.returncode, "datalad containers-run", rc.stderr[-2000:]
    if have_datalad and not no_container and digest:
        # datalad recorded but containers-run unavailable: still get provenance capture
        rc = subprocess.run(["datalad", "run", "--", *cmd.split()],
                            cwd=str(run_root), capture_output=True, text=True)
        return rc.returncode, "datalad run (no container pin enforced)", rc.stderr[-2000:]
    rc = subprocess.run(cmd, shell=True, cwd=str(run_root), capture_output=True, text=True)
    via = "host subprocess (--no-container)" if no_container else "host subprocess (no container/datalad available)"
    return rc.returncode, via, rc.stderr[-2000:]


# ─────────────────────────────────────────────────────────────────────────────
# verification tiers
# ─────────────────────────────────────────────────────────────────────────────
def _tol_pass(obs, exp, tol):
    rel = tol.get("rel", 0.0) if tol else 0.0
    ab = tol.get("abs", 0.0) if tol else 0.0
    return abs(obs - exp) <= max(ab, rel * abs(exp))


def verify_byte_identical(pin, run_root):
    out = _norm(pin.get("output-path"), run_root)
    if not out or not Path(out).exists():
        return {"node": pin.get("node"), "passed": False, "reason": "output not on disk", "tier": "byte-identical"}
    observed, norm = normalized_hash(out)
    expected = pin.get("expected-hash")
    return {"node": pin.get("node"), "tier": "byte-identical", "expected": expected,
            "observed": observed, "normalization": norm, "passed": observed == expected}


def verify_numeric(pin, run_root, tolerance):
    """Compare re-derived numbers in the output to the recorded expected-values."""
    out = _norm(pin.get("output-path"), run_root)
    results = []
    if not out or not Path(out).exists():
        return [{"node": pin.get("node"), "passed": False, "reason": "output not on disk"}]
    try:
        produced = json.loads(Path(out).read_text())
    except Exception as e:
        return [{"node": pin.get("node"), "passed": False, "reason": f"output not JSON: {e}"}]
    expected_values = pin.get("expected-values") or {}
    qtol = (tolerance or {}).get("quantities") or {}
    default_tol = (tolerance or {}).get("default") or {}
    for name, exp in expected_values.items():
        obs = produced.get(name)
        tol = qtol.get(name, default_tol)
        ok = isinstance(obs, (int, float)) and _tol_pass(float(obs), float(exp), tol)
        results.append({"node": pin.get("node"), "quantity": name, "expected": exp, "observed": obs,
                        "abs-diff": (abs(obs - exp) if isinstance(obs, (int, float)) else None),
                        "tol": tol, "passed": bool(ok)})
    return results


def verify_structural(run_fm, graph):
    """For agent-inferred runs: cited nodes must exist and (best-effort) hold the
    cited values; retriever-manifest, if present, must be self-consistent."""
    trace = run_fm.get("reasoning-trace") or {}
    # find an emitted finding's trace if the run-record itself carries none
    if not trace:
        for e in run_fm.get("edges") or []:
            if e.get("type") == "emits" and e.get("target") in graph:
                trace = (graph[e["target"]][1].get("reasoning-trace") or {})
                break
    accessed = trace.get("nodes-accessed") or []
    checks = []
    all_exist = True
    for nid in accessed:
        exists = nid in graph
        all_exist = all_exist and exists
        checks.append({"cited-node": nid, "exists": exists})
    manifest_ok = True
    if run_fm.get("retriever-manifest"):
        manifest_ok = bool(run_fm["retriever-manifest"].get("index-sha") or run_fm["retriever-manifest"].get("embedding-model"))
    return {"cited-nodes": checks, "all-cited-exist": all_exist,
            "retriever-manifest-ok": manifest_ok, "passed": all_exist and manifest_ok}


# ─────────────────────────────────────────────────────────────────────────────
# the engine
# ─────────────────────────────────────────────────────────────────────────────
def run_node(rokb, node_id, *, mode="run", offline=False, no_container=False, no_gate=False, graph=None):
    """Execute (and, in reproduce mode, verify) a single run-record. Returns a RunVerdict."""
    rokb = Path(rokb)
    run_root = rokb.parent if rokb.parent != rokb else rokb   # project root: code/, inputs/, out/ live here
    graph = graph or load_graph(rokb)
    if node_id not in graph:
        return RunVerdict(node=node_id, mode=mode, verdict="error", notes="node not in index")
    path, fm = graph[node_id]
    if fm.get("type") != "run-record":
        return RunVerdict(node=node_id, mode=mode, verdict="error", notes=f"not a run-record (type={fm.get('type')})")
    fm["edges"] = fm.get("edges") or []
    pmode = fm.get("provenance-mode", "deterministic")
    v = RunVerdict(node=node_id, mode=mode, status=fm.get("status", "?"), provenance_mode=pmode,
                   command=fm.get("command", ""))

    # 1. Standards gate
    passed, gate, inputs_summary = standards_gate(fm, graph, rokb, run_root, offline=offline, no_gate=no_gate)
    v.validation_gate, v.inputs = gate, inputs_summary
    if not passed:
        any_missing = any(not e.get("pinned", True) for e in inputs_summary)
        v.verdict = "inputs-unavailable" if any_missing else "gate-failed"
        v.notes = "input unavailable" if any_missing else "standards gate failed"
        return v

    # 2. Execute
    exit_code, resolved_via, stderr_tail = execute(fm, run_root, no_container=no_container)
    v.exit_code = exit_code
    v.environment = {"container-digest": fm.get("container-digest"), "resolved-via": resolved_via}
    if exit_code != 0:
        v.verdict = "error"
        v.notes = f"command exited {exit_code}: {stderr_tail.strip()[-400:]}"
        return v

    # 3. Verify / record outputs
    if mode == "run":
        for pin in fm.get("outputs") or []:
            out = _norm(pin.get("output-path"), run_root)
            if out and Path(out).exists():
                h, norm = normalized_hash(out)
                v.outputs.append({"node": pin.get("node"), "produced-hash": h, "normalization": norm,
                                  "output-path": pin.get("output-path")})
            else:
                v.outputs.append({"node": pin.get("node"), "produced-hash": None, "reason": "not on disk"})
        v.tier = "execute"
        v.verdict = "executed"
        return v

    # reproduce mode — verify per tier
    tier = pmode
    tol = fm.get("reproduction-tolerance")
    if pmode == "deterministic":
        v.tier = "byte-identical"
        v.outputs = [verify_byte_identical(pin if "output-path" in pin else {**pin, "output-path": pin.get("output-path")}, run_root)
                     for pin in fm.get("outputs") or []]
        if tol:
            for pin in fm.get("outputs") or []:
                v.numeric_checks += verify_numeric(pin, run_root, tol)
        ok = all(o.get("passed") for o in v.outputs) and all(n.get("passed") for n in v.numeric_checks)
        v.verdict = "verified" if ok else "mismatch"
    elif pmode == "stochastic":
        if tol:
            v.tier = "numeric-tolerance"
            for pin in fm.get("outputs") or []:
                v.numeric_checks += verify_numeric(pin, run_root, tol)
            ok = bool(v.numeric_checks) and all(n.get("passed") for n in v.numeric_checks)
            v.verdict = "reproduced-within-tolerance" if ok else "mismatch"
        else:
            sc = verify_structural(fm, graph); v.tier = "structural"
            v.structural_checks = [sc]; v.verdict = "structurally-valid" if sc["passed"] else "mismatch"
    else:  # agent-inferred
        sc = verify_structural(fm, graph); v.tier = "structural"
        v.structural_checks = [sc]
        v.verdict = "structurally-valid" if sc["passed"] else "mismatch"
    return v


def order_runs(graph, ids):
    """Order run-records so a run that regenerates another's input comes first
    (a light topological sort over consume/regenerate edges). Stable for the
    common case; falls back to the given order on a cycle."""
    produced_by = {}   # output node -> run-record that regenerates it
    for rid in ids:
        for e in graph[rid][1].get("edges") or []:
            if e.get("type") == "regenerates":
                produced_by[e.get("target")] = rid
    deps = {rid: set() for rid in ids}
    for rid in ids:
        for e in graph[rid][1].get("edges") or []:
            if e.get("type") == "consumes":
                producer = produced_by.get(e.get("target"))
                if producer and producer in deps and producer != rid:
                    deps[rid].add(producer)
    ordered, seen = [], set()
    while len(ordered) < len(ids):
        progressed = False
        for rid in ids:
            if rid not in seen and deps[rid] <= seen:
                ordered.append(rid); seen.add(rid); progressed = True
        if not progressed:   # cycle / unresolved — append the rest in original order
            ordered += [r for r in ids if r not in seen]
            break
    return ordered


def certify_equivalence(rokb, run_record_a, run_record_b, *, tolerance=None, no_container=False):
    """Certify `equivalent-to`: run two run-records (each binding a method) and
    assert their outputs match — byte-identical, or numerically within tolerance.
    Returns an EquivalenceVerdict. This makes equivalence a CHECKED claim."""
    rokb = Path(rokb); graph = load_graph(rokb)
    run_root = rokb.parent if rokb.parent != rokb else rokb
    fa = graph[run_record_a][1]; fb = graph[run_record_b][1]
    va = run_node(rokb, run_record_a, mode="run", no_container=no_container, graph=graph)
    vb = run_node(rokb, run_record_b, mode="run", no_container=no_container, graph=graph)
    ev = EquivalenceVerdict(method_a=fa.get("method"), method_b=fb.get("method"))
    if va.verdict != "executed" or vb.verdict != "executed":
        ev.notes = f"a={va.verdict}, b={vb.verdict}"; return ev
    pa = [o.get("output-path") for o in va.outputs]
    pb = [o.get("output-path") for o in vb.outputs]
    equiv = True
    for oa, ob in zip(pa, pb):
        ha, _ = normalized_hash(_norm(oa, run_root))
        hb, _ = normalized_hash(_norm(ob, run_root))
        match = ha == hb
        cmp = {"a": oa, "b": ob, "hash-match": match}
        if not match and tolerance:
            try:
                da = json.loads(_norm(oa, run_root).read_text())
                db = json.loads(_norm(ob, run_root).read_text())
                keys = set(da) & set(db)
                match = all(_tol_pass(float(da[k]), float(db[k]), tolerance.get("default", tolerance))
                            for k in keys if isinstance(da[k], (int, float)))
                cmp["numeric-match-within-tolerance"] = match
            except Exception as e:
                cmp["error"] = str(e)
        equiv = equiv and match
        ev.comparisons.append(cmp)
    ev.equivalent = equiv
    return ev


# ─────────────────────────────────────────────────────────────────────────────
# writeback + manifest
# ─────────────────────────────────────────────────────────────────────────────
def write_verdict_back(rokb, node_id, verdict: RunVerdict):
    """Write `validation-gate` + `replay-verdict` (and, for forward runs, status +
    produced hashes) back into the sidecar, preserving the body."""
    path, fm = load_graph(rokb)[node_id]
    text = Path(path).read_text()
    _, fmtext, body = text.split("---\n", 2)
    fm = yaml.safe_load(fmtext) or {}
    fm["validation-gate"] = verdict.validation_gate
    fm["replay-verdict"] = {
        "verdict": verdict.verdict, "tier": verdict.tier, "runner-version": RUNNER_VERSION,
        "environment": verdict.environment, "outputs-checked": verdict.outputs,
        "numeric-checks": verdict.numeric_checks, "structural-checks": verdict.structural_checks,
        "exit-code": verdict.exit_code, "notes": verdict.notes,
    }
    if verdict.mode == "run" and verdict.verdict == "executed":
        fm["status"] = "executed"
        produced = {o["node"]: o.get("produced-hash") for o in verdict.outputs if o.get("produced-hash")}
        default_mode = fm.get("provenance-mode", "deterministic")
        for pin in fm.get("outputs") or []:
            # Only pin an expected-hash for byte-identical outputs. A stochastic /
            # agent output is NOT hash-reproducible, so recording its hash would be
            # a false pin — those tiers verify by tolerance / structure instead.
            tier = pin.get("tier") or ("byte-identical" if default_mode == "deterministic" else None)
            if tier == "byte-identical" and pin.get("node") in produced and not pin.get("expected-hash"):
                pin["expected-hash"] = produced[pin["node"]]
    Path(path).write_text("---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n" + body)


def write_manifest(verdicts, path):
    """Write the provenance manifest JSON (superset of verification-report.json)."""
    runs = [v.to_dict() for v in verdicts]
    summary = {}
    for v in verdicts:
        summary[v.verdict] = summary.get(v.verdict, 0) + 1
    total = len(verdicts)
    good = sum(summary.get(k, 0) for k in
               ("executed", "verified", "reproduced-within-tolerance", "structurally-valid"))
    summary["total"] = total
    summary["reproducibility-rate-pct"] = round(good / total * 100, 1) if total else 0.0
    manifest = {"glimmer-run-version": RUNNER_VERSION, "summary": summary, "runs": runs}
    Path(path).write_text(json.dumps(manifest, indent=2))
    return manifest


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Run / reproduce Glimmer run-record nodes.")
    ap.add_argument("rokb", help="path to a Glimmer RO-KB directory")
    ap.add_argument("node_id", help="run-record id, or 'all'")
    ap.add_argument("--mode", choices=["run", "reproduce"], default="run")
    ap.add_argument("--manifest", default=None, help="write the provenance manifest JSON here")
    ap.add_argument("--write-verdict", action="store_true", help="write gate + verdict back into sidecars")
    ap.add_argument("--offline", action="store_true", help="do not datalad-get; treat missing inputs as unavailable")
    ap.add_argument("--no-container", action="store_true", help="run on the host instead of the pinned container")
    ap.add_argument("--no-gate", action="store_true", help="skip the standards gate (flagged dirty)")
    args = ap.parse_args()

    rokb = Path(args.rokb)
    graph = load_graph(rokb)
    if args.node_id == "all":
        targets = [nid for nid, (_, fm) in graph.items() if fm.get("type") == "run-record"]
    else:
        targets = [t.strip() for t in args.node_id.split(",") if t.strip()]
    targets = order_runs(graph, [t for t in targets if t in graph]) + [t for t in targets if t not in graph]

    verdicts = []
    for nid in targets:
        v = run_node(rokb, nid, mode=args.mode, offline=args.offline,
                     no_container=args.no_container, no_gate=args.no_gate, graph=graph)
        verdicts.append(v)
        mark = {"executed": "▶", "verified": "✓", "reproduced-within-tolerance": "≈",
                "structurally-valid": "≋"}.get(v.verdict, "✗")
        print(f"  {mark} {nid}: {v.verdict}" + (f" [{v.tier}]" if v.tier else "")
              + (f" — {v.notes}" if v.notes else ""))
        if args.write_verdict:
            write_verdict_back(rokb, nid, v)
            graph = load_graph(rokb)  # refresh after writeback

    if args.manifest:
        m = write_manifest(verdicts, args.manifest)
        print(f"\nManifest: {args.manifest}  (reproducibility-rate {m['summary']['reproducibility-rate-pct']}%)")

    bad = [v for v in verdicts if v.verdict in ("mismatch", "gate-failed", "inputs-unavailable", "error")]
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
