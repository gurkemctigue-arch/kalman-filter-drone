"""Infrastructure stop decisions must not turn tracking failures into aborts."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from uav_tracking.research_failures import classify_infrastructure_failure


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def healthy(root):
    bag = root / "rosbag"
    bag.mkdir()
    metadata = {"rosbag2_bagfile_information": {"version": 9, "message_count": 180,
                "topics_with_message_count": [
                    {"topic_metadata": {"name": topic}, "message_count": count}
                    for topic, count in (("/clock", 100), ("/vehicle/odometry", 80))],
                "relative_file_paths": ["rosbag_0.db3.zstd"]}}
    write_json(bag / "metadata.yaml", metadata)
    # The classifier may inspect file existence, never decompress/read bytes.
    (bag / "rosbag_0.db3.zstd").write_bytes(b"not-a-database-and-must-never-be-opened")
    write_json(root / "summary.json", {"max_vehicle_altitude_m": 3., "basic_flight_passed": True,
               "armed_seen": True, "offboard_seen": True, "termination_reason": "follow_duration_reached"})
    write_json(root / "process_exit_codes.json", {"gazebo": 0, "px4": 0, "ros": 0, "bag": 0, "agent": -2, "monitor": 0})
    write_telemetry(root, [{"kind": "telemetry", "time_s": 1., "position": [0., 0., .1], "phase": "TAKEOFF"},
                           {"kind": "telemetry", "time_s": 15., "position": [5., 0., 3.], "phase": "FOLLOW"}])
    return metadata


def write_telemetry(root, rows):
    (root / "telemetry.jsonl").write_text("".join(json.dumps(row)+"\n" for row in rows), encoding="utf-8")


def codes(report):
    return {item["code"] for item in report["reasons"]}


class ResearchFailureTests(unittest.TestCase):
    def test_parent_launch_zero_does_not_hide_failing_child_at_shutdown(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            healthy(root)
            (root / "ros.log").write_text(
                "[ERROR] [flight_supervisor-5]: process has died [pid 123, exit code 1, cmd 'flight_supervisor'].\n",
                encoding="utf-8")
            result = classify_infrastructure_failure(root)
            self.assertTrue(result["stop"])
            self.assertIn("ROS_CHILD_PROCESS_FAILURE", codes(result))
            self.assertEqual(result["evidence"]["process_exit_codes"]["ros"], 0)

    def test_expected_child_sigint_or_sigterm_is_not_a_hidden_crash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            healthy(root)
            (root / "ros.log").write_text(
                "[ERROR] [node-1]: process has died [pid 123, exit code -2, cmd 'node'].\n"
                "[ERROR] [node-2]: process has died [pid 124, exit code -15, cmd 'node'].\n",
                encoding="utf-8")
            self.assertFalse(classify_infrastructure_failure(root)["stop"])

    def test_healthy_recording_and_normal_shutdown_do_not_stop_or_read_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            healthy(root)
            before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
            result = classify_infrastructure_failure(root)
            self.assertFalse(result["stop"], result["reasons"])
            self.assertEqual({path: path.read_bytes() for path in before}, before)
            self.assertEqual(result["evidence"]["telemetry"]["vehicle_samples"], 2)

    def test_ordinary_tracking_failure_missing_follow_and_window_zero_counts_do_not_stop(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            healthy(root)
            write_json(root / "summary.json", {"max_vehicle_altitude_m": 3., "basic_flight_passed": False,
                "monitor_exit_code": 1, "termination_reason": "wall_timeout", "follow_start_s": None})
            write_json(root / "process_exit_codes.json", {"monitor": 1, "agent": -2, "ros": -15, "bag": -9})
            write_json(root / "offline_evaluation.json", {"schema_version": 3, "acceptance": {"result": "FAIL"},
                "topic_message_counts": {"/vehicle/odometry": 0}, "inputs": {"clock_recorded": True,
                "clock_samples_read": 100, "topic_types": {"/clock": "Clock", "/vehicle/odometry": "Odometry"}}})
            self.assertFalse(classify_infrastructure_failure(root)["stop"])

    def test_absent_bag_metadata_is_definite_missing_recording(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = classify_infrastructure_failure(Path(temporary))
            self.assertIn("MISSING_BAG_METADATA", codes(report))
            self.assertTrue(report["stop"])

    def test_full_metadata_missing_clock_or_vehicle_and_empty_bag_stop(self):
        for topic, expected in (("/clock", "MISSING_CLOCK"), ("/vehicle/odometry", "MISSING_VEHICLE_ODOMETRY")):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                metadata = healthy(root)
                info = metadata["rosbag2_bagfile_information"]
                info["topics_with_message_count"] = [row for row in info["topics_with_message_count"] if row["topic_metadata"]["name"] != topic]
                write_json(root / "rosbag/metadata.yaml", metadata)
                self.assertIn(expected, codes(classify_infrastructure_failure(root)))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata = healthy(root)
            metadata["rosbag2_bagfile_information"]["message_count"] = 0
            write_json(root / "rosbag/metadata.yaml", metadata)
            self.assertIn("EMPTY_BAG", codes(classify_infrastructure_failure(root)))

    def test_recorder_declared_missing_data_file_is_detected_without_database_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata = healthy(root)
            metadata["rosbag2_bagfile_information"]["relative_file_paths"] = ["missing.db3.zstd"]
            write_json(root / "rosbag/metadata.yaml", metadata)
            result = classify_infrastructure_failure(root)
            self.assertIn("MISSING_BAG_FILE", codes(result))
            self.assertEqual(result["evidence"]["bag"]["missing_files"], ["missing.db3.zstd"])

    def test_explicit_supervisor_abort_from_summary_or_phase_is_infrastructure(self):
        for source in ("summary", "telemetry"):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                healthy(root)
                if source == "summary":
                    write_json(root / "summary.json", {"termination_reason": "flight_aborted"})
                else:
                    with (root / "telemetry.jsonl").open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps({"kind": "phase", "phase": "ABORTED", "time_s": 16.,
                                                 "detail": "ABORTED: flight guard: stale PX4 state"})+"\n")
                self.assertIn("SUPERVISOR_ABORTED", codes(classify_infrastructure_failure(root)))

    def test_real_long_vehicle_window_below_half_meter_detects_no_takeoff(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            healthy(root)
            write_json(root / "summary.json", {"max_vehicle_altitude_m": .1})
            write_telemetry(root, [{"kind": "telemetry", "time_s": t, "position": [0., 0., .1]} for t in (1., 12.)])
            result = classify_infrastructure_failure(root)
            self.assertIn("NO_TAKEOFF", codes(result))
            self.assertTrue(result["evidence"]["no_takeoff_assessment"]["sufficient_vehicle_window"])

    def test_short_vehicle_window_or_summary_duration_alone_cannot_prove_no_takeoff(self):
        for rows in ([], [{"kind": "telemetry", "time_s": t, "position": [0., 0., .1]} for t in (1., 4.)]):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                healthy(root)
                write_json(root / "summary.json", {"max_vehicle_altitude_m": .1, "start_sim_s": 1., "end_sim_s": 100.,
                                                    "wall_duration_s": 300., "basic_flight_passed": False})
                write_telemetry(root, rows)
                self.assertFalse(classify_infrastructure_failure(root)["stop"])

    def test_observed_takeoff_overrides_inconsistent_low_altitude_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            healthy(root)
            write_json(root / "summary.json", {"max_vehicle_altitude_m": .01})
            self.assertNotIn("NO_TAKEOFF", codes(classify_infrastructure_failure(root)))

    def test_known_missing_clock_or_core_message_types_in_evaluator_stop(self):
        for metadata, expected in (({"clock_recorded": False}, "MISSING_CLOCK"),
                                   ({"clock_samples_read": 0}, "MISSING_CLOCK"),
                                   ({"unavailable_types": {"/vehicle/odometry": "missing nav_msgs"}}, "CORE_TOPIC_UNREADABLE"),
                                   ({"read_errors": {"/vehicle/odometry: TypeError: corrupted": 1}}, "CORE_TOPIC_UNREADABLE"),
                                   ({"topic_types": {"/clock": "Clock"}}, "MISSING_VEHICLE_ODOMETRY")):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                healthy(root)
                write_json(root / "flight_evaluation.json", {"inputs": metadata})
                self.assertIn(expected, codes(classify_infrastructure_failure(root)))

    def test_ordinary_target_decode_failures_and_partial_jsonl_stay_audited_without_false_stop(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            healthy(root)
            write_json(root / "stage2_evaluation.json", {"result": "FAIL", "inputs": {
                "read_errors": {"/tracking/state: ValueError": 1}, "unavailable_types": {"/tracking/tracks": "unknown"}}})
            with (root / "telemetry.jsonl").open("a", encoding="utf-8") as handle:
                handle.write('{"kind":"incomplete"')
            result = classify_infrastructure_failure(root)
            self.assertFalse(result["stop"])
            self.assertEqual(result["evidence"]["telemetry"]["malformed_lines"], 1)

    def test_definite_core_crashes_stop_but_monitor_nonzero_alone_does_not(self):
        for exits, expected in (({"gazebo": -11}, True), ({"ros": 139}, True), ({"monitor": 1, "agent": -2}, False)):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                healthy(root)
                write_json(root / "process_exit_codes.json", exits)
                self.assertEqual(classify_infrastructure_failure(root)["stop"], expected)

    def test_metadata_parse_corruption_or_data_path_escape_is_a_recording_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            healthy(root)
            (root / "rosbag/metadata.yaml").write_text("[malformed", encoding="utf-8")
            self.assertIn("INVALID_BAG_METADATA", codes(classify_infrastructure_failure(root)))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata = healthy(root)
            metadata["rosbag2_bagfile_information"]["relative_file_paths"] = ["../outside.db3"]
            write_json(root / "rosbag/metadata.yaml", metadata)
            self.assertIn("INVALID_BAG_METADATA", codes(classify_infrastructure_failure(root)))

    def test_nonfinite_damaged_evidence_does_not_break_strict_caller_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            healthy(root)
            write_json(root / "summary.json", {"max_vehicle_altitude_m": float("nan")})
            result = classify_infrastructure_failure(root)
            self.assertFalse(result["stop"])
            self.assertEqual(result["evidence"]["monitor"]["max_vehicle_altitude_m"], "NONFINITE:nan")
            json.dumps(result, allow_nan=False)

    def test_malformed_sqlite_evaluator_log_stops_even_when_bag_exit_and_metadata_are_healthy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            healthy(root)
            (root / "offline_evaluation.log").write_text(
                "Traceback (most recent call last):\n"
                "RuntimeError: SQLite error. Error code: 11. Error message: database disk image is malformed\n",
                encoding="utf-8")
            result = classify_infrastructure_failure(root)
            self.assertTrue(result["stop"])
            self.assertIn("EVALUATOR_RECORDING_IO_FAILURE", codes(result))
            self.assertIn("EVALUATOR_EXCEPTION_WITHOUT_REPORT", codes(result))
            self.assertEqual(result["evidence"]["process_exit_codes"]["bag"], 0)
            self.assertFalse((root / "offline_evaluation.json").exists())
            self.assertEqual(result["evidence"]["evaluator_execution"][0]["sample_scheme"], "complete")

    def test_generic_exception_without_completed_report_is_execution_infrastructure(self):
        for report in (None, {}, "malformed-json"):
            with self.subTest(report=report), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                healthy(root)
                if isinstance(report, dict):
                    write_json(root / "offline_evaluation.json", report)
                elif report is not None:
                    (root / "offline_evaluation.json").write_text("{broken", encoding="utf-8")
                (root / "offline_evaluation.log").write_text(
                    "Traceback (most recent call last):\nKeyError: missing evaluator input\n", encoding="utf-8")
                self.assertIn("EVALUATOR_EXCEPTION_WITHOUT_REPORT", codes(classify_infrastructure_failure(root)))

    def test_completed_normal_failure_report_and_expected_nonzero_verdict_do_not_stop(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            healthy(root)
            write_json(root / "stage2_evaluation.json", {"result": "FAIL", "checks": {"identity_held": False}})
            (root / "stage2_evaluation.log").write_text(
                '{"result": "FAIL", "checks": {"identity_held": false}}\n', encoding="utf-8")
            result = classify_infrastructure_failure(root, evaluator_attempts=[{
                "report": "stage2_evaluation.json", "log": "stage2_evaluation.log", "returncode": 2}])
            self.assertFalse(result["stop"], result["reasons"])

    def test_external_matrix_log_is_explicitly_bound_to_evaluator_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / "trial"
            root.mkdir()
            healthy(root)
            log = parent / "matrix/logs/seed_flight_eval.log"
            log.parent.mkdir(parents=True)
            log.write_text("sqlite3.DatabaseError: database disk image is malformed\n", encoding="utf-8")
            result = classify_infrastructure_failure(root, evaluator_attempts=[{
                "report": str(root / "flight_evaluation.json"), "log": str(log), "returncode": 1}])
            self.assertIn("EVALUATOR_RECORDING_IO_FAILURE", codes(result))
            self.assertIn("EVALUATOR_EXECUTION_FAILED", codes(result))
            self.assertTrue(any(item["source"] == str(log) for item in result["reasons"]))

    def test_missing_report_alone_before_evaluation_is_unknown_but_failed_attempt_is_stop(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            healthy(root)
            self.assertFalse(classify_infrastructure_failure(root)["stop"])
            result = classify_infrastructure_failure(root, evaluator_attempts=[{
                "report": "offline_evaluation.json", "returncode": 1}])
            self.assertIn("EVALUATOR_EXECUTION_FAILED", codes(result))

    def test_explicit_evaluator_crash_is_detected_independently_of_completed_report(self):
        for entry, text in (({"returncode": -11}, ""), ({"returncode": 139}, ""),
                            ({"returncode": 0}, "Segmentation fault (core dumped)\n")):
            with self.subTest(entry=entry, text=text), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                healthy(root)
                write_json(root / "offline_evaluation.json", {"acceptance": {"result": "FAIL"}})
                (root / "offline_evaluation.log").write_text(text, encoding="utf-8")
                result = classify_infrastructure_failure(root, evaluator_attempts=[{
                    "report": "offline_evaluation.json", "log": "offline_evaluation.log", **entry}])
                self.assertIn("EVALUATOR_PROCESS_CRASH", codes(result))

    def test_bounded_log_scan_keeps_tail_error_and_marks_hash_as_sample(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            healthy(root)
            (root / "offline_evaluation.log").write_text(
                "normal progress\n" * 30000 + "RuntimeError: decompression failed: zstd error\n", encoding="utf-8")
            result = classify_infrastructure_failure(root)
            self.assertIn("EVALUATOR_RECORDING_IO_FAILURE", codes(result))
            entry = result["evidence"]["evaluator_execution"][0]
            self.assertEqual(entry["sample_scheme"], "first64KiB_last192KiB")
            self.assertLess(entry["sampled_bytes"], entry["log_bytes"])
            self.assertIn("sample_sha256", entry)

    def test_saved_failure_verdict_does_not_hide_later_unhandled_exception(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            healthy(root)
            write_json(root / "offline_evaluation.json", {"acceptance": {"result": "FAIL"}})
            (root / "offline_evaluation.log").write_text(
                "Traceback (most recent call last):\nRuntimeError: post-report processing failed\n", encoding="utf-8")
            self.assertIn("EVALUATOR_EXCEPTION_AFTER_REPORT", codes(classify_infrastructure_failure(root)))

    def test_attempted_evaluator_zero_exit_without_parseable_completed_report_is_failure(self):
        for report in (None, {}, "broken"):
            with self.subTest(report=report), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                healthy(root)
                if isinstance(report, dict):
                    write_json(root / "offline_evaluation.json", report)
                elif report is not None:
                    (root / "offline_evaluation.json").write_text("{broken", encoding="utf-8")
                result = classify_infrastructure_failure(root, evaluator_attempts=[{
                    "report": "offline_evaluation.json", "returncode": 0}])
                self.assertIn("EVALUATOR_REPORT_MISSING_OR_INVALID", codes(result))


if __name__ == "__main__":
    unittest.main()
