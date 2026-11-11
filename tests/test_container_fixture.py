"""Archive and failure-receipt regressions; live Docker qualification is separate."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import tarfile

EXAMPLE = Path(__file__).resolve().parents[1] / 'examples/container-provenance'
spec = importlib.util.spec_from_file_location('container_entry', EXAMPLE/'code/container_entry.py')
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)
spec = importlib.util.spec_from_file_location('container_qualification', EXAMPLE/'qualify.py')
qualification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualification)


class ContainerFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root/'image.tar'

    def archive_with(self, *, modern=False, corrupt=False, config_path=None, count=1, link=False):
        config = b'{"architecture":"arm64","os":"linux"}'
        config_digest = hashlib.sha256(config).hexdigest()
        config_path = config_path or ('blobs/sha256/'+config_digest if modern else config_digest+'.json')
        members = {'manifest.json': json.dumps([{'Config':config_path}]*count).encode(),
                   config_path: b'corrupt' if corrupt else config}
        ids = ['sha256:'+config_digest]
        if modern:
            descriptor = json.dumps({'schemaVersion':2,'config':{'digest':'sha256:'+config_digest}}).encode()
            descriptor_digest = hashlib.sha256(descriptor).hexdigest()
            members['index.json'] = json.dumps({'manifests':[{'digest':'sha256:'+descriptor_digest}]}).encode()
            members['blobs/sha256/'+descriptor_digest] = descriptor
            ids.append('sha256:'+descriptor_digest)
        with tarfile.open(self.archive,'w') as archive:
            for name, payload in members.items():
                info = tarfile.TarInfo(name)
                if link and name == config_path:
                    info.type = tarfile.SYMTYPE; info.linkname = '/outside-fixture'
                    archive.addfile(info)
                else:
                    info.size = len(payload); archive.addfile(info,io.BytesIO(payload))
        return ids

    def test_classic_archive_uses_verified_config_digest(self):
        expected = self.archive_with()
        self.assertEqual(entry.image_ids(self.archive),expected)

    def test_containerd_archive_also_accepts_verified_oci_descriptor(self):
        expected = self.archive_with(modern=True)
        self.assertEqual(entry.image_ids(self.archive),expected)

    def test_corrupt_config_is_rejected(self):
        self.archive_with(corrupt=True)
        with self.assertRaisesRegex(ValueError,'hash mismatch'): entry.image_ids(self.archive)

    def test_multiple_images_are_rejected(self):
        self.archive_with(count=2)
        with self.assertRaisesRegex(ValueError,'exactly one'): entry.image_ids(self.archive)

    def test_path_escape_is_rejected_without_extraction(self):
        self.archive_with(config_path='../outside-fixture')
        with self.assertRaisesRegex(ValueError,'configuration path'): entry.image_ids(self.archive)
        self.assertFalse((self.root.parent/'outside-fixture').exists())

    def test_linked_config_is_rejected(self):
        self.archive_with(link=True)
        with self.assertRaisesRegex(ValueError,'configuration'): entry.image_ids(self.archive)

    def test_oci_descriptor_must_reach_the_archive_config(self):
        self.archive_with(modern=True)
        with tarfile.open(self.archive,'a') as archive:
            unrelated=b'{"schemaVersion":2,"manifests":[]}'
            reference=hashlib.sha256(unrelated).hexdigest()
            for name,payload in {'blobs/sha256/'+reference:unrelated,
                    'index.json':json.dumps({'manifests':[{'digest':'sha256:'+reference}]}).encode()}.items():
                info=tarfile.TarInfo(name);info.size=len(payload);archive.addfile(info,io.BytesIO(payload))
        with self.assertRaisesRegex(ValueError,'does not reach'): entry.image_ids(self.archive)

    def invoke_failure(self, failure):
        image_id=self.archive_with()[0]
        for name in ('code','inputs','out'): (self.root/name).mkdir()
        host={k:None for k in ('NetworkMode','ReadonlyRootfs','CapDrop','SecurityOpt',
                              'Memory','MemorySwap','NanoCpus','PidsLimit','Tmpfs')}
        removals=[]
        def docker(*args,**kwargs):
            if args[0]=='image': value=[{'Id':image_id}]
            elif args[0]=='create':
                if failure=='create-timeout': raise subprocess.TimeoutExpired(args,120,stderr=b'create deadline')
                return SimpleNamespace(stdout='bad-id' if failure=='invalid-id' else 'a'*64)
            elif args[0]=='inspect': value=[{'HostConfig':host,'Mounts':[],'Config':{'User':'501:1000'},'State':{'Running':True}}]
            elif args[0]=='start':
                if failure=='signal': entry.signal.raise_signal(entry.signal.SIGTERM)
                raise subprocess.TimeoutExpired(args,15)
            elif args[0]=='kill': raise subprocess.CalledProcessError(1,args,stderr='kill failed')
            elif args[0]=='rm': removals.append(args[-1]);value=''
            else: value=''
            return SimpleNamespace(stdout=json.dumps(value),stderr='',returncode=0)
        with patch.object(entry.Path,'cwd',return_value=self.root), \
             patch.object(entry.os,'geteuid',return_value=501), \
             patch.object(entry.sys,'argv',['container_entry.py',str(self.archive),'python','method.py']), \
             patch.object(entry,'docker',side_effect=docker), self.assertRaises(SystemExit) as raised:
            entry.main()
        receipt=json.loads(next((self.root/'execution-receipts').glob('*.json')).read_text())
        self.assertEqual(removals,[receipt['container_name']])
        self.assertTrue(receipt['container_removed'])
        self.assertNotEqual(raised.exception.code,0)
        return receipt

    def test_create_timeout_cleans_by_reserved_name_and_retains_diagnostic(self):
        receipt=self.invoke_failure('create-timeout')
        self.assertEqual(receipt['failed_step'],'create')
        self.assertEqual(receipt['error_stderr'],'create deadline')

    def test_invalid_create_identifier_still_cleans_by_name(self):
        self.assertEqual(self.invoke_failure('invalid-id')['failed_step'],'create')

    def test_kill_failure_preserves_timeout_and_attempts_removal(self):
        receipt=self.invoke_failure('kill-failure')
        self.assertEqual(receipt['status'],'timed-out')
        self.assertEqual(receipt['kill_stderr'],'kill failed')
        self.assertEqual(receipt['exit_code'],124)

    def test_sigterm_leaves_failed_receipt_and_removes_container(self):
        receipt=self.invoke_failure('signal')
        self.assertEqual(receipt['failed_step'],'start')
        self.assertEqual(receipt['status'],'failed')

    def test_post_execution_inspection_failure_cannot_report_success(self):
        image_id = self.archive_with()[0]
        for name in ('code','inputs','out'): (self.root/name).mkdir()
        host = {k:None for k in ('NetworkMode','ReadonlyRootfs','CapDrop','SecurityOpt',
                                'Memory','MemorySwap','NanoCpus','PidsLimit','Tmpfs')}
        def docker(*args, **kwargs):
            if args[0] == 'image': value = [{'Id':image_id}]
            elif args[0] == 'create': return SimpleNamespace(stdout='a'*64)
            elif args[0] == 'inspect':
                if getattr(docker,'inspected',False): raise subprocess.CalledProcessError(1,args)
                docker.inspected = True
                value = [{'HostConfig':host,'Mounts':[],'Config':{'User':'501:1000'}}]
            else: value = ''
            return SimpleNamespace(stdout=json.dumps(value),stderr='',returncode=0)
        with patch.object(entry.Path,'cwd',return_value=self.root), \
             patch.object(entry.os,'geteuid',return_value=501), \
             patch.object(entry.sys,'argv',['container_entry.py',str(self.archive),'python','method.py']), \
             patch.object(entry,'docker',side_effect=docker), self.assertRaises(SystemExit) as raised:
            entry.main()
        self.assertEqual(raised.exception.code,1)
        receipts = list((self.root/'execution-receipts').glob('*.json'))
        self.assertEqual(len(receipts),1)
        receipt = json.loads(receipts[0].read_text())
        self.assertEqual(receipt['status'],'failed')
        self.assertTrue(receipt['container_removed'])
        self.assertEqual(receipt['exit_code'],1)


class QualificationHarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_command_deadline_terminates_the_descendant_process_group(self):
        code="""import os,signal,time,pathlib
if os.fork()==0:
    def stop(signum,frame):
        pathlib.Path('child-stopped').write_text(str(signum))
        raise SystemExit(0)
    signal.signal(signal.SIGTERM,stop)
time.sleep(60)
"""
        result=qualification.command([sys.executable,'-c',code],self.root,check=False,timeout=0.75)
        self.assertEqual(result.returncode,124)
        self.assertEqual((self.root/'child-stopped').read_text(),str(entry.signal.SIGTERM))

    def test_unexpected_case_error_retains_receipt_and_failed_result(self):
        evidence=self.root/'evidence';evidence.mkdir()
        receipt=self.root/'broken/execution-receipts/failure.json';receipt.parent.mkdir(parents=True)
        receipt.write_text('{"status":"failed"}\n')
        with patch.object(qualification,'run_case',side_effect=ValueError('missing manifest')), \
             patch.object(qualification,'container_inventory',return_value=[]):
            result=qualification.collect_case(self.root,evidence,None,'broken','error','commit','hash')
        self.assertFalse(result['passed'])
        self.assertIn('missing manifest',result['error'])
        self.assertEqual((evidence/'broken/failure.json').read_bytes(),receipt.read_bytes())
        self.assertIn('failure.json',result['evidence_sha256'])
        self.assertTrue((evidence/'broken/attempt.json').exists())

    def test_engine_inventory_overrides_a_successful_helper_receipt(self):
        evidence=self.root/'evidence';evidence.mkdir()
        with patch.object(qualification,'run_case',return_value={'checks':{'helper_passed':True}}), \
             patch.object(qualification,'container_inventory',return_value=['abc123']), \
             patch.object(qualification,'command') as command:
            result=qualification.collect_case(self.root,evidence,None,'leaked','executed','commit','hash')
        self.assertFalse(result['passed'])
        self.assertFalse(result['checks']['engine_cleanup_verified'])
        command.assert_called_once_with(['docker','rm','--force','abc123'],self.root)

    def test_source_verification_rejects_untracked_transfer_metadata(self):
        here=self.root/'examples/container-provenance';here.mkdir(parents=True)
        (here/'README.md').write_text('fixture\n')
        for args in [('init',),('add','.'),('commit','-m','fixture')]:
            qualification.command(['git',*args],self.root)
        revision=qualification.command(['git','rev-parse','HEAD'],self.root).stdout.strip()
        (here/'._README.md').write_bytes(b'transfer metadata')
        with patch.object(qualification,'HERE',here),self.assertRaisesRegex(ValueError,'source must be clean'):
            qualification.verify_source(revision)


if __name__ == '__main__': unittest.main()
