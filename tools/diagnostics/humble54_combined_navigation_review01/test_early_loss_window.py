"""Check diagnostic scope isolation without opening an experiment or ROS."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


PATH = Path(__file__).with_name("extract_early_loss_window.py")
SPEC = importlib.util.spec_from_file_location("early_loss_window_fixture", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ScopeTests(unittest.TestCase):
    def test_describe_needs_no_native_environment_or_experiment(self):
        run = subprocess.run([sys.executable, "-B", str(PATH), "--describe"],
                             check=True, stdout=subprocess.PIPE, text=True)
        result = json.loads(run.stdout)
        self.assertFalse(result["experimental_inputs_opened"])
        self.assertEqual(result["status"], "PREPARED_NOT_EXECUTED")

    def test_new_window_cannot_impersonate_original_short_window(self):
        original_short = {"start_s": 29.8, "end_s": 30.08, "checks": {"prediction_observed": False}}
        manifest = {"slot_id": MODULE.SLOT, "original_short_window": copy.deepcopy(original_short),
                    "original_terminal_status": "FAIL", "original_acceptance": {"result": "FAIL"},
                    "claim_boundary": "Original constraints retained."}
        result = MODULE.specialize_manifest(manifest, {"sha256": "fixture"})
        self.assertNotIn("original_short_window", result)
        self.assertEqual(result["original_short_window_not_selection_basis"], original_short)
        self.assertEqual(result["original_terminal_status"], "FAIL")
        self.assertEqual(result["original_acceptance"], {"result": "FAIL"})
        self.assertEqual(result["selection"]["start_s_decimal"], "33.8")
        self.assertEqual(result["selection"]["end_s_decimal"], "35.2")
        self.assertIn("NOT_SHORT_SHUTTER", result["extraction_kind"])
        self.assertFalse(result["selection"]["success_or_failure_selection"])

    def test_other_slot_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "only"):
            MODULE.specialize_manifest({"slot_id": "car_extension_combined_seed004"}, {})

    def test_changed_helper_is_rejected_before_import(self):
        with self.assertRaisesRegex(ValueError, "Pinned source"):
            MODULE.checked_bytes(PATH, "0" * 64)


if __name__ == "__main__":
    unittest.main()
