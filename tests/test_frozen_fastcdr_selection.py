"""Optional compiler choice rejects invalid configs and records real cache."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools.diagnostics.reliability54_build01.record_native_validation import compiler_selection, successful_suite

ROOT = Path(__file__).resolve().parents[1]


class NativeBuildReceiptTests(unittest.TestCase):
    def test_cmake_cache_requires_one_actual_system_fastcdr_selection(self):
        expected = "/opt/ros/humble/lib/cmake/fastcdr"
        self.assertEqual(compiler_selection("// package\nfastcdr_DIR:PATH="+expected+"\n", expected), expected)
        for text in ("", "fastcdr_DIR:PATH=/root/agent/install/lib/cmake/fastcdr\n",
                     "fastcdr_DIR:PATH="+expected+"\nfastcdr_DIR:PATH="+expected+"\n"):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "system FastCDR"):
                compiler_selection(text, expected)

    def test_native_suite_receipt_keeps_skips_separate_and_rejects_failed_or_partial_log(self):
        self.assertEqual(successful_suite("warnings\nRan 1950 tests in 34.12s\n\nOK (skipped=5)\n"),
                         {"tests": 1950, "skipped": 5})
        self.assertEqual(successful_suite("Ran 2 tests in 0.1s\n\nOK\n"), {"tests": 2, "skipped": 0})
        self.assertEqual(successful_suite('Ran 2021 tests in 121.793s\n\nOK (skipped=5)\n{"status":"COMPLETE_AUXILIARY_ANALYSIS"}\n'),
                         {"tests": 2021, "skipped": 5})
        for text in ("Ran 2 tests in 0.1s\n\nFAILED (errors=1)\n", "Running tests", "Ran 0 tests in 0.0s\n\nOK\n"):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "successful suite"):
                successful_suite(text)
        with self.assertRaisesRegex(ValueError, "one successful suite"):
            successful_suite("Ran 2 tests in 0.1s\n\nOK\nRan 2 tests in 0.2s\n\nOK\n")


@unittest.skipUnless(os.name == "posix" and shutil.which("bash"), "POSIX shell integration; no WSL launched on Windows")
class OptionalFastCdrShellTests(unittest.TestCase):
    def invoke(self, config=None):
        shell = (ROOT / "scripts/freeze_full_plan_workspace.sh").read_text(encoding="utf-8")
        segment = "tracking_cmake_extra_args=()\n" + shell.split("tracking_cmake_extra_args=()\n", 1)[1].split('if ! [[ "$tracking_frozen"', 1)[0]
        environment = dict(os.environ)
        environment.pop("STAGE1_FASTCDR_CMAKE_DIR", None)
        if config is not None:
            environment["STAGE1_FASTCDR_CMAKE_DIR"] = str(config)
        return subprocess.run(["bash", "-c", segment+'printf \'%s\\n\' "${#tracking_cmake_extra_args[@]}" "${tracking_cmake_extra_args[@]}"'],
                              env=environment, capture_output=True, text=True, timeout=5)

    def test_default_adds_no_compiler_argument(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "0")

    def test_explicit_valid_config_is_one_argument_even_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="system fastcdr ") as directory:
            (Path(directory) / "fastcdr-config.cmake").write_text("# test package\n")
            result = self.invoke(directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["1", "-Dfastcdr_DIR="+directory])

    def test_invalid_explicit_config_fails_before_freeze_or_build(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.invoke(directory)
        self.assertEqual(result.returncode, 2)
        self.assertIn("must contain fastcdr-config.cmake", result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
