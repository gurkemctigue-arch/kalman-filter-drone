"""Recorder receive capacity, archived inputs, and actual launch arguments."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import yaml

from scripts import run_stage1_trial as trial


ROOT = Path(__file__).resolve().parents[1]


class RecordingQoSTests(unittest.TestCase):
    def test_checked_in_profiles_bound_only_five_evidence_histories(self):
        profiles = yaml.safe_load((ROOT / "config" / "recording_qos.yaml").read_bytes())
        self.assertEqual({topic: profile["depth"] for topic, profile in profiles.items()}, {
            "/clock": 1, "/fmu/out/vehicle_odometry": 1024,
            "/vehicle/odometry_timing": 1024, "/vehicle/odometry": 1024,
            "/tracking/flight_phase": 256,
        })
        self.assertTrue(all(profile["history"] == "keep_last" for profile in profiles.values()))

    def test_original_bytes_hash_and_actual_recorder_command_use_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            snapshot = root / "configuration"
            snapshot.mkdir()
            source = root / "config" / "recording_qos.yaml"
            raw = (ROOT / "config" / "recording_qos.yaml").read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            source.write_bytes(raw)
            evidence = trial.snapshot_recording_qos(root, snapshot)
            archived = Path(evidence["snapshot"])
            self.assertEqual(archived.read_bytes(), raw)
            self.assertEqual(evidence["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(evidence["bytes"], len(raw))
            source.write_text("changed after snapshot", encoding="utf-8")

            start = Mock(return_value=object())
            topics = ["/clock", "/camera/color/image_raw", "/vehicle/odometry"]
            process = trial.start_recording(start, root / "spool", topics, qos_snapshot=archived)
            self.assertIs(process, start.return_value)
            name, command = start.call_args.args
            self.assertEqual(name, "bag")
            self.assertEqual(command[:5], ["ros2", "bag", "record", "--storage", "sqlite3"])
            qos_index = command.index("--qos-profile-overrides-path")
            self.assertEqual(Path(command[qos_index + 1]), archived)
            self.assertEqual(archived.read_bytes(), raw)
            output_index = command.index("-o")
            self.assertEqual(Path(command[output_index + 1]), root / "spool" / "rosbag")
            self.assertEqual(command[output_index + 2:], topics)

    def test_reliable_raw_override_is_rejected_before_snapshot_or_start(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            snapshot = root / "configuration"
            snapshot.mkdir()
            profiles = yaml.safe_load((ROOT / "config" / "recording_qos.yaml").read_bytes())
            profiles["/fmu/out/vehicle_odometry"]["reliability"] = "reliable"
            (root / "config" / "recording_qos.yaml").write_text(yaml.safe_dump(profiles), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "incompatible.*vehicle_odometry"):
                trial.snapshot_recording_qos(root, snapshot)
            self.assertFalse((snapshot / "recording_qos.yaml").exists())

    def test_zero_and_boolean_keep_last_depths_are_rejected(self):
        for depth in (0, True):
            with self.subTest(depth=depth), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "config").mkdir()
                snapshot = root / "configuration"
                snapshot.mkdir()
                profiles = yaml.safe_load((ROOT / "config" / "recording_qos.yaml").read_bytes())
                profiles["/clock"]["depth"] = depth
                (root / "config" / "recording_qos.yaml").write_text(yaml.safe_dump(profiles), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Invalid.*clock"):
                    trial.snapshot_recording_qos(root, snapshot)
                self.assertFalse((snapshot / "recording_qos.yaml").exists())


if __name__ == "__main__":
    unittest.main()
