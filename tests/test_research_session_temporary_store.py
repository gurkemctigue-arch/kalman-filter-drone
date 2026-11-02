"""A native temporary-store choice must survive the real session wrapper."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "posix" and shutil.which("bash"),
                     "Native shell integration; never launches WSL on Windows")
class ResearchSessionTemporaryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="research session ")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.project = self.directory / "source"
        scripts = self.project / "scripts"
        scripts.mkdir(parents=True)
        self.script = scripts / "run_research_session.sh"
        shutil.copyfile(ROOT / "scripts/run_research_session.sh", self.script)
        (scripts / "ros_python.sh").write_text(
            '#!/usr/bin/env bash\nprintf \'%s\\n\' "$TMPDIR" "$ROS_LOG_DIR" > "$TEST_SESSION_RECEIPT"\n',
            encoding="utf-8")
        self.receipt = self.directory / "receipt.txt"

    def invoke(self, **updates):
        environment = dict(os.environ)
        for name in ("TMPDIR", "STAGE1_TRANSIENT_DIR"):
            environment.pop(name, None)
        environment.update(TEST_SESSION_RECEIPT=str(self.receipt), **updates)
        return subprocess.run(["bash", str(self.script)], env=environment,
                              capture_output=True, text=True, timeout=5)

    def check_selected(self, result, selected):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.receipt.read_text().splitlines(),
                         [str(selected), str(self.project / "results/runtime/ros_logs")])
        self.assertTrue(selected.is_dir())

    def test_default_store_remains_inside_results_when_no_override_is_selected(self):
        self.check_selected(self.invoke(), self.project / "results/runtime/tmp")

    def test_inherited_native_tmpdir_survives_results_wrapper(self):
        selected = self.directory / "native ext4 temporary"
        self.check_selected(self.invoke(TMPDIR=str(selected)), selected)
        self.assertFalse((self.project / "results/runtime/tmp").exists())

    def test_explicit_store_takes_precedence_over_inherited_tmpdir(self):
        selected, inherited = self.directory / "explicit native", self.directory / "unselected"
        self.check_selected(self.invoke(TMPDIR=str(inherited), STAGE1_TRANSIENT_DIR=str(selected)), selected)
        self.assertFalse(inherited.exists())

    def test_relative_store_is_rejected_before_creating_runtime_or_invoking_python(self):
        for name in ("TMPDIR", "STAGE1_TRANSIENT_DIR"):
            with self.subTest(name=name):
                result = self.invoke(**{name: "relative temporary"})
                self.assertEqual(result.returncode, 2)
                self.assertIn("absolute temporary directory", result.stderr)
                self.assertFalse((self.project / "results").exists())
                self.assertFalse(self.receipt.exists())


if __name__ == "__main__":
    unittest.main()
