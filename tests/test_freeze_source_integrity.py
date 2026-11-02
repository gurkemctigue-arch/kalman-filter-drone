"""Source/copy maps include ignored resources and reject changes and omissions."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.diagnostics.reliability54_build01 import source_integrity as integrity

ROOT = Path(__file__).resolve().parents[1]


class FreezeSourceIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source, self.frozen, self.evidence = self.base / "source", self.base / "frozen", self.base / "evidence"
        self.evidence.mkdir()
        for name, data in (("uav_tracking/algorithm.py", b"original algorithm\n"),
                           ("config/ignored_runtime.json", b"original runtime\n"),
                           ("models/ignored_weights.pt", b"original weight bytes\n")):
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (self.source / "scripts").mkdir()
        shutil.copy2(ROOT / "scripts/freeze_full_plan_workspace.sh", self.source / "scripts/freeze_full_plan_workspace.sh")
        self.before = self.evidence / "source_before.json"

    def capture(self):
        integrity.snapshot(self.source, self.before)
        shutil.copytree(self.source, self.frozen)

    def verify(self):
        with redirect_stdout(io.StringIO()):
            return integrity.verify(self.before, self.source, self.frozen, self.evidence)

    def test_exact_filters_keep_ignored_weights_runtime_and_nonroot_build_directories(self):
        for name in ("results/big.bin", "nested/results/big.bin", "node_modules/file", ".git/config",
                     "x.egg-info/PKG-INFO", "ros2_ws/build/cache", "__pycache__/cache.pyc",
                     ".test_temp/temp", "ros2_ws/install/generated", "ros2_ws/log/log"):
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"excluded")
        keep = self.source / "nested/ros2_ws/build/keep.txt"
        keep.parent.mkdir(parents=True)
        keep.write_bytes(b"root-relative slash filter does not exclude this")
        integrity.validate_filters(ROOT / "scripts/freeze_full_plan_workspace.sh")
        result = integrity.file_map(self.source)
        self.assertEqual(set(result), {"uav_tracking/algorithm.py", "config/ignored_runtime.json",
                                       "models/ignored_weights.pt", "scripts/freeze_full_plan_workspace.sh",
                                       "nested/ros2_ws/build/keep.txt"})

    def test_source_runtime_change_is_fail_even_when_copy_matches_original(self):
        self.capture()
        (self.source / "config/ignored_runtime.json").write_bytes(b"changed runtime")
        result = self.verify()
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["source_pre_post"]["changed"], ["config/ignored_runtime.json"])
        self.assertTrue(result["copy_identical"])
        self.assertFalse(result["source_unchanged"])

    def test_missing_weight_and_new_algorithm_are_not_silently_ignored(self):
        self.capture()
        (self.frozen / "models/ignored_weights.pt").unlink()
        for directory in (self.source, self.frozen):
            (directory / "uav_tracking/new_algorithm.py").write_bytes(b"new code")
        result = self.verify()
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["frozen_copy"]["missing"], ["models/ignored_weights.pt"])
        self.assertEqual(result["frozen_copy"]["added"], ["uav_tracking/new_algorithm.py"])
        self.assertEqual(result["source_pre_post"]["added"], ["uav_tracking/new_algorithm.py"])

    def test_exact_copy_passes_and_publication_or_result_cannot_overwrite_evidence(self):
        self.capture()
        result = self.verify()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["expected_entries"], 4)
        original = (self.evidence / "source_frozen_integrity.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.verify()
        self.assertEqual((self.evidence / "source_frozen_integrity.json").read_bytes(), original)
        destination = self.base / "published"
        integrity.publish(self.evidence, destination)
        self.assertEqual((destination / "source_frozen_integrity.json").read_bytes(), original)
        with self.assertRaises(FileExistsError):
            integrity.publish(self.evidence, destination)
        self.assertEqual(json.loads((destination / "source_frozen_integrity.json").read_text())["status"], "PASS")

    @unittest.skipIf(os.name == "nt", "Real directory-symlink behavior is validated on Linux")
    def test_new_results_link_requires_its_exact_declared_store(self):
        self.capture()
        store = self.base / "external_results"
        store.mkdir()
        (self.frozen / "results").symlink_to(store, target_is_directory=True)
        with redirect_stdout(io.StringIO()):
            result = integrity.verify(self.before, self.source, self.frozen, self.evidence, results_store=store)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["generated_results_link"]["expected_store"], str(store.resolve()))


if __name__ == "__main__":
    unittest.main()
