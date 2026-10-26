"""Optional imaging-normalization tests; raw bytes and spatial meaning stay distinct."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from glimmer.tools.run import normalized_hash, sha256_file


class ImagingTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('nibabel'), 'install glimmer-rokb[imaging]')
    def test_dotted_nifti_names_and_spatial_changes(self):
        import nibabel as nib
        import numpy as np
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);a=root/'sub-01.run-1.nii.gz';b=root/'sub-01.run-2.nii.gz'
            data=np.arange(8,dtype=np.float32).reshape(2,2,2)
            image=nib.Nifti1Image(data,np.eye(4));image.header['descrip']=b'first run';nib.save(image,a)
            image.header['descrip']=b'second run';nib.save(image,b)
            self.assertNotEqual(sha256_file(a),sha256_file(b))
            self.assertEqual(normalized_hash(a),normalized_hash(b))
            image=nib.Nifti1Image(data,np.diag([2,1,1,1]));nib.save(image,b)
            self.assertNotEqual(normalized_hash(a)[0],normalized_hash(b)[0])
            image=nib.Nifti1Image(data.reshape(4,2,1),np.eye(4));nib.save(image,b)
            self.assertNotEqual(normalized_hash(a)[0],normalized_hash(b)[0])

    def test_gifti_semantic_metadata_is_retained(self):
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/'left.cortex.gii';b=Path(td)/'right.cortex.gii'
            a.write_text('<GIFTI><MetaData><MD><Name>AnatomicalStructurePrimary</Name><Value>CortexLeft</Value></MD></MetaData></GIFTI>')
            b.write_text(a.read_text().replace('CortexLeft','CortexRight'))
            self.assertNotEqual(normalized_hash(a)[0],normalized_hash(b)[0])

    @unittest.skipUnless(importlib.util.find_spec('nibabel'), 'install glimmer-rokb[imaging]')
    def test_nifti_large_integer_voxels_remain_distinct(self):
        import nibabel as nib
        import numpy as np
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/'a.nii';b=Path(td)/'b.nii'
            data=np.array([2**53],dtype=np.int64).reshape(1,1,1)
            header=nib.Nifti1Header();header.set_data_dtype(np.int64)
            nib.save(nib.Nifti1Image(data,np.eye(4),header=header),a)
            nib.save(nib.Nifti1Image(data+1,np.eye(4),header=header),b)
            self.assertEqual(nib.load(a).get_fdata().item(),nib.load(b).get_fdata().item())
            self.assertEqual(normalized_hash(a)[1],'nifti-header-zeroed')
            self.assertNotEqual(normalized_hash(a)[0],normalized_hash(b)[0])

    @unittest.skipUnless(importlib.util.find_spec('nibabel'), 'install glimmer-rokb[imaging]')
    def test_nifti_extensions_and_scaling_remain_distinct(self):
        import nibabel as nib
        import numpy as np
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/'a.nii';b=Path(td)/'b.nii'
            image=nib.Nifti1Image(np.ones((2,2,2),dtype=np.int16),np.eye(4))
            image.header.extensions.append(nib.nifti1.Nifti1Extension(6,b'first annotation'))
            nib.save(image,a)
            image.header.extensions.clear()
            image.header.extensions.append(nib.nifti1.Nifti1Extension(6,b'second annotation'))
            nib.save(image,b)
            self.assertEqual(normalized_hash(a)[1],'nifti-header-zeroed')
            self.assertNotEqual(normalized_hash(a)[0],normalized_hash(b)[0])
            nib.save(image,a)
            image.header.set_slope_inter(2,1);nib.save(image,b)
            self.assertNotEqual(normalized_hash(a)[0],normalized_hash(b)[0])
