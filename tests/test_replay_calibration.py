"""Covariance calibration sample membership, without bags or real parameters."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("replay_calibration", ROOT / "scripts/calibrate_estimator_replay_v4.py")
calibration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(calibration)


def measurement(stamp, variance, *, accepted=True):
    return {"source_s": stamp, "target_uuid": "fixture-task", "track_id": 1,
        "acquisition_id": str(stamp), "reference_valid": True, "fusion_accepted": accepted,
        "R_geometry_world_m2": np.diag([variance, variance * 2., variance * 3.]).tolist(),
        "R_pose_world_m2": np.diag([100., 200., 300.]).tolist()}


def trial(rows):
    return {"interval": {"follow_start_s": 1., "recorded_clock_end_s": 3.},
            "measurements": rows, "truth_samples": [{"position_world_m": [999., 999., 999.]}]}


class CalibrationTests(unittest.TestCase):
    def test_named_recording_is_bound_by_actual_configuration_archive_hash_and_bag_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            files = {"run_config.json": {"seed": 4, "target_class": "person", "command_mode": "velocity"},
                     "bag_integrity.json": {"status": "PASS", "fixture_only": True}}
            for name, data in files.items():
                (directory / name).write_text(json.dumps(data), encoding="utf-8")
            hashes = {name: calibration.replay.file_sha256(directory / name) for name in files}
            slot = {"directory": str(directory), "target_class": "person"}
            record = {"artifact_hashes": hashes}
            data = {"export_audit": {"bag_reader": {"bag": str(directory / "rosbag")},
                                    "native_archive_integrity_sha256": hashes["bag_integrity.json"]}}
            self.assertEqual(set(calibration.bind_named_recording(slot, record, data)), set(files))
            data["export_audit"]["bag_reader"]["bag"] = str(directory / "different_named_bag")
            with self.assertRaisesRegex(ValueError, "terminal recording archive"):
                calibration.bind_named_recording(slot, record, data)
            data["export_audit"]["bag_reader"]["bag"] = str(directory / "rosbag")
            (directory / "run_config.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "evidence changed"):
                calibration.bind_named_recording(slot, record, data)

    def test_geometry_rejected_by_online_gate_still_calibrates_without_pose_noise(self):
        data = trial([measurement(1., 1.), measurement(2., 3., accepted=False)])
        value = calibration.geometry_statistics(data)
        np.testing.assert_array_equal(value["R0_sensor_world_m2"], np.diag([2., 4., 6.]))
        self.assertEqual(value["independent_valid_geometry"], 2)

    def test_duplicate_callbacks_do_not_reweight_and_clock_tail_is_included(self):
        first = measurement(1., 1.)
        value = calibration.geometry_statistics(trial([first, deepcopy(first), measurement(3., 3.)]))
        np.testing.assert_array_equal(value["R0_sensor_world_m2"], np.diag([2., 4., 6.]))
        self.assertEqual(value["excluded_counts"], {"duplicate_acquisition": 1})
        self.assertEqual(len(value["selected_acquisitions"]), 2)

    def test_invalid_geometry_and_outside_follow_are_explicitly_counted(self):
        invalid = {"source_s": 2., "reference_valid": False, "reference_reason": "no_depth"}
        value = calibration.geometry_statistics(trial([measurement(.5, 1.), invalid, measurement(2.5, 4.)]))
        self.assertEqual(value["total_measurement_opportunities"], 3)
        self.assertEqual(value["excluded_counts"], {"outside_follow_to_full_clock": 1, "invalid_reference:no_depth": 1})

    def test_truth_and_fusion_verdict_cannot_change_selected_samples(self):
        data = trial([measurement(1., 1.), measurement(2., 3.)])
        previous = calibration.geometry_statistics(data)
        data["truth_samples"] = "irrelevant even if not a valid scoring input"
        for row in data["measurements"]:
            row["fusion_accepted"] = False
        self.assertEqual(calibration.geometry_statistics(data), previous)

    def test_conflicting_duplicate_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "conflicting"):
            calibration.geometry_statistics(trial([measurement(1., 1.), measurement(1., 2.)]))

    def test_invalid_covariance_and_singular_mean_never_receive_jitter(self):
        for matrix in ([[1., 2., 0.], [0., 1., 0.], [0., 0., 1.]],
                       np.diag([-1., 1., 1.]).tolist(), np.diag([0., 1., 1.]).tolist(),
                       [[True, 0., 0.], [0., 1., 0.], [0., 0., 1.]],
                       np.diag([float("nan"), 1., 1.]).tolist()):
            row = measurement(1., 1.); row["R_geometry_world_m2"] = matrix
            with self.subTest(matrix=matrix), self.assertRaises(ValueError):
                calibration.geometry_statistics(trial([row]))

    def test_formal_or_unplanned_seed_rejected_before_opening_arrays(self):
        for mode, seeds in (("FORMAL", [1000]), ("PROBE", [3]), ("EXTENSION_PROBE", [4])):
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "plan.json"; path.touch()
                plan = {"mode": mode, "selected_seeds": seeds}
                with patch.object(calibration.engineering, "load", return_value=plan), \
                        patch.object(calibration.replay, "load") as array_loader, \
                        self.assertRaisesRegex(ValueError, "PROBE plan"):
                    calibration.calibrate(path, {"person": "missing", "car": "missing"}, Path(temporary)/"output")
                array_loader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
