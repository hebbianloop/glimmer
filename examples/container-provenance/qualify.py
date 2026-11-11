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
import subprocess
import sys

import yaml

HERE = Path(__file__).resolve().parent
RUN_ID = 'run-container-summary'
IMAGE = '.datalad/environments/python-fixture/image.tar'
SUCCESS = {'executed', 'checks-passed'}


def digest(path):
    with Path(path).open('rb') as stream:
        return 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()


def command(argv, cwd, *, check=True, env=None, timeout=240):
    process_env = {**os.environ, 'GIT_AUTHOR_NAME': 'Glimmer synthetic fixture',
                   'GIT_COMMITTER_NAME': 'Glimmer synthetic fixture',
                   'GIT_AUTHOR_EMAIL': 'fixture@example.invalid', 'GIT_COMMITTER_EMAIL': 'fixture@example.invalid'}
    process_env.update(env or {})
    result = subprocess.run(argv, cwd=cwd, env=process_env, capture_output=True,
                            text=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f'{argv[0]} exited {result.returncode}: '+result.stderr[-2000:])
    return result


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
         'reproduction-tolerance': {'abs': 0.0, 'rel': 0.0}},
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


def check_runtime(receipt):
    cfg = receipt['configuration']
    required = {'NetworkMode':'none','ReadonlyRootfs':True,'Memory':134217728,
                'MemorySwap':134217728,'NanoCpus':500000000,'PidsLimit':64}
    if any(cfg.get(k)!=v for k,v in required.items()): raise AssertionError('container limits differ')
    if cfg['CapDrop'] != ['ALL'] or not any(v.startswith('no-new-privileges') for v in cfg['SecurityOpt']):
        raise AssertionError('container privilege restriction missing')
    mounts = {m['Destination']:m for m in receipt['mounts']}
    if set(mounts) != {'/work/code','/work/inputs','/work/out','/tmp'} and set(mounts) != {'/work/code','/work/inputs','/work/out'}:
        raise AssertionError('unexpected container mounts')
    for path in ('/work/code','/work/inputs'):
        if mounts[path]['RW']: raise AssertionError('an input mount is writable')
    if not mounts['/work/out']['RW'] or not receipt['container_removed']: raise AssertionError('output/cleanup failed')
    if receipt['status'] == 'completed':
        probe = json.loads(receipt['stdout'].strip())
        if not all(probe['checks'].values()) or probe['uid'] == 0: raise AssertionError('isolation probe failed')


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
    root.mkdir(parents=True);evidence=root/'evidence';evidence.mkdir()
    template = root/'template'
    commit = prepare(template,archive)
    validation = command(['glimmer','validate',str(template/'rokb')],root,check=False)
    (evidence/'validation.txt').write_text(validation.stdout+validation.stderr)
    if validation.returncode not in (0,2): raise AssertionError('graph validation failed')
    cases = {'execute':'executed','replay':'checks-passed','changed-input':'gate-failed',
        'missing-input':'inputs-unavailable','invalid-input':'gate-failed','missing-validator':'gate-failed',
        'changed-image':'error','missing-image':'error','failed-command':'error',
        'missing-output':'error','wrong-baseline':'mismatch','timeout':'error','unavailable-engine':'error'}
    results = []
    for case,expected in cases.items():
        target=root/case;attempt=evidence/case;attempt.mkdir()
        command(['datalad','clone',str(template),str(target)],root)
        command(['datalad','get',IMAGE],target)
        (target/'out').mkdir(exist_ok=True)
        inject(target,case)
        before=snapshot(target)
        source_status=command(['git','status','--porcelain'],target).stdout
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
            if 'configuration' in obj: check_runtime(obj)
        products={}
        for name in ('raw.json','numeric.json'):
            output=target/'out'/name
            if output.is_file():
                shutil.copyfile(output,attempt/name);products[name]=digest(output)
        checks={'expected_verdict':verdict['verdict']==expected,
                'expected_exit':completed.returncode==(0 if expected in SUCCESS else 1),
                'definition_unchanged':frozen}
        if case in ('execute','replay'):
            checks['exact_products']=len(products)==2 and all(v==digest(HERE/'expected/summary.json') for v in products.values())
            checks['real_container']=len(receipts)==1 and receipts[0]['status']=='completed' and verdict['environment']['pinned'] is True
        if case=='replay':
            checks['raw_check']=bool(verdict['outputs']) and verdict['outputs'][0].get('passed') is True
            checks['numeric_checks']=len(verdict['numeric-checks'])==3 and all(c['passed'] for c in verdict['numeric-checks'])
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
        if case in ('changed-image','missing-image'):
            checks['image_rejected']='container file unavailable or digest mismatch' in verdict['notes']
        result_commit=command(['git','rev-parse','HEAD'],target).stdout.strip()
        (attempt/'datalad-history.txt').write_text(command(['git','log','-1','--format=fuller'],target).stdout)
        item={'case':case,'started_at':started,'finished_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'template_commit':commit,'result_commit':result_commit,'source_status':source_status,'invocation':invocation,
              'definition_sha256':before,'checks':checks,'passed':all(checks.values()),'products':products,
              'manifest_sha256':digest(attempt/'manifest.json')}
        (attempt/'attempt.json').write_text(json.dumps(item,sort_keys=True,indent=2)+'\n')
        results.append(item)
        print(case,verdict['verdict'],'PASS' if item['passed'] else 'FAIL',flush=True)
    import glimmer.tools.run as runner
    sources=[HERE/'qualify.py',HERE/'requirements.txt',*sorted((HERE/'code').glob('*.py')),
             *sorted((HERE/'inputs').glob('*.json')),*sorted((HERE/'expected').glob('*.json'))]
    result={'version':1,'source_revision':args.source_revision,
        'source_sha256':{str(p.relative_to(HERE)):digest(p) for p in sources},
        'runner_sha256':digest(Path(runner.__file__)),
        'image_archive_sha256':digest(archive),'template_commit':commit,
        'python':sys.version,'packages':{p:importlib.metadata.version(p) for p in ('glimmer-rokb','datalad','datalad-container','PyYAML')},
        'docker':command(['docker','version','--format','{{json .Server}}'],root).stdout.strip(),
        'results':results,'passed':all(x['passed'] for x in results)}
    (evidence/'qualification.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    (evidence/'packages.txt').write_text(command([sys.executable,'-m','pip','freeze','--all'],root).stdout)
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
