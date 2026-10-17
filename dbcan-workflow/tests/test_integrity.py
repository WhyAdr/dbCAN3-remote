"""Integrity refresh checks cover changed, added and ignored files."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from refresh_files_sha256 import manifest_text

class IntegrityTests(unittest.TestCase):
    def test_inventory_tracks_source_changes_and_ignores_temporary_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'source.py').write_text('one\n')
            first = manifest_text(root)
            (root/'FILES.sha256').write_text(first)
            (root/'cache.pyc').write_bytes(b'cache')
            (root/'scratch.tmp').write_text('temporary')
            (root/'__pycache__').mkdir()
            (root/'__pycache__/hidden').write_text('cache')
            self.assertEqual(first, manifest_text(root))
            (root/'source.py').write_text('two\n')
            self.assertNotEqual(first, manifest_text(root))
            (root/'added.md').write_text('new\n')
            self.assertIn('added.md', manifest_text(root))

    def test_complete_package_inventory_and_generated_docs_are_current(self):
        for command in [('tools/refresh_files_sha256.py','--check'),('scripts/gen_docs.py','--check')]:
            subprocess.run([sys.executable,'-B',str(ROOT/command[0]),command[1]],check=True)

if __name__ == '__main__': unittest.main()
