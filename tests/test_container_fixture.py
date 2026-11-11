"""Archive and failure-receipt regressions; live Docker qualification is separate."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import tarfile

EXAMPLE = Path(__file__).resolve().parents[1] / 'examples/container-provenance'
spec = importlib.util.spec_from_file_location('container_entry', EXAMPLE/'code/container_entry.py')
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


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
            descriptor = b'{"schemaVersion":2,"manifests":[]}'
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


if __name__ == '__main__': unittest.main()
