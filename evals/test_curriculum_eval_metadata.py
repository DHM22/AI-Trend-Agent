import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


EVAL_PATH = Path(__file__).with_name("run_curriculum_eval.py")
SPEC = importlib.util.spec_from_file_location("run_curriculum_eval", EVAL_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BenchmarkVersionMetadataTests(unittest.TestCase):
    def test_reads_sibling_manifest_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gold = root / "curriculum_benchmark_v1_1.json"
            gold.write_text("[]", encoding="utf-8")
            (root / "curriculum_benchmark_v1_1_manifest.json").write_text(
                json.dumps({"benchmark_version": "1.1"}), encoding="utf-8"
            )
            self.assertEqual(MODULE.benchmark_version(gold, []), "1.1")

    def test_preserves_v1_fallback_without_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            gold = Path(tmp) / "curriculum_benchmark_v1.json"
            gold.write_text("[]", encoding="utf-8")
            self.assertEqual(MODULE.benchmark_version(gold, []), "1.0")


if __name__ == "__main__":
    unittest.main()
