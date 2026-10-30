"""Detection extraction retains ambiguous observations without picking by GT."""
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("recording_ambiguity_test", ROOT / "scripts/extract_research_recording.py")
recording = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recording)


def observation(candidate, confidence=.8, *, depth_valid=True):
    return NS(candidate_id=candidate, class_name="car", confidence=confidence,
              header=NS(stamp=NS(sec=1, nanosec=0)), depth_valid=depth_valid,
              depth_m=6., depth_valid_ratio=1., depth_std_m=.05,
              position_camera_m=NS(x=float(candidate), y=0., z=6.),
              bbox_x_min_px=10.+candidate, bbox_y_min_px=20.,
              bbox_x_max_px=110., bbox_y_max_px=90.)


class RecordingCandidateAmbiguityTests(unittest.TestCase):
    def test_multiple_candidates_remain_in_original_order_without_confidence_selection(self):
        available = [observation(9, .99), observation(1, .46)]
        selected, evidence = recording.measurement_observation(available)
        self.assertIsNone(selected)
        self.assertEqual(evidence["observation_reason"], "multiple_candidates_no_single_measurement")
        self.assertEqual(evidence["observation_count"], 2)
        self.assertEqual([row["candidate_id"] for row in evidence["candidate_observations"]], [9, 1])
        self.assertEqual(evidence["candidate_observations"][0]["position_camera_m"], [9., 0., 6.])

    def test_empty_and_unique_invalid_depth_have_distinct_evidence(self):
        selected, missing = recording.measurement_observation([])
        self.assertIsNone(selected)
        self.assertEqual(missing["observation_reason"], "no_observation")
        item = observation(5, depth_valid=False)
        selected, invalid = recording.measurement_observation([item])
        self.assertIs(selected, item)
        self.assertEqual(invalid["observation_reason"], "unique_invalid_depth")
        self.assertFalse(invalid["candidate_observations"][0]["depth_valid"])

    def test_main_keeps_detection_opportunity_when_legacy_measurement_is_ambiguous(self):
        """Regression for the former unconditional multi-observation exception."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            trial, output = root / "trial", root / "export"
            (trial / "rosbag").mkdir(parents=True)
            (trial / "rosbag/metadata.yaml").write_text("fixture")
            sdf = root / "fixture_model.sdf"
            sdf.write_text("fixture model")
            messages = [
                ("/ground_truth/poses", NS(transforms=[NS(child_frame_id="target_car")])),
                ("/ground_truth/vehicle_poses", NS(transforms=[NS(child_frame_id="stage1_uav")])),
                ("/camera/color/camera_info", NS(width=640, height=480, k=[500., 0, 320., 0, 500., 240., 0, 0, 1.])),
                ("/tracking/observations", observation(9, .99)),
                ("/tracking/observations", observation(1, .46)),
                ("/tracking/detection_diagnostics", NS(data=json.dumps({
                    "stamp_s": 1., "completed_s": 1.2,
                    "detections": [{"bbox": [19., 20., 110., 90.], "confidence": .99},
                                   {"bbox": [11., 20., 110., 90.], "confidence": .46}]}))),
            ]

            class Reader:
                def __init__(self):
                    self.index = 0

                def get_all_topics_and_types(self):
                    return [NS(name=topic, type="fixture/Type") for topic, _ in messages]

                def set_filter(self, _filter):
                    pass

                def has_next(self):
                    return self.index < len(messages)

                def read_next(self):
                    topic, message = messages[self.index]
                    self.index += 1
                    return topic, message, self.index

            @contextmanager
            def reader(*_args):
                yield Reader(), {"fixture_only": True}

            bag = ModuleType("rosbag2_py")
            bag.StorageFilter = lambda **kwargs: kwargs
            serialization = ModuleType("rclpy.serialization")
            serialization.deserialize_message = lambda message, _type: message
            utilities = ModuleType("rosidl_runtime_py.utilities")
            utilities.get_message = lambda _name: object
            modules = {"rosbag2_py": bag, "rclpy.serialization": serialization,
                       "rosidl_runtime_py.utilities": utilities}
            pose = (np.zeros(3), np.eye(3))
            with patch.dict(sys.modules, modules), \
                    patch.object(sys, "argv", ["extract_research_recording.py", str(trial),
                                               "--output", str(output), "--target-class", "car", "--skip-images"]), \
                    patch.object(recording, "open_bag_reader", reader), \
                    patch.object(recording, "pose_dict", return_value={"time_s": 1., "position_m": [0., 0., 0.], "quaternion_xyzw": [0., 0., 0., 1.]}), \
                    patch.object(recording, "interpolate_pose", return_value=pose), \
                    patch.object(recording, "model_camera_mount", return_value=(pose[0], pose[1], {})), \
                    patch.object(recording, "target_mesh_points", return_value=(np.zeros((1, 3)), {"model_sdf": str(sdf), "sources": []})), \
                    patch.object(recording, "read_monitor_events", return_value=([], {})), \
                    patch.object(recording, "shutter_windows", return_value=[]), \
                    patch.object(recording, "project_mesh", return_value={"fully_in_frame": True, "bbox": [10., 20., 110., 90.]}):
                recording.main()
            result = json.loads((output / "recording.json").read_text())
            self.assertEqual(len(result["observations"]), 1)
            self.assertIsNone(result["observations"][0]["point_world_m"])
            self.assertIsNone(result["observations"][0]["confidence"])
            self.assertEqual(result["observations"][0]["observation_count"], 2)
            self.assertEqual(result["observation_reason_counts"], {"multiple_candidates_no_single_measurement": 1})
            self.assertEqual(len(result["frames"]), 1)
            self.assertEqual(len(result["frames"][0]["pred"]), 2)
            self.assertTrue(result["frames"][0]["eligible_geometric_subset"])
            self.assertEqual(result["frames"][0]["review_status"], "PENDING")


if __name__ == "__main__":
    unittest.main()
