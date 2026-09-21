import importlib.util
import tempfile
import unittest
from pathlib import Path


EVAL_PATH = Path(__file__).with_name("run_curriculum_eval.py")
SPEC = importlib.util.spec_from_file_location("run_curriculum_eval", EVAL_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class VectorStoreIdentityTests(unittest.TestCase):
    def test_hash_is_deterministic_and_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "z.bin").write_bytes(b"z")
            (root / "a.bin").write_bytes(b"a")
            first = MODULE.vector_store_identity(root)
            second = MODULE.vector_store_identity(root)
            self.assertEqual(first["identity_sha256"], second["identity_sha256"])
            self.assertEqual([x["path"] for x in first["persistent_files"]], ["a.bin", "z.bin"])

    def test_excludes_sqlite_transient_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "chroma.sqlite3").write_bytes(b"db")
            (root / "chroma.sqlite3-wal").write_bytes(b"wal")
            (root / "chroma.sqlite3-shm").write_bytes(b"shm")
            (root / "chroma.sqlite3.lock").write_bytes(b"lock")
            identity = MODULE.vector_store_identity(root)
            self.assertEqual([x["path"] for x in identity["persistent_files"]], ["chroma.sqlite3"])


if __name__ == "__main__":
    unittest.main()
