"""Protect the historical data boundary: inputs never supply executable code."""
import importlib.util
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('reproduce_tool', ROOT/'tools/reproduce.py')
reproduce = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reproduce)

class ReproductionBoundaryTests(unittest.TestCase):
    def test_existing_output_is_preserved_before_bundle_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'run'; out.mkdir()
            sentinel=out/'keep.txt'; sentinel.write_text('original')
            with self.assertRaisesRegex(ValueError,'already exists'):
                reproduce.reproduce(Path(tmp)/'not-present.zip',out)
            self.assertEqual(sentinel.read_text(),'original')

    def test_missing_prediction_data_does_not_execute_bundle_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle=Path(tmp)/'bundle.zip'; marker=Path(tmp)/'executed'
            with zipfile.ZipFile(bundle,'w') as z:
                z.writestr('reanalysis/recompute_sys1.py',f'open({str(marker)!r}, "w").write("bad")')
                z.writestr('../outside.txt','untrusted')
            with self.assertRaises(KeyError):
                reproduce.reproduce(bundle,Path(tmp)/'run')
            self.assertFalse(marker.exists())
            self.assertFalse((Path(tmp)/'run').exists())

    def test_duplicate_entries_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle=Path(tmp)/'bundle.zip'
            with warnings.catch_warnings():
                warnings.simplefilter('ignore',UserWarning)
                with zipfile.ZipFile(bundle,'w') as z:
                    z.writestr('reanalysis/sys1_order_inputs.jsonl','{}\n')
                    z.writestr('reanalysis/sys1_order_inputs.jsonl','{}\n')
            with self.assertRaisesRegex(ValueError,'Duplicate'):
                reproduce.reproduce(bundle,Path(tmp)/'run')
            self.assertFalse((Path(tmp)/'run').exists())

if __name__ == '__main__': unittest.main()
