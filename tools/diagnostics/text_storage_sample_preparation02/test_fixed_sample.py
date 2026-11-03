"""Tiny inert fixtures: no telemetry read, native query, or compression."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


SPEC = importlib.util.spec_from_file_location("fixed_sample_small_tests", Path(__file__).with_name("run_fixed_sample.py"))
s = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(s)


class FixedSampleTests(unittest.TestCase):
    def test_api_executes_only_the_single_verified_source_read(self):
        raw = b"class API:\n    verified = True\ndef wide(path):\n    return str(path)\n"
        with patch.object(s, "small", side_effect=[raw, AssertionError("No second source read")]) as read, \
                patch.object(s, "SURVEY_SHA", s.digest(raw)):
            api, wide = s.load_api()
        self.assertTrue(api.verified)
        self.assertEqual(wide("fixture"), "fixture")
        read.assert_called_once_with(s.SURVEY)

    def test_unreviewed_api_source_refuses_before_execution(self):
        raw = b"raise AssertionError('Unreviewed code executed')\n"
        with patch.object(s, "small", return_value=raw), patch.object(s, "SURVEY_SHA", "0" * 64):
            with self.assertRaisesRegex(ValueError, "API source differs"):
                s.load_api()

    def test_operation_and_volume_failure_keep_original_error_and_partial_rows(self):
        original = RuntimeError("SYNTHETIC compact failure")
        volume = OSError("SYNTHETIC volume unavailable")
        report = {"status": "FAIL_PARTIAL_SAMPLE_RETAINED", "error": f"RuntimeError: {original}",
                  "files": [{"path": "INERT FIXTURE", "returncode": 5}]}
        with tempfile.TemporaryDirectory(prefix="fixed_sample_receipt_") as temporary:
            output = Path(temporary) / "result.json"
            api = SimpleNamespace(volume=Mock(side_effect=volume))
            with self.assertRaises(RuntimeError) as raised:
                try:
                    raise original
                finally:
                    s.finalize_report(report, output, api, original)
            retained = json.loads(output.read_bytes())
        self.assertIs(raised.exception, original)
        self.assertEqual(retained["error"], "RuntimeError: SYNTHETIC compact failure")
        self.assertEqual(retained["volume_after_error"], "OSError: SYNTHETIC volume unavailable")
        self.assertIsNone(retained["volume_after"])
        self.assertEqual(retained["files"], report["files"])

    def test_volume_failure_after_success_writes_failed_receipt_before_raising(self):
        volume = OSError("SYNTHETIC final query failure")
        report = {"status": "PASS_FIXED_SAMPLE_ONLY_NOT_FULL_BUDGET", "files": [{"saved_allocation_bytes": 12}]}
        with tempfile.TemporaryDirectory(prefix="fixed_sample_receipt_") as temporary:
            output = Path(temporary) / "result.json"
            with self.assertRaises(OSError) as raised:
                s.finalize_report(report, output, SimpleNamespace(volume=Mock(side_effect=volume)))
            retained = json.loads(output.read_bytes())
        self.assertIs(raised.exception, volume)
        self.assertEqual(retained["status"], "FAIL_PARTIAL_SAMPLE_RETAINED")
        self.assertEqual(retained["error"], retained["volume_after_error"])
        self.assertEqual(retained["files"], [{"saved_allocation_bytes": 12}])

    def test_success_retains_original_rows_and_final_volume(self):
        rows = [{"path": "INERT FIXTURE", "saved_allocation_bytes": 12}]
        report = {"status": "PASS_FIXED_SAMPLE_ONLY_NOT_FULL_BUDGET", "files": deepcopy(rows)}
        with tempfile.TemporaryDirectory(prefix="fixed_sample_receipt_") as temporary:
            output = Path(temporary) / "result.json"
            s.finalize_report(report, output, SimpleNamespace(volume=lambda: {"filesystem": "INERT NTFS FIXTURE"}))
            retained = json.loads(output.read_bytes())
        self.assertEqual(retained["status"], "PASS_FIXED_SAMPLE_ONLY_NOT_FULL_BUDGET")
        self.assertEqual(retained["files"], rows)
        self.assertEqual(retained["volume_after"], {"filesystem": "INERT NTFS FIXTURE"})

    def test_receipt_failure_cannot_replace_original_operation_error(self):
        original = RuntimeError("SYNTHETIC operation failure")
        with patch.object(s, "save_new", side_effect=OSError("SYNTHETIC receipt unavailable")):
            with self.assertRaises(RuntimeError) as raised:
                try:
                    raise original
                finally:
                    s.finalize_report({"status": "FAIL_PARTIAL_SAMPLE_RETAINED"}, Path("INERT NO FILE"),
                                      SimpleNamespace(volume=lambda: {}), original)
        self.assertIs(raised.exception, original)


if __name__ == "__main__":
    unittest.main()
