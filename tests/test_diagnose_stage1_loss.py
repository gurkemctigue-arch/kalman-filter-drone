"""Small scalar diagnostic regressions; no real recording or ROS dependency."""
from copy import deepcopy
import builtins
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import diagnose_stage1_loss as diagnostic


def navigation(output_s, *, acquisition=71.55, processing=71.65, uuid="new-task", track=9, candidate=2):
    return {"kind": "navigation_diagnostics", "time_s": output_s + .02, "output_s": output_s,
            "acquisition_s": acquisition, "measurement_processing_s": processing,
            "target_uuid": uuid, "track_id": track, "candidate_id": candidate,
            "reference_valid": True, "reference_reason": "ground_support", "fusion_accepted": True,
            "fusion_reason": "ACCEPTED", "output_target_uuid": uuid, "output_track_id": track,
            "output_state": 1 if output_s == acquisition else 2, "state_reason": "predicted",
            "output_measurement_source_s": acquisition, "measurement_age_s": output_s - acquisition}


class StageOneLossDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "telemetry.jsonl"
        self.events = [
            {"kind": "phase", "time_s": 10., "phase": "FOLLOW"},
            navigation(71.4, acquisition=71.4, processing=71.46, uuid="old-task", track=4, candidate=1),
            {"kind": "explicit_reselection_requested", "time_s": 71.57, "image_stamp_s": 71.55,
             "target_uuid": "new-task", "source": "TEST_SCRIPT_EXPLICIT_RESELECTION", "bbox": [1., 2., 8., 9.]},
            navigation(71.55), navigation(72.),
            {"kind": "navigation_state", "time_s": 72.12, "stamp_s": 72.1, "state": 2, "target_uuid": "new-task", "track_id": 9},
            {"kind": "detection", "time_s": 72.35, "stamp_s": 72.25, "completed_s": 72.33,
             "navigation_overlap_pair_count": 1, "navigation_incomplete_overlap_pair_count": 0,
             "detections": [{"candidate_id": 2, "bbox": [1., 2., 8., 9.], "navigation_overlap_count": 1}]},
            {"kind": "control_status", "time_s": 72.3, "lifecycle": 3, "reason": "coasting_prediction", "track_id": 9},
            navigation(72.6), navigation(72.61),
        ]

    def write(self, events=None):
        self.path.write_text("".join(json.dumps(row) + "\n" for row in (self.events if events is None else events)), encoding="utf-8")

    def test_reselection_window_keeps_source_arrival_identity_and_each_cached_state_publication(self):
        self.write()
        report = diagnostic.diagnose_telemetry(self.path, diagnostic.Window(71.5, 72.6))
        rows = report["causal_table"]
        self.assertEqual([row["record_sequence"] for row in rows], list(range(2, 9)))
        self.assertEqual(rows[0]["selection"]["target_uuid"], "new-task")
        self.assertEqual(rows[1]["source_s"], 71.55)
        self.assertAlmostEqual(rows[1]["received_s"], 71.57)
        self.assertEqual(rows[2]["source_s"], 72.)
        self.assertEqual(rows[2]["navigation"]["measurement_key"]["acquisition_s"], 71.55)
        self.assertTrue(rows[2]["navigation"]["cached_measurement_diagnostics"])
        self.assertEqual(rows[2]["navigation"]["first_seen_record_sequence"], 3)
        self.assertEqual(rows[-2]["source_s"], None)
        self.assertEqual(rows[-2]["window_time_basis"], "ARRIVAL_ONLY_NO_MESSAGE_SOURCE")
        self.assertEqual(rows[-2]["controller"]["reason"], "coasting_prediction")
        self.assertEqual(rows[4]["detector"]["detections"][0]["navigation_overlap_count"], 1)
        self.assertEqual(report["window_counts"]["navigation_publications"], 3)
        self.assertEqual(report["window_counts"]["new_accepted_navigation_measurements"], 1)
        self.assertEqual(report["window_counts"]["cached_navigation_publications"], 2)
        self.assertIn("NOT_BAG_SEQUENCE", rows[0]["sequence_kind"])

    def test_sequence_bounds_are_inclusive_and_work_without_follow(self):
        self.write(self.events[1:])
        report = diagnostic.diagnose_telemetry(self.path, diagnostic.Window(sequence_start=1, sequence_end=3))
        self.assertEqual([row["record_sequence"] for row in report["causal_table"]], [1, 2, 3])
        self.assertIsNone(report["follow_start_s"])
        self.assertEqual(report["window"], [None, None])

    def test_time_and_sequence_intersection_does_not_recount_cache_first_seen_outside_window(self):
        self.write()
        report = diagnostic.diagnose_telemetry(self.path, diagnostic.Window(71.5, 72.6, 4, 7))
        self.assertEqual([row["record_sequence"] for row in report["causal_table"]], [4, 5, 6, 7])
        self.assertEqual(report["window_counts"]["new_accepted_navigation_measurements"], 0)
        self.assertEqual(report["window_counts"]["cached_navigation_publications"], 1)
        changed = [navigation(71.55), navigation(71.55, track=10), navigation(71.55, candidate=3), navigation(71.55, uuid="other")]
        self.write(changed)
        distinct = diagnostic.diagnose_telemetry(self.path, diagnostic.Window(71.5, 72.6))
        self.assertEqual(distinct["window_counts"]["distinct_navigation_reference_evaluations"], 4)

    def test_explicit_window_without_follow_is_valid_default_without_follow_fails(self):
        self.write(self.events[1:])
        report = diagnostic.diagnose_telemetry(self.path, diagnostic.Window(71.5, 72.6))
        self.assertIsNone(report["follow_start_s"])
        self.assertTrue(report["causal_table"])
        with self.assertRaisesRegex(ValueError, "No FOLLOW.*explicit"):
            diagnostic.diagnose_telemetry(self.path, diagnostic.Window())

    def test_single_telemetry_read_uses_no_ros_or_bag_import(self):
        self.write()
        original_open, original_import, reads = Path.open, builtins.__import__, []
        def counted(path, *args, **kwargs):
            if path == self.path:
                reads.append(args[0] if args else kwargs.get("mode", "r"))
            return original_open(path, *args, **kwargs)
        def guarded(name, *args, **kwargs):
            if name.split(".")[0] in {"rclpy", "rosbag2_py", "evaluate_stage1_flight", "rosidl_runtime_py"}:
                raise AssertionError("Telemetry imported a bag/ROS dependency: " + name)
            return original_import(name, *args, **kwargs)
        with patch.object(Path, "open", counted), patch("builtins.__import__", side_effect=guarded):
            report = diagnostic.diagnose_telemetry(self.path, diagnostic.Window(71.5, 72.6))
        self.assertEqual(reads, ["rb"])
        self.assertEqual(report["inputs"]["read_passes"], 1)
        self.assertEqual(report["inputs"]["records_read"], len(self.events))

    def test_bad_json_timestamps_and_bounds_fail_explicitly_even_outside_window(self):
        for raw in ('{broken}\n', '{"kind":"phase","time_s":NaN}\n',
                    '{"kind":"phase","time_s":1,"time_s":2}\n', '{"kind":"phase"}\n'):
            with self.subTest(raw=raw):
                self.path.write_text(raw, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "telemetry line 1"):
                    diagnostic.diagnose_telemetry(self.path, diagnostic.Window(71.5, 72.6))
        for options in ({"start": 3., "end": 2.}, {"sequence_start": 4, "sequence_end": 3},
                        {"start": float("nan")}, {"sequence_start": -1}):
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    diagnostic.Window(**options)

    def test_original_default_bag_cli_preserves_follow_arrays_and_tf_summary(self):
        import evaluate_stage1_flight as evaluation
        point = lambda x, y, z: NS(x=x, y=y, z=z)
        state = NS(state=1, track_id=7, prediction_age_s=0., rejected_measurements=0,
                   position_m=point(1., 2., 3.), velocity_mps=point(0., 0., 0.))
        observation = NS(depth_valid=True, depth_m=5., depth_std_m=.1, depth_valid_ratio=1., confidence=.9,
                         position_camera_m=point(0., 0., 5.), bbox_x_min_px=1., bbox_y_min_px=2., bbox_x_max_px=3., bbox_y_max_px=4.)
        records = [evaluation.Record("/tracking/state", 9.5, state, 10.2),
                   evaluation.Record("/tracking/flight_phase", 10., NS(data="FOLLOW:ready"), 10.),
                   evaluation.Record("/tracking/observations", 10.1, observation, 10.3),
                   evaluation.Record("/tracking/detection_diagnostics", 10.2,
                                     NS(data=json.dumps({"stamp_s": 10.05, "completed_s": 10.2, "detections": []})), 10.3)]
        output = self.root / "legacy.json"
        with patch.object(evaluation, "read_rosbag", return_value=(records, {"fixture": True})) as reader:
            self.assertEqual(diagnostic.main([str(self.root / "fakebag"), "--output", str(output)]), 0)
        reader.assert_called_once()
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["follow_start_s"], 10.)
        self.assertEqual(report["window"], [9., 15.])
        self.assertEqual(len(report["states"]), 1)
        self.assertEqual(len(report["observations"]), 1)
        self.assertEqual(len(report["diagnostics"]), 1)
        self.assertIn("tf_summary", report)


if __name__ == "__main__":
    unittest.main()
