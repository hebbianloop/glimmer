"""DataLad call-fmt for this trusted example's single Docker archive.

Not a general untrusted-container service. The host caller controls Docker and
must be isolated from production. No host credentials or Docker socket enter the
container. A receipt is retained even if execution fails or exceeds its deadline.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tarfile
import uuid

DEADLINE = 15


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return 'sha256:' + digest.hexdigest()


def image_ids(archive):
    with tarfile.open(archive, 'r:') as tar:
        member = tar.getmember('manifest.json')
        if not member.isfile() or member.size > 1048576:
            raise ValueError('invalid archive manifest')
        manifest = json.load(tar.extractfile(member))
        if not isinstance(manifest, list) or len(manifest) != 1:
            raise ValueError('exactly one archived image required')
        config = manifest[0]['Config']
        if not re.fullmatch(r'(?:blobs/sha256/)?[a-f0-9]{64}(?:\.json)?', config):
            raise ValueError('unsupported image configuration path')
        member = tar.getmember(config)
        if not member.isfile() or member.size > 1048576:
            raise ValueError('invalid image configuration')
        content = tar.extractfile(member).read()
        digest = hashlib.sha256(content).hexdigest()
        if digest != Path(config).name.removesuffix('.json'):
            raise ValueError('image configuration hash mismatch')
        ids = ['sha256:' + digest]
        # Docker's classic store addresses the config; its containerd store may
        # address the OCI index. Both candidates must come from this archive.
        if 'index.json' in tar.getnames():
            member = tar.getmember('index.json')
            if not member.isfile() or member.size > 1048576:
                raise ValueError('invalid OCI index')
            index = json.load(tar.extractfile(member))
            if len(index['manifests']) != 1:
                raise ValueError('exactly one OCI index entry required')
            reference = index['manifests'][0]['digest']
            if not re.fullmatch(r'sha256:[a-f0-9]{64}', reference):
                raise ValueError('unsupported OCI digest')
            member = tar.getmember('blobs/sha256/'+reference.removeprefix('sha256:'))
            if not member.isfile() or member.size > 1048576:
                raise ValueError('invalid OCI descriptor')
            if hashlib.sha256(tar.extractfile(member).read()).hexdigest() != reference.removeprefix('sha256:'):
                raise ValueError('OCI descriptor hash mismatch')
            def reaches_config(ref, depth=0):
                if depth > 8 or not re.fullmatch(r'sha256:[a-f0-9]{64}', ref):
                    raise ValueError('invalid OCI descriptor chain')
                path = 'blobs/sha256/'+ref.removeprefix('sha256:')
                if path not in tar.getnames(): return False  # other, unexported platforms
                item = tar.getmember(path)
                if not item.isfile() or item.size > 1048576:
                    raise ValueError('invalid OCI chain member')
                payload = tar.extractfile(item).read()
                if 'sha256:'+hashlib.sha256(payload).hexdigest() != ref:
                    raise ValueError('OCI chain hash mismatch')
                node = json.loads(payload)
                if 'config' in node: return node['config']['digest'] == ids[0]
                return any(reaches_config(child['digest'],depth+1) for child in node.get('manifests',[]))
            if not reaches_config(reference):
                raise ValueError('OCI descriptor does not reach the archived configuration')
            if reference not in ids: ids.append(reference)
        return ids


def docker(*args, timeout=120):
    return subprocess.run(['docker', *args], check=True, capture_output=True,
                          text=True, timeout=timeout)


def stderr_detail(exc):
    value=getattr(exc,'stderr',None) or ''
    return (value.decode(errors='replace') if isinstance(value,bytes) else value)[-2048:]


def main():
    if os.geteuid() == 0:
        raise SystemExit('Run the fixture as an unprivileged user of the disposable Docker host')
    root = Path.cwd().resolve()
    archive = Path(sys.argv[1]).resolve()
    if not archive.is_file() or not archive.is_relative_to(root):
        raise SystemExit('container archive must be inside the fixture dataset')
    command = sys.argv[2:]
    if not command: raise SystemExit('a container command is required')
    for name in ('code', 'inputs', 'out'):
        path = root / name
        if path.is_symlink() or not path.is_dir():
            raise SystemExit('fixture mount directories must be ordinary directories')
    receipt_dir = root / 'execution-receipts'
    receipt_dir.mkdir(mode=0o700, exist_ok=True)
    attempt = str(uuid.uuid4())
    record = {'version': 1, 'id': attempt, 'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'archive_sha256': sha256(archive), 'command': command, 'timeout_seconds': DEADLINE,
              'status': 'failed', 'exit_code': None}
    container = None
    container_name = 'glimmer-fixture-'+attempt
    record['container_name'] = container_name
    create_attempted = False
    exit_code = 1
    step = 'parse-archive'
    def interrupted(signum, frame):
        raise RuntimeError('interrupted by signal '+str(signum))
    handlers = {sig: signal.signal(sig,interrupted) for sig in (signal.SIGTERM,signal.SIGINT)}
    try:
        candidates = image_ids(archive)
        record['archive_image_ids'] = candidates
        record['image_preexisting'] = {}
        for candidate in candidates:
            try:
                docker('image','inspect',candidate)
                record['image_preexisting'][candidate] = True
            except subprocess.CalledProcessError:
                record['image_preexisting'][candidate] = None
        step = 'load'
        docker('load', '--input', str(archive))
        step = 'inspect-image'
        frozen_id = None
        for candidate in candidates:
            try:
                loaded = json.loads(docker('image', 'inspect', candidate).stdout)[0]
            except subprocess.CalledProcessError:
                continue
            if loaded['Id'] == candidate:
                frozen_id = candidate
                record['image_platform'] = {k: loaded.get(k) for k in ('Os','Architecture','Variant')}
                break
        if not frozen_id: raise RuntimeError('loaded image does not match an archived immutable identifier')
        record['image_id'] = frozen_id
        args = ['create', '--name', container_name, '--pull=never', '--network=none',
                '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges',
                '--user', f'{os.getuid()}:{os.getgid()}', '--memory=128m', '--memory-swap=128m',
                '--cpus=0.5', '--pids-limit=64', '--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=16m',
                '--workdir=/work', '--env=PYTHONDONTWRITEBYTECODE=1', '--env=PYTHONHASHSEED=0']
        for name in ('code', 'inputs', 'out'):
            args += ['--mount', f'type=bind,src={root/name},dst=/work/{name}' + (',readonly' if name != 'out' else '')]
        step = 'create'
        create_attempted = True
        created = docker(*args, frozen_id, *command).stdout.strip()
        if not re.fullmatch(r'[0-9a-f]{64}', created): raise RuntimeError('invalid created container identifier')
        container = created
        step = 'inspect-container'
        info = json.loads(docker('inspect', container).stdout)[0]
        record['container_id'] = container
        record['configuration'] = {k: info['HostConfig'][k] for k in
            ('NetworkMode', 'ReadonlyRootfs', 'CapDrop', 'SecurityOpt', 'Memory', 'MemorySwap', 'NanoCpus', 'PidsLimit', 'Tmpfs')}
        record['mounts'] = [{k: m[k] for k in ('Type', 'Source', 'Destination', 'RW')} for m in info['Mounts']]
        record['user'] = info['Config']['User']
        step = 'start'
        try:
            result = docker('start', '--attach', container, timeout=DEADLINE)
            exit_code = result.returncode
            record['stdout'] = result.stdout[-8192:]
            record['stderr'] = result.stderr[-8192:]
            record['status'] = 'completed'
        except subprocess.TimeoutExpired:
            exit_code = 124
            record['status'] = 'timed-out'
            try:
                docker('kill', container, timeout=10)
            except (OSError,subprocess.SubprocessError) as exc:
                record['kill_error'] = str(exc)
                record['kill_stderr'] = stderr_detail(exc)
        except subprocess.CalledProcessError as exc:
            exit_code = exc.returncode
            record['stdout'] = (exc.stdout or '')[-8192:]
            record['stderr'] = (exc.stderr or '')[-8192:]
            record['failed_step'] = step
        step = 'inspect-final-state'
        record['state'] = json.loads(docker('inspect', container).stdout)[0]['State']
        if record['state']['Running'] and record['status'] != 'timed-out':
            raise RuntimeError('container still running after execution returned')
    except (OSError, ValueError, KeyError, TypeError, IndexError, tarfile.TarError, RuntimeError, subprocess.SubprocessError) as exc:
        exit_code = 1
        record['status'] = 'failed'
        record['failed_step'] = step
        record['error'] = str(exc)[-2048:]
        record['error_stderr'] = stderr_detail(exc)
    finally:
        if create_attempted:
            try:
                docker('rm', '--force', container_name, timeout=15)
                record['container_removed'] = True
            except (OSError, subprocess.SubprocessError) as exc:
                record['container_removed'] = False
                record['cleanup_error'] = str(exc)
                record['cleanup_stderr'] = stderr_detail(exc)
                record['status'] = 'cleanup-failed'
                exit_code = 1
        record['exit_code'] = exit_code
        record['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with (receipt_dir/(attempt+'.json')).open('x') as stream:
            json.dump(record, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write('\n')
        for sig, handler in handlers.items(): signal.signal(sig,handler)
    raise SystemExit(exit_code)


if __name__ == '__main__': main()
