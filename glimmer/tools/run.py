#!/usr/bin/env python3
"""Execute trusted local research-object run records and report bounded checks.

Inputs must match their content pins and declared validators must be available.
Registered DataLad container image files are hash-checked before invocation;
unpinned host execution requires --no-container. Commands/validators are argv
strings, not implicit shell programs. Use an explicit shell when needed.

Output checks distinguish raw byte identity, normalized content, finite numeric
agreement and structural citation/value checks. Structural success does not
verify scientific interpretation. See docs/proactive-provenance.md for the
supported formats, migration requirements and untested integration boundaries.
"""

import sys, os, json, hashlib, argparse, shutil, subprocess, xml.dom.minidom
import io, math, re, shlex
from dataclasses import dataclass, field, asdict
from pathlib import Path

import yaml

RUNNER_VERSION = "glimmer-run 0.6.0-hardening"
SUCCESS = {"executed", "verified", "normalized-match", "reproduced-within-tolerance", "structurally-valid", "checks-passed"}


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
        if entry["id"] in graph or fm.get("id") != entry["id"]:
            raise ValueError("duplicate index ID or sidecar ID mismatch")
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
    suf = path.name.lower()
    if suf.endswith((".nii", ".nii.gz")):
        return _nifti_hash(path)
    if suf.endswith(".gii"):
        return _gifti_hash(path)
    if suf.endswith(".json"):
        try:
            canon = json.dumps(json.loads(path.read_text()), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            return _sha256_bytes(canon), "json-canonical"
        except Exception:
            return sha256_file(path), "raw (json parse failed)"
    return sha256_file(path), "none"


def _nifti_hash(path):
    """Hash declared header fields, extensions, scaling and exact stored voxels.

    Avoid get_fdata(): converting int64 voxels to float64 can erase differences.
    Unavailable normalization is reported as a raw fallback, never acceptance.
    """
    try:
        import numpy as np
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
        proxy = img.dataobj
        data = proxy.get_unscaled() if hasattr(proxy, "get_unscaled") else np.asanyarray(proxy)
        h = hashlib.sha256()
        h.update(hdr.binaryblock)
        h.update(str(img.shape).encode())
        h.update(bytes(img.affine.astype("float64").tobytes()))
        h.update(str(img.get_data_dtype()).encode())
        h.update(repr((getattr(proxy, "slope", 1.0), getattr(proxy, "inter", 0.0))).encode())
        for extension in hdr.extensions:
            serialized = io.BytesIO()
            extension.write_to(serialized, byteswap=sys.byteorder == "big")
            h.update(serialized.getvalue())
        h.update(data.tobytes())
        return "sha256:" + h.hexdigest(), "nifti-header-zeroed"
    except Exception as e:
        return sha256_file(path), f"raw (nibabel error: {e})"


def _gifti_hash(path):
    """Serialize XML while retaining metadata with possible scientific meaning."""
    try:
        dom = xml.dom.minidom.parseString(Path(path).read_text())
        # Metadata may carry anatomical/coordinate semantics; retain it.
        return _sha256_bytes(dom.toxml().encode()), "gifti-xml-serialized"
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
    """A declared standard needs an available validator; unchecked is a failure."""
    validator = standard_fm.get("validator") or {}
    if not isinstance(validator, dict):
        return False, "invalid validator declaration"
    if validator.get("kind") == "glimmer":
        rc = subprocess.run([sys.executable, str(Path(__file__).with_name("validate.py")),
                             str(Path(rokb).resolve())], capture_output=True, text=True)
        return rc.returncode in (0, 2), f"graph schema only: rc={rc.returncode}"
    command = validator.get("command")
    if not isinstance(command, str) or not command.strip():
        return False, "standard has no executable validator"
    # Substitute after tokenization so paths with spaces stay one argument.
    argv = [arg.replace("{path}", str(target_path)) for arg in shlex.split(command)]
    try:
        rc = subprocess.run(argv, cwd=run_root, capture_output=True, text=True)
    except OSError as exc:
        return False, f"validator unavailable: {exc}"
    return rc.returncode == 0, f"{argv[0]} rc={rc.returncode}"


def _verify_pin(pin, path):
    """Check actual bytes against every declared pin, without trusting availability.

    Hash-based annex keys can be checked offline. Commit pins compare a regular
    Git blob with the working file (not merely the current HEAD). Other annex
    backends and symlink blobs are unsupported and fail closed.
    """
    checks = []
    key = pin.get("datalad-annex-key")
    if key:
        match = re.fullmatch(r"(SHA256|MD5)E?-s([0-9]+)--([0-9a-fA-F]+)(?:\..*)?", str(key))
        if not match:
            return False, "unsupported or malformed annex content key"
        algorithm, size, expected = match.groups()
        if len(expected) != (64 if algorithm == "SHA256" else 32):
            return False, "invalid annex digest length"
        digest = hashlib.new(algorithm.lower())
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        checks.append(Path(path).stat().st_size == int(size) and digest.hexdigest() == expected.lower())
    commit = pin.get("datalad-commit-sha")
    if commit:
        if not re.fullmatch(r"[0-9a-fA-F]{40}", str(commit)):
            return False, "commit pin must be a full SHA-1 commit ID"
        git_root = subprocess.run(["git", "-C", str(Path(path).parent), "rev-parse", "--show-toplevel"],
                                  capture_output=True, text=True)
        if git_root.returncode:
            return False, "commit pin cannot be resolved outside a Git repository"
        root = Path(git_root.stdout.strip())
        object_type = subprocess.run(["git", "-C", str(root), "cat-file", "-t", str(commit)],
                                     capture_output=True, text=True)
        if object_type.returncode or object_type.stdout.strip() != "commit":
            return False, "commit pin must identify a Git commit object"
        relative = str(Path(path).resolve().relative_to(root.resolve()))
        entry = subprocess.run(["git", "-C", str(root), "ls-tree", str(commit), "--", relative],
                               capture_output=True, text=True)
        if entry.returncode or not entry.stdout.startswith(("100644 ", "100755 ")):
            return False, "commit pin does not resolve to a regular file blob"
        blob = subprocess.run(["git", "-C", str(root), "show", f"{commit}:{relative}"], capture_output=True)
        checks.append(blob.returncode == 0 and _sha256_bytes(blob.stdout) == sha256_file(path))
    return bool(checks) and all(checks), "content pins match" if checks and all(checks) else "missing or mismatched content pin"


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
    gate, inputs_summary = {}, []
    pins = run_fm.get("inputs")
    if not isinstance(pins, list) or not pins:
        return False, {"error": "non-empty input pins required"}, []
    passed, seen, checked_standards = True, set(), set()
    for pin in pins:
        if not isinstance(pin, dict) or pin.get("node") not in graph:
            return False, {"error": "input node missing or unknown"}, inputs_summary
        nid = pin["node"]
        if nid in seen:
            return False, {"error": "duplicate input node"}, inputs_summary
        seen.add(nid)
        fpath = _resolve_input_path(pin, graph, run_root)
        present = bool(fpath and Path(fpath).is_file())
        if not present and not offline and fpath:
            present = _datalad_get(fpath, run_root) and Path(fpath).is_file()
        entry = {"node": nid, "path": str(fpath) if fpath else None, "available": present, "pinned": False}
        if not present:
            entry["data-liveness"] = "unreachable" if offline else "missing"
        else:
            entry["pinned"], entry["pin-check"] = _verify_pin(pin, fpath)
            entry["observed-hash"] = sha256_file(fpath)
        valid = True
        standards = {e["target"] for e in graph[nid][1].get("edges", []) if e.get("type") == "conforms-to"}
        if pin.get("conforms-to"):
            standards.add(pin["conforms-to"])
        if standards and not no_gate:
            results = {}
            for std_id in sorted(standards):
                std = graph.get(std_id, (None, {}))[1]
                if not present or std.get("type") != "standard":
                    ok, detail = False, "standard or input unavailable"
                else:
                    ok, detail = _run_validator(std, fpath, rokb, run_root)
                results[std_id] = {"valid": ok, "validator": detail}
                valid = valid and ok
                checked_standards.add(std_id)
            entry.update({"standards": results, "valid": valid})
        elif no_gate:
            entry.update({"standards": sorted(standards), "valid": None, "validator": "skipped (--no-gate)"})
        passed = passed and present and entry["pinned"] and valid
        gate[nid] = entry
        inputs_summary.append(entry)
    required = {e["target"] for e in run_fm.get("edges", []) if e.get("type") == "requires-standard"}
    if not no_gate and required - checked_standards:
        return False, {**gate, "error": "required standards need explicit input conformance bindings",
                       "unbound-standards": sorted(required - checked_standards)}, inputs_summary
    return passed, gate, inputs_summary


# ─────────────────────────────────────────────────────────────────────────────
# execution
# ─────────────────────────────────────────────────────────────────────────────
def execute(run_fm, run_root, *, no_container):
    """Use a registered, hash-checked local container image or explicit host mode.

    container-image names a DataLad registration, not an OCI image URL.
    container-digest is the raw SHA-256 of its local image file (e.g. SIF).
    """
    command = run_fm.get("command")
    if not isinstance(command, str) or not command.strip():
        return 1, "not executed", "non-empty command required"
    argv = shlex.split(command)
    if no_container:
        rc = subprocess.run(argv, cwd=run_root, capture_output=True, text=True)
        return rc.returncode, "host subprocess (--no-container; environment unpinned)", rc.stderr[-2000:]
    name, digest = run_fm.get("container-image"), run_fm.get("container-digest")
    if not name or not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        return 1, "not executed", "registered container name and full SHA-256 required; use --no-container explicitly for host execution"
    if not shutil.which("datalad"):
        return 1, "not executed", "DataLad unavailable; no host fallback"
    listing = subprocess.run(["datalad", "-f", "json", "containers-list", "-d", str(run_root)],
                             cwd=run_root, capture_output=True, text=True)
    if listing.returncode:
        return 1, "not executed", "container registration unavailable (install datalad-container); no host fallback"
    records = [json.loads(line) for line in listing.stdout.splitlines() if line.strip()]
    records = [r for r in records if r.get("name") == name and r.get("status") == "ok"]
    if len(records) != 1 or not records[0].get("path"):
        return 1, "not executed", "registered container not found or ambiguous"
    image = _norm(records[0]["path"], run_root)
    if not image.is_file() or sha256_file(image) != digest:
        return 1, "not executed", "container file unavailable or digest mismatch"
    full = ["datalad", "containers-run", "-d", str(run_root), "-n", name, "--explicit"]
    for pin in run_fm["inputs"]:
        full += ["--input", pin["path"]]
    for pin in run_fm["outputs"]:
        full += ["--output", pin["output-path"]]
    rc = subprocess.run(full + ["--", *argv], cwd=run_root, capture_output=True, text=True)
    return rc.returncode, "datalad containers-run (image file SHA-256 checked)", rc.stderr[-2000:]


# ─────────────────────────────────────────────────────────────────────────────
# verification tiers
# ─────────────────────────────────────────────────────────────────────────────
def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _tol_pass(obs, exp, tol):
    if not _number(obs) or not _number(exp) or not isinstance(tol, dict):
        return False
    if any(k not in ("rel", "abs") or not _number(v) or v < 0 for k, v in tol.items()):
        return False
    difference = abs(obs - exp)
    bound = max(tol.get("abs", 0.0), tol.get("rel", 0.0) * abs(exp))
    return _number(difference) and _number(bound) and difference <= bound


def verify_byte_identical(pin, run_root):
    tier = pin.get("tier", "byte-identical")
    result = {"node": pin.get("node"), "tier": tier, "passed": False}
    out = _norm(pin.get("output-path"), run_root)
    if not out or not out.is_file():
        return {**result, "reason": "output not on disk"}
    observed, norm = normalized_hash(out) if tier == "normalized-content" else (sha256_file(out), "none")
    if tier == "normalized-content" and (norm.startswith("raw") or norm == "none"):
        return {**result, "reason": "requested normalization unavailable", "normalization": norm}
    expected = pin.get("expected-hash")
    return {**result, "expected": expected, "observed": observed, "normalization": norm,
            "passed": bool(expected) and observed == expected}


def verify_numeric(pin, run_root, tolerance):
    out = _norm(pin.get("output-path"), run_root)
    expected = pin.get("expected-values")
    failure = [{"node": pin.get("node"), "passed": False, "reason": "non-empty finite expected values and JSON object required"}]
    if not out or not out.is_file() or not isinstance(expected, dict) or not expected:
        return failure
    try:
        produced = json.loads(out.read_text())
    except (ValueError, OSError):
        return failure
    if not isinstance(produced, dict) or not isinstance(tolerance, dict):
        return failure
    qtol = tolerance.get("quantities", {})
    if not isinstance(qtol, dict):
        return failure
    checks = []
    for name, exp in expected.items():
        obs = produced.get(name)
        tol = qtol.get(name, tolerance.get("default", {}))
        checks.append({"node": pin.get("node"), "quantity": name, "expected": exp,
                       "observed": obs, "tol": tol, "passed": _tol_pass(obs, exp, tol)})
    return checks


def verify_structural(run_fm, graph, run_root=None):
    """Check fresh output traces and cited numeric evidence, not prose entailment.

    Each output JSON must carry reasoning-trace. metrics-cited maps a metric name
    to {node, value, tolerance?}; values are checked against the cited input JSON.
    Unsupported trace-only/prose assertions cannot receive structural acceptance.
    """
    result = {"passed": False, "scope": "output citations and numeric evidence only; scientific interpretation is not verified", "checks": []}
    if run_root is None or not run_fm.get("outputs"):
        return {**result, "reason": "fresh output artifacts and run root required"}
    inputs = {p["node"]: p for p in run_fm.get("inputs", [])}
    for output in run_fm["outputs"]:
        path = _norm(output.get("output-path"), run_root)
        try:
            data = json.loads(path.read_text())
            trace = data.get("reasoning-trace")
        except (OSError, ValueError, AttributeError):
            return {**result, "reason": "output must be JSON with a reasoning trace"}
        if not isinstance(trace, dict):
            return {**result, "reason": "missing output reasoning trace"}
        accessed, metrics = trace.get("nodes-accessed"), trace.get("metrics-cited")
        if (not isinstance(accessed, list) or not accessed or
                any(not isinstance(n, str) or n not in graph or n not in inputs for n in accessed) or
                not isinstance(metrics, dict) or not metrics or
                any(not isinstance(trace.get(k), str) or not trace[k].strip()
                    for k in ("model-identifier", "timestamp", "evidence-summary"))):
            return {**result, "reason": "incomplete trace, unknown citation, or citation is not a pinned input"}
        for metric, claim in metrics.items():
            if not isinstance(claim, dict) or claim.get("node") not in accessed:
                return {**result, "reason": "numeric citations require {node, value, tolerance?}"}
            source = _resolve_input_path(inputs[claim["node"]], graph, run_root)
            try:
                evidence = json.loads(source.read_text())
                observed = evidence.get(metric)
            except (OSError, ValueError, AttributeError):
                return {**result, "reason": "cited source is not a readable JSON object"}
            result["checks"].append({"node": claim["node"], "metric": metric,
                                     "observed": observed, "claimed": claim.get("value"),
                                     "passed": _tol_pass(observed, claim.get("value"), claim.get("tolerance", {}))})
        # A retriever manifest needs a verifiable snapshot, not merely a model name.
        manifest = trace.get("retriever-manifest", run_fm.get("retriever-manifest"))
        if manifest is not None:
            return {**result, "reason": "retriever snapshot verification is not implemented"}
    result["passed"] = bool(result["checks"]) and all(c["passed"] for c in result["checks"])
    return result


def project_root(rokb, explicit=None):
    if explicit is not None:
        return Path(explicit).resolve()
    rokb = Path(rokb).resolve()
    # Preserve the documented .../rokb layout; an index at the project root also works.
    return rokb.parent if rokb.name == "rokb" else rokb


def _tier(fm, pin):
    default = {"deterministic": "byte-identical", "stochastic": "numeric-tolerance", "agent-inferred": "structural"}
    return pin.get("tier", default[fm["provenance-mode"]])


def run_node(rokb, node_id, *, mode="run", offline=False, no_container=False, no_gate=False, graph=None, run_root=None):
    """Execute a trusted local run-record; never treat missing checks as success."""
    v = RunVerdict(node=node_id, mode=mode)
    try:
        return _run_node(rokb, node_id, v, mode=mode, offline=offline, no_container=no_container,
                         no_gate=no_gate, graph=graph, run_root=run_root)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        v.verdict, v.notes = "error", str(exc)
        return v


def _run_node(rokb, node_id, v, *, mode, offline, no_container, no_gate, graph, run_root):
    rokb = Path(rokb).resolve()
    run_root = project_root(rokb, run_root)
    graph = load_graph(rokb) if graph is None else graph
    if mode not in ("run", "reproduce"):
        raise ValueError("unknown execution mode")
    if node_id not in graph:
        raise ValueError("node not in index")
    path, fm = graph[node_id]
    if fm.get("type") != "run-record" or fm.get("provenance-mode") not in ("deterministic", "stochastic", "agent-inferred"):
        raise ValueError("valid run-record and provenance mode required")
    if fm.get("method") not in graph or graph[fm["method"]][1].get("type") != "method":
        raise ValueError("method must resolve to a method node")
    outputs = fm.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise ValueError("non-empty declared outputs required")
    paths = []
    for pin in outputs:
        if not isinstance(pin, dict) or pin.get("node") not in graph or graph[pin["node"]][1].get("type") != "derivative":
            raise ValueError("output must resolve to a derivative node")
        if not pin.get("output-path") or _tier(fm, pin) not in ("byte-identical", "normalized-content", "numeric-tolerance", "structural"):
            raise ValueError("output path and supported verification tier required")
        paths.append(_norm(pin["output-path"], run_root))
    if len(set(paths)) != len(paths) or len({p["node"] for p in outputs}) != len(outputs):
        raise ValueError("duplicate output paths or nodes")
    v.status, v.provenance_mode, v.command = fm.get("status", "unknown"), fm["provenance-mode"], fm.get("command", "")
    passed, v.validation_gate, v.inputs = standards_gate(fm, graph, rokb, run_root, offline=offline, no_gate=no_gate)
    if not passed:
        v.verdict = "inputs-unavailable" if any(not p.get("available") for p in v.inputs) else "gate-failed"
        v.notes = "input availability, content pin or declared standard failed"
        return v
    input_paths = {Path(i["path"]).resolve() for i in v.inputs}
    if input_paths.intersection(paths):
        raise ValueError("outputs must not overwrite pinned inputs")
    before = {p: p.stat() if p.exists() else None for p in paths}
    # Supply resolved explicit inputs to DataLad, including pins whose path is on the node.
    execution_fm = {**fm, "inputs": [{**p, "path": i["path"]} for p, i in zip(fm["inputs"], v.inputs)]}
    v.exit_code, via, stderr = execute(execution_fm, run_root, no_container=no_container)
    v.environment = {"container-digest": fm.get("container-digest"), "resolved-via": via,
                     "pinned": not no_container and v.exit_code == 0, "standards-bypassed": no_gate}
    if v.exit_code:
        v.notes = stderr
        return v
    for pin, path in zip(outputs, paths):
        if not path.is_file():
            v.notes = "declared output missing: " + str(pin["output-path"])
            return v
        old = before[path]
        if old and (old.st_ino, old.st_mtime_ns, old.st_size) == (path.stat().st_ino, path.stat().st_mtime_ns, path.stat().st_size):
            v.notes = "declared output was not refreshed: " + str(pin["output-path"])
            return v
        raw = sha256_file(path)
        h, norm = normalized_hash(path) if _tier(fm, pin) == "normalized-content" else (raw, "none")
        if _tier(fm, pin) == "normalized-content" and (norm.startswith("raw") or norm == "none"):
            v.notes = "requested normalization unavailable: " + norm
            return v
        v.outputs.append({"node": pin["node"], "output-path": pin["output-path"], "produced-hash": h,
                          "raw-hash": raw, "normalization": norm, "tier": _tier(fm, pin)})
    # A command modifying its own inputs invalidates the provenance just checked.
    if any(sha256_file(i["path"]) != i["observed-hash"] for i in v.inputs):
        v.notes = "input bytes changed during execution"
        return v
    if no_gate:
        v.verdict, v.notes = "unchecked", "standards bypassed; no verified result"
        return v
    if mode == "run":
        structural_outputs = [p for p in outputs if _tier(fm, p) == "structural"]
        if structural_outputs:
            check = verify_structural({**fm, "outputs": structural_outputs}, graph, run_root)
            v.structural_checks = [check]
            if not check["passed"]:
                v.verdict, v.notes = "mismatch", "output evidence check failed"
                return v
        v.verdict, v.tier = "executed", "execute"
        return v
    checks, tiers = [], set()
    for pin in outputs:
        tier = _tier(fm, pin); tiers.add(tier)
        if tier in ("byte-identical", "normalized-content"):
            checked = verify_byte_identical({**pin, "tier": tier}, run_root)
            checks.append(checked["passed"])
            next(o for o in v.outputs if o["node"] == pin["node"]).update(checked)
        elif tier == "numeric-tolerance":
            checked = verify_numeric(pin, run_root, fm.get("reproduction-tolerance", {}))
            v.numeric_checks.extend(checked); checks.append(all(c["passed"] for c in checked))
        else:
            checked = verify_structural({**fm, "outputs": [pin]}, graph, run_root)
            v.structural_checks.append(checked); checks.append(checked["passed"])
    v.tier = next(iter(tiers)) if len(tiers) == 1 else "mixed"
    names = {"byte-identical": "verified", "normalized-content": "normalized-match",
             "numeric-tolerance": "reproduced-within-tolerance", "structural": "structurally-valid", "mixed": "checks-passed"}
    v.verdict = names[v.tier] if checks and all(checks) else "mismatch"
    return v


def order_runs(graph, ids):
    """Order run-records so a run that regenerates another's input comes first
    (a light topological sort over consume/regenerate edges). Stable for the
    common case; rejects cycles and ambiguous producers."""
    produced_by = {}   # output node -> run-record that regenerates it
    for rid in ids:
        for e in graph[rid][1].get("edges") or []:
            if e.get("type") == "regenerates":
                target = e.get("target")
                if target in produced_by and produced_by[target] != rid:
                    raise ValueError("ambiguous producers for output node: " + str(target))
                produced_by[target] = rid
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
        if not progressed:
            raise ValueError("cyclic run dependencies")
    return ordered


def certify_equivalence(rokb, run_record_a, run_record_b, *, tolerance=None, no_container=False):
    """Compare observed runs on matching inputs; not universal method equivalence."""
    graph = load_graph(rokb)
    fa, fb = graph[run_record_a][1], graph[run_record_b][1]
    ev = EquivalenceVerdict(method_a=fa.get("method"), method_b=fb.get("method"))
    va = run_node(rokb, run_record_a, no_container=no_container, graph=graph)
    # Snapshot content before B can overwrite an overlapping output path.
    root = project_root(rokb)
    values = []
    for output in va.outputs:
        try:
            values.append(json.loads(_norm(output["output-path"], root).read_text()))
        except (ValueError, OSError):
            values.append(None)
    vb = run_node(rokb, run_record_b, no_container=no_container, graph=graph)
    if va.verdict != "executed" or vb.verdict != "executed":
        ev.notes = f"a={va.verdict}, b={vb.verdict}"
        return ev
    if (not va.outputs or len(va.outputs) != len(vb.outputs) or
            sorted(i["observed-hash"] for i in va.inputs) != sorted(i["observed-hash"] for i in vb.inputs)):
        ev.notes = "non-empty equal output counts and identical input content required"
        return ev
    for i, (a, b) in enumerate(zip(va.outputs, vb.outputs)):
        match = a["raw-hash"] == b["raw-hash"]
        if not match and tolerance is not None:
            try:
                da, db = values[i], json.loads(_norm(b["output-path"], root).read_text())
                match = (isinstance(da, dict) and isinstance(db, dict) and bool(da) and set(da) == set(db)
                         and all(_tol_pass(da[k], db[k], tolerance.get("default", tolerance)) for k in da))
            except (ValueError, OSError, TypeError):
                match = False
        ev.comparisons.append({"a": a["output-path"], "b": b["output-path"], "passed": bool(match)})
    ev.equivalent = bool(ev.comparisons) and all(c["passed"] for c in ev.comparisons)
    ev.notes = "observed outputs on these pinned inputs only"
    return ev


# ─────────────────────────────────────────────────────────────────────────────
# writeback + manifest
# ─────────────────────────────────────────────────────────────────────────────
def write_verdict_back(rokb, node_id, verdict: RunVerdict):
    """Write `validation-gate` + `replay-verdict` (and, for forward runs, status +
    produced hashes) back into the sidecar, preserving the body."""
    path, fm = load_graph(rokb)[node_id]
    is_json = Path(path).read_text().startswith("{")
    fm, body = read_sidecar(path)
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
            # Establish only a missing baseline for the declared hash tier;
            # tolerance and structural tiers have separate expectations.
            tier = pin.get("tier") or ("byte-identical" if default_mode == "deterministic" else None)
            if tier in ("byte-identical", "normalized-content") and pin.get("node") in produced and not pin.get("expected-hash"):
                pin["expected-hash"] = produced[pin["node"]]
    if verdict.verdict not in SUCCESS:
        fm["status"] = "failed"
    if is_json:
        Path(path).write_text(json.dumps(_json_safe(fm), indent=2, allow_nan=False) + "\n")
    else:
        Path(path).write_text("---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n" + body)


def _json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def write_manifest(verdicts, path):
    """Report separate execution and reproduction counts; no pooled success rate."""
    summary = {"total": len(verdicts), "execution": {}, "reproduction": {}}
    for v in verdicts:
        bucket = summary["execution" if v.mode == "run" else "reproduction"]
        bucket[v.verdict] = bucket.get(v.verdict, 0) + 1
    manifest = {"glimmer-run-version": RUNNER_VERSION, "summary": summary, "runs": [v.to_dict() for v in verdicts]}
    manifest = _json_safe(manifest)
    Path(path).write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
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
    ap.add_argument("--run-root", help="explicit working directory (default: parent of rokb/, otherwise index directory)")
    args = ap.parse_args()

    rokb = Path(args.rokb)
    try:
        graph = load_graph(rokb)
    except (OSError, ValueError, KeyError) as exc:
        ap.error(str(exc))
    if args.node_id == "all":
        targets = [nid for nid, (_, fm) in graph.items() if fm.get("type") == "run-record"]
    else:
        targets = [t.strip() for t in args.node_id.split(",") if t.strip()]
    targets = list(dict.fromkeys(targets))
    try:
        targets = order_runs(graph, [t for t in targets if t in graph]) + [t for t in targets if t not in graph]
    except ValueError as exc:
        ap.error(str(exc))

    verdicts = []
    for nid in targets:
        v = run_node(rokb, nid, mode=args.mode, offline=args.offline,
                     no_container=args.no_container, no_gate=args.no_gate, graph=graph, run_root=args.run_root)
        verdicts.append(v)
        mark = {"executed": "▶", "verified": "✓", "reproduced-within-tolerance": "≈",
                "structurally-valid": "≋", "normalized-match": "≈", "checks-passed": "✓"}.get(v.verdict, "✗")
        print(f"  {mark} {nid}: {v.verdict}" + (f" [{v.tier}]" if v.tier else "")
              + (f" — {v.notes}" if v.notes else ""))
        if args.write_verdict and nid in graph:
            write_verdict_back(rokb, nid, v)
            graph = load_graph(rokb)  # refresh after writeback

    if args.manifest:
        m = write_manifest(verdicts, args.manifest)
        print(f"\nManifest: {args.manifest}  {json.dumps(m['summary'])}")

    bad = [v for v in verdicts if v.verdict not in SUCCESS]
    sys.exit(1 if bad or not verdicts else 0)


if __name__ == "__main__":
    main()
