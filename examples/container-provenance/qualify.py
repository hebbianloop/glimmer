#!/usr/bin/env python3
"""Real container qualification. Use only a disposable Linux Docker host and synthetic data."""
import argparse
import datetime
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

import yaml

HERE = Path(__file__).resolve().parent
RUN_ID = 'run-container-summary'
IMAGE = '.datalad/environments/python-fixture/image.tar'
SUCCESS = {'executed', 'checks-passed'}


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return 'sha256:' + value.hexdigest()


def command(argv, cwd, *, check=True, env=None, timeout=240):
    process_env = {**os.environ, 'GIT_AUTHOR_NAME': 'Glimmer synthetic fixture',
                   'GIT_COMMITTER_NAME': 'Glimmer synthetic fixture',
                   'GIT_AUTHOR_EMAIL': 'fixture@example.invalid', 'GIT_COMMITTER_EMAIL': 'fixture@example.invalid'}
    process_env.update(env or {})
    proc = subprocess.Popen(argv, cwd=cwd, env=process_env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout,stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid,signal.SIGTERM)
        try:
            stdout,stderr = proc.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid,signal.SIGKILL)
            stdout,stderr = proc.communicate()
        result = subprocess.CompletedProcess(argv,124,stdout,stderr+'\nQualification command deadline exceeded')
    else:
        result = subprocess.CompletedProcess(argv,proc.returncode,stdout,stderr)
    if check and result.returncode:
        raise RuntimeError(f'{argv[0]} exited {result.returncode}: '+result.stderr[-2000:])
    return result


def verify_source(requested):
    repo=Path(command(['git','rev-parse','--show-toplevel'],HERE).stdout.strip())
    revision=command(['git','rev-parse','HEAD'],repo).stdout.strip()
    if requested != revision: raise ValueError('source revision differs from the checkout')
    paths=['examples/container-provenance','glimmer','tests/test_container_fixture.py']
    status=command(['git','status','--porcelain','--untracked-files=all','--ignored','--',*paths],repo).stdout
    if status: raise ValueError('source must be clean, including ignored files: '+status)
    tracked=command(['git','ls-files','--','examples/container-provenance'],repo).stdout.splitlines()
    if any(part.startswith('._') for name in tracked for part in Path(name).parts):
        raise ValueError('AppleDouble metadata is not example source')
    actual={str(p.relative_to(repo)) for p in HERE.rglob('*') if p.is_file()}
    if actual != set(tracked): raise ValueError('example files differ from tracked source')
    import glimmer.tools.run as runner
    import glimmer.tools.cli as cli
    for module,relative in ((runner,'glimmer/tools/run.py'),(cli,'glimmer/tools/cli.py')):
        if digest(Path(module.__file__)) != digest(repo/relative):
            raise ValueError('installed CLI differs from the committed source: '+relative)
    for name in ('glimmer','datalad'):
        location=shutil.which(name)
        if not location or not Path(location).resolve().is_relative_to(Path(sys.prefix).resolve()):
            raise ValueError(name+' must come from the current Python environment')
    if not Path(shutil.which('python')).samefile(sys.executable):
        raise ValueError('python on PATH differs from the qualification interpreter')
    return {'revision':revision,'source_status':status,
            'source_sha256':{str(Path(p).relative_to('examples/container-provenance')):digest(repo/p) for p in tracked},
            'runner_sha256':digest(Path(runner.__file__)), 'cli_sha256':digest(Path(cli.__file__)),
            'tools':{name:shutil.which(name) for name in ('python','glimmer','datalad','git','git-annex','docker')}}


def read_node(path):
    _, fields, body = path.read_text().split('---\n', 2)
    return yaml.safe_load(fields), body


def write_node(path, fields, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = {**fields, 'provenance-hash': 'sha256:'+hashlib.sha256(body.encode()).hexdigest()}
    path.write_text('---\n'+yaml.safe_dump(fields, sort_keys=False)+'---\n'+body)


def create_graph(root):
    nodes = []
    def add(kind, node_id, name, fields, edges=()):
        fm = {'id': node_id, 'type': kind, 'name': name, 'created': '2026-11-11T00:00:00Z',
              'modified': '2026-11-11T00:00:00Z', **fields,
              'edges': [{'type': rel, 'target': target} for rel, target in edges]}
        relative = f'{kind}s/{node_id}.md'
        write_node(root/'rokb'/relative, fm, '\nSynthetic container qualification; not a scientific finding.\n')
        nodes.append({'id': node_id, 'type': kind, 'path': relative})

    expected = root/'expected/summary.json'
    add('concept', 'concept-container-replay', 'A pinned calculation and a fresh replay',
        {'statement': 'Does this declared synthetic calculation reproduce raw bytes and scalar values?',
         'concept-kind': 'research-question', 'status': 'open'})
    add('method', 'method-container-summary', 'Summarize four synthetic values',
        {'tool': 'Python standard library', 'version': 'fixture-1',
         'parameters': {'sum': 'math.fsum', 'mean': 'sum / count'},
         'workflow-definition-sha': digest(root/'code/compute.py')})
    add('standard', 'standard-bounded-values', 'Bounded numeric-list fixture format',
        {'standard-class': 'spec', 'version': '1',
         'validator': {'kind': 'external', 'command': 'python code/check_values.py {path}'}})
    sources = [('dataset-values','inputs/values.json','data'),
               ('dataset-compute-code','code/compute.py','method-code'),
               ('dataset-validator-code','code/check_values.py','validator-code'),
               ('dataset-container-entry','code/container_entry.py','trusted-execution-adapter'),
               ('dataset-container-registration','.datalad/config','trusted-container-registration'),
               ('dataset-expected-baseline','expected/summary.json','authored-comparison-baseline')]
    pins = []
    source_commit = command(['git','rev-parse','HEAD'],root).stdout.strip()
    for node_id, path, role in sources:
        edges = [('conforms-to','standard-bounded-values')] if role == 'data' else []
        add('dataset', node_id, role.replace('-',' ').capitalize(),
            {'datalad-relative-path': path, 'datalad-commit-sha': source_commit,
             'data-provenance': 'Committed synthetic fixture source; no participant data'}, edges)
        pin = {'node': node_id, 'path': path, 'role': role, 'datalad-commit-sha': source_commit}
        if role == 'data': pin['conforms-to'] = 'standard-bounded-values'
        pins.append(pin)
    outputs = []
    for name, tier in [('raw','byte-identical'),('numeric','numeric-tolerance')]:
        node_id = 'derivative-'+name+'-summary'
        add('derivative', node_id, name.capitalize()+' summary output',
            {'provenance-mode': 'deterministic', 'output-path': f'out/{name}.json', 'output-format': 'json'},
            [('produced-by','method-container-summary'),('derives-from','dataset-values')])
        pin = {'node': node_id, 'output-path': f'out/{name}.json', 'tier': tier}
        if name == 'raw': pin['expected-hash'] = digest(expected)
        else: pin['expected-values'] = json.loads(expected.read_text())
        outputs.append(pin)
    add('run-record', RUN_ID, 'Declared container summary invocation',
        {'method': 'method-container-summary', 'command': 'python code/compute.py inputs/values.json out',
         'provenance-mode': 'deterministic', 'status': 'ready', 'inputs': pins, 'outputs': outputs,
         'container-image': 'python-fixture', 'container-digest': digest(root/IMAGE),
         'reproduction-tolerance': {'default': {'abs': 0.0, 'rel': 0.0}}},
        [('reruns','method-container-summary'),('addresses-concept','concept-container-replay'),
         ('requires-standard','standard-bounded-values')]
        + [('consumes',p['node']) for p in pins] + [('regenerates',p['node']) for p in outputs])
    profile = root/'rokb/_glimmer-profiles/container-fixture.yaml'
    profile.parent.mkdir(parents=True)
    profile.write_text('profile: container-fixture\nstandard: synthetic\nstatus: local\naugments: {}\n')
    (root/'rokb/_glimmer-index.json').write_text(json.dumps({'schema': 'glimmer/v0.6.0',
        'dataset-name': 'container-provenance', 'default-domain': 'container-fixture',
        'nodes': sorted(nodes,key=lambda n:n['id'])},indent=2)+'\n')


def prepare(root, archive):
    command(['datalad','create','-d',str(root)], root.parent)
    for folder in ('code','inputs','expected'): shutil.copytree(HERE/folder,root/folder)
    (root/'out').mkdir()
    (root/'.gitignore').write_text('execution-receipts/\n__pycache__/\n')
    command(['git','config','annex.backends','SHA256E'],root)
    command(['datalad','save','--to-git','-m','Record synthetic method source','code','inputs','expected','.gitignore'],root)
    command(['datalad','containers-add','python-fixture','--url',str(archive),'--image',IMAGE,
             '--call-fmt','{python} code/container_entry.py {img} {cmd}',
             '--extra-input','code/container_entry.py'],root)
    create_graph(root)
    command(['datalad','save','--to-git','-m','Freeze synthetic invocation definition','rokb'],root)
    return command(['git','rev-parse','HEAD'],root).stdout.strip()


def inject(root, case):
    path = root/'rokb/run-records'/f'{RUN_ID}.md'
    fm, body = read_node(path)
    values = root/'inputs/values.json'
    if case == 'changed-input': values.write_text('{"values":[2,4,6,9]}\n')
    elif case == 'missing-input': values.unlink()
    elif case == 'invalid-input':
        values.write_text('{"values":["invalid"]}\n')
        command(['git','add','inputs/values.json'],root)
        command(['git','commit','-m','Pin deliberately invalid fixture data'],root)
        invalid_commit=command(['git','rev-parse','HEAD'],root).stdout.strip()
        fm['inputs'][0]['datalad-commit-sha'] = invalid_commit
        node_path = root/'rokb/datasets/dataset-values.md'
        node, node_body = read_node(node_path);node['datalad-commit-sha'] = invalid_commit
        write_node(node_path,node,node_body)
    elif case == 'missing-validator':
        std = root/'rokb/standards/standard-bounded-values.md'
        fields, text = read_node(std)
        fields['validator']['command'] = 'unavailable-glimmer-fixture-validator {path}'
        write_node(std,fields,text)
    elif case == 'changed-image':
        replacement = root/'replacement.tar'
        shutil.copyfile(root/IMAGE,replacement)
        with replacement.open('ab') as stream: stream.write(b'changed archive')
        replacement.replace(root/IMAGE)
    elif case == 'missing-image': (root/IMAGE).unlink()
    elif case in ('failed-command','missing-output','timeout'):
        fm['command'] += ' --mode '+{'failed-command':'fail','missing-output':'missing','timeout':'timeout'}[case]
    elif case == 'wrong-baseline':
        fm['outputs'][0]['expected-hash'] = 'sha256:'+'0'*64
        fm['outputs'][1]['expected-values']['mean'] = 99.0
    write_node(path,fm,body)


def snapshot(root):
    files = [p for folder in ('rokb','code','expected') for p in (root/folder).rglob('*') if p.is_file()]
    files.append(root/'.datalad/config')
    return {str(p.relative_to(root)):digest(p) for p in sorted(files)}


def check_runtime(receipt,target):
    cfg = receipt['configuration']
    required = {'NetworkMode':'none','ReadonlyRootfs':True,'Memory':134217728,
                'MemorySwap':134217728,'NanoCpus':500000000,'PidsLimit':64}
    if any(cfg.get(k)!=v for k,v in required.items()): raise AssertionError('container limits differ')
    if cfg['CapDrop'] != ['ALL'] or not any(v.startswith('no-new-privileges') for v in cfg['SecurityOpt']):
        raise AssertionError('container privilege restriction missing')
    if not {'size=16m','noexec','nosuid','nodev'} <= set(cfg['Tmpfs']['/tmp'].split(',')):
        raise AssertionError('temporary filesystem limits differ')
    if receipt['user'] != f'{os.getuid()}:{os.getgid()}': raise AssertionError('container user differs')
    mounts = {m['Destination']:m for m in receipt['mounts']}
    if set(mounts) != {'/work/code','/work/inputs','/work/out','/tmp'} and set(mounts) != {'/work/code','/work/inputs','/work/out'}:
        raise AssertionError('unexpected container mounts')
    for path in ('/work/code','/work/inputs'):
        if mounts[path]['RW']: raise AssertionError('an input mount is writable')
    for name in ('code','inputs','out'):
        if mounts['/work/'+name]['Source'] != str(target/name): raise AssertionError('mount source differs')
    if not mounts['/work/out']['RW'] or not receipt['container_removed']: raise AssertionError('output/cleanup failed')
    if receipt['status'] == 'completed':
        probe = json.loads(receipt['stdout'].strip())
        if not all(probe['checks'].values()) or probe['uid'] == 0: raise AssertionError('isolation probe failed')


def run_case(root,evidence,template,case,expected,commit,archive_hash):
    target=root/case;attempt=evidence/case;attempt.mkdir()
    command(['datalad','clone',str(template),str(target)],root)
    command(['datalad','get',IMAGE],target)
    (target/'out').mkdir(exist_ok=True)
    inject(target,case)
    before=snapshot(target)
    source_status=command(['git','status','--porcelain'],target).stdout
    run_path=Path('rokb/run-records')/(RUN_ID+'.md')
    definition,_=read_node(target/run_path)
    shutil.copytree(target/'rokb',attempt/'definition')
    mode='run' if case=='execute' else 'rerun'
    invocation=['glimmer',mode,str(target/'rokb'),RUN_ID,'--offline','--run-root',str(target),
                '--manifest',str(attempt/'manifest.json')]
    started=datetime.datetime.now(datetime.timezone.utc).isoformat()
    env={'DOCKER_HOST':'unix:///nonexistent-glimmer-fixture.sock'} if case=='unavailable-engine' else None
    completed=command(invocation,target,check=False,env=env)
    (attempt/'cli.txt').write_text(completed.stdout+completed.stderr)
    manifest=json.loads((attempt/'manifest.json').read_text())
    verdict=manifest['runs'][0]
    frozen=before==snapshot(target)
    receipts=[]
    for receipt in sorted((target/'execution-receipts').glob('*.json')):
        obj=json.loads(receipt.read_text());receipts.append(obj)
        shutil.copyfile(receipt,attempt/receipt.name)
        if 'configuration' in obj: check_runtime(obj,target)
    products={}
    for name in ('raw.json','numeric.json'):
        output=target/'out'/name
        if output.is_file():
            shutil.copyfile(output,attempt/name);products[name]=digest(output)
    checks={'expected_verdict':verdict['verdict']==expected,
            'expected_exit':completed.returncode==(0 if expected in SUCCESS else 1),
            'definition_unchanged':frozen}
    changes={'changed-input':{'inputs/values.json'},'missing-input':{'inputs/values.json'},
        'invalid-input':{str(run_path),'rokb/datasets/dataset-values.md'},
        'missing-validator':{'rokb/standards/standard-bounded-values.md'},
        'changed-image':{IMAGE},'missing-image':{IMAGE},
        **{name:{str(run_path)} for name in ('failed-command','missing-output','wrong-baseline','timeout')}}
    checks['only_intended_mutations']={line[3:] for line in source_status.splitlines()}==changes.get(case,set())
    gate=verdict['validation-gate'].get('dataset-values',{})
    standard=gate.get('standards',{}).get('standard-bounded-values',{})
    if case=='changed-input': checks['pin_failure_only']=gate.get('pinned') is False and standard.get('valid') is True
    if case=='invalid-input': checks['standard_failure_only']=gate.get('pinned') is True and standard.get('valid') is False and standard.get('validator')=='python rc=1'
    if case=='missing-validator': checks['validator_unavailable']=gate.get('pinned') is True and standard.get('validator','').startswith('validator unavailable:')
    if case=='missing-input': checks['input_unavailable']=gate.get('available') is False
    if case in ('execute','replay','unavailable-engine'):
        checks['template_definition_intact']=digest(target/run_path)==digest(template/run_path)
    if case in ('execute','replay'):
        checks['exact_products']=len(products)==2 and all(v==digest(HERE/'expected/summary.json') for v in products.values())
        checks['real_container']=len(receipts)==1 and receipts[0]['status']=='completed' and verdict['environment']['pinned'] is True
        checks['archive_bound']=len(receipts)==1 and receipts[0]['archive_sha256']==definition['container-digest']==archive_hash
        baseline=json.loads((template/'expected/summary.json').read_text())
        checks['authored_oracle']=definition['outputs'][0]['expected-hash']==digest(template/'expected/summary.json') and definition['outputs'][1]['expected-values']==baseline
    if case=='replay':
        checks['raw_check']=bool(verdict['outputs']) and verdict['outputs'][0].get('passed') is True
        checks['numeric_checks']=len(verdict['numeric-checks'])==3 and all(c['passed'] for c in verdict['numeric-checks'])
        checks['declared_tolerance']=all(c['tol']=={'abs':0.0,'rel':0.0} for c in verdict['numeric-checks'])
        checks['observed_oracle']=verdict['outputs'][0].get('expected')==digest(template/'expected/summary.json') and {c['quantity']:c['expected'] for c in verdict['numeric-checks']}==baseline
    if case in ('changed-input','missing-input','invalid-input','missing-validator','changed-image','missing-image'):
        checks['not_executed']=not receipts and not products
    if case=='timeout': checks['stopped']=len(receipts)==1 and receipts[0]['status']=='timed-out' and receipts[0]['container_removed']
    if case=='failed-command':
        checks['method_failed']=len(receipts)==1 and receipts[0]['exit_code']==23 and not products
    if case=='missing-output':
        checks['method_completed']=len(receipts)==1 and receipts[0]['status']=='completed'
        checks['missing_product_detected']='declared output missing: out/numeric.json' in verdict['notes']
    if case=='wrong-baseline':
        checks['both_comparisons_failed']=bool(verdict['outputs']) and verdict['outputs'][0].get('passed') is False and any(not c['passed'] for c in verdict['numeric-checks'])
    if case=='unavailable-engine':
        checks['no_container_created']=len(receipts)==1 and receipts[0]['status']=='failed' and 'container_id' not in receipts[0] and not products
        checks['engine_connection_failed']=len(receipts)==1 and bool(receipts[0].get('archive_image_ids')) and receipts[0].get('failed_step')=='load' and 'nonexistent-glimmer-fixture.sock' in receipts[0].get('error_stderr','')
    if case in ('changed-image','missing-image'):
        checks['image_rejected']='container file unavailable or digest mismatch' in verdict['notes']
    result_commit=command(['git','rev-parse','HEAD'],target).stdout.strip()
    (attempt/'datalad-history.txt').write_text(command(['git','log','-1','--format=fuller'],target).stdout)
    item={'case':case,'started_at':started,'finished_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'template_commit':commit,'result_commit':result_commit,'source_status':source_status,'invocation':invocation,
          'definition_sha256':before,'checks':checks,'passed':all(checks.values()),'products':products,
          'manifest_sha256':digest(attempt/'manifest.json')}
    if case in ('execute','replay') and receipts:
        item['image_id']=receipts[0].get('image_id')
        item['image_platform']=receipts[0].get('image_platform')
    item['verdict']=verdict['verdict']
    return item


def container_inventory(root):
    return command(['docker','ps','-a','--filter','name=glimmer-fixture-',
                    '--format','{{.ID}}'],root).stdout.splitlines()


def write_json(path,value):
    path.write_text(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n')


def collect_case(root,evidence,template,case,expected,commit,archive_hash):
    """A failed assertion must leave evidence and must not masquerade as a pass."""
    attempt=evidence/case
    try:
        item=run_case(root,evidence,template,case,expected,commit,archive_hash)
    except Exception as exc:
        attempt.mkdir(exist_ok=True)
        item={'case':case,'verdict':'qualification-error','checks':{'completed':False},
              'error':type(exc).__name__+': '+str(exc)}
    finally:
        attempt.mkdir(exist_ok=True)
        for receipt in (root/case/'execution-receipts').glob('*.json'):
            shutil.copyfile(receipt,attempt/receipt.name)
    try:
        remaining=container_inventory(root)
        item['engine_inventory_after']=remaining
        item['checks']['engine_cleanup_verified']=not remaining
        # The preflight requires an empty fixture namespace. Recover any test
        # container left by this case, but keep the failed check in the receipt.
        for container in remaining:
            command(['docker','rm','--force',container],root)
    except Exception as exc:
        item['checks']['engine_cleanup_verified']=False
        item['cleanup_error']=str(exc)
    item['passed']=all(item['checks'].values())
    item['evidence_sha256']={str(p.relative_to(attempt)):digest(p) for p in sorted(attempt.rglob('*')) if p.is_file() and p.name!='attempt.json'}
    write_json(attempt/'attempt.json',item)
    return item


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--image-archive',type=Path,required=True)
    parser.add_argument('--source-revision',required=True,help='Commit containing this example; file hashes are also retained')
    args = parser.parse_args()
    if not __debug__ or sys.platform != 'linux' or os.geteuid() == 0:
        raise SystemExit('Use normal Python as a nonroot user on a disposable Linux Docker host')
    if not Path('/var/lib/glimmer-other-project/marker.txt').is_file():
        raise SystemExit('Create the synthetic outer-project marker described in the README first')
    root = args.work.resolve();archive = args.image_archive.resolve()
    if root.exists() or not archive.is_file(): raise SystemExit('Use a new work directory and an existing archive')
    for tool in ('git','git-annex','datalad','docker','glimmer'):
        if not shutil.which(tool): raise SystemExit('Missing required tool: '+tool)
    source=verify_source(args.source_revision)
    archive_hash=digest(archive)
    root.mkdir(parents=True);evidence=root/'evidence';evidence.mkdir()
    result={'version':1,'source_revision':source['revision'],**source,
            'image_archive_sha256':archive_hash,'results':[],'passed':False,'phase':'preparing'}
    write_json(evidence/'qualification.json',result)
    cases = {'execute':'executed','replay':'checks-passed','changed-input':'gate-failed',
        'missing-input':'inputs-unavailable','invalid-input':'gate-failed','missing-validator':'gate-failed',
        'changed-image':'error','missing-image':'error','failed-command':'error',
        'missing-output':'error','wrong-baseline':'mismatch','timeout':'error','unavailable-engine':'error'}
    try:
        if container_inventory(root): raise RuntimeError('another fixture container exists; use a fresh disposable host')
        template=root/'template'
        commit=prepare(template,archive)
        result.update({'template_commit':commit,'python':sys.version,
            'packages':{p:importlib.metadata.version(p) for p in ('glimmer-rokb','datalad','datalad-container','PyYAML')},
            'docker':json.loads(command(['docker','version','--format','{{json .Server}}'],root).stdout),
            'image_store':json.loads(command(['docker','info','--format','{{json .DriverStatus}}'],root).stdout)})
        validation=command(['glimmer','validate',str(template/'rokb')],root,check=False)
        (evidence/'validation.txt').write_text(validation.stdout+validation.stderr)
        if validation.returncode not in (0,2): raise AssertionError('graph validation failed')
        result['phase']='running'
        for case,expected in cases.items():
            item=collect_case(root,evidence,template,case,expected,commit,archive_hash)
            result['results'].append(item)
            write_json(evidence/'qualification.json',result)
            print(case,item.get('verdict'),'PASS' if item['passed'] else 'FAIL',flush=True)
        first,replay=result['results'][:2]
        result['checks']={'same_image':bool(first.get('image_id')) and first.get('image_id')==replay.get('image_id'),
                          'archive_unchanged':digest(archive)==archive_hash,
                          'source_unchanged':verify_source(args.source_revision)==source}
        result['image_id']=first.get('image_id');result['image_platform']=first.get('image_platform')
        result['passed']=all(x['passed'] for x in result['results']) and all(result['checks'].values())
        result['phase']='complete'
        (evidence/'packages.txt').write_text(command([sys.executable,'-m','pip','freeze','--all'],root).stdout)
    except Exception as exc:
        result.update({'phase':'failed','passed':False,'error':type(exc).__name__+': '+str(exc)})
    finally:
        result['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        result['evidence_sha256']={str(p.relative_to(evidence)):digest(p) for p in sorted(evidence.rglob('*')) if p.is_file() and p.name!='qualification.json'}
        write_json(evidence/'qualification.json',result)
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
