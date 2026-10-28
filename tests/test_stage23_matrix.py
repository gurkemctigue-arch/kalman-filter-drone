"""Test experiment pairing, honest failures and serial execution without SITL."""

from __future__ import annotations

import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_stage23_matrix as matrix
import evaluate_stage1_flight as base


def manifest(trials):
    return {"plan_sha256": "test", "protocol": {"wall_timeout_s": 300., "render_backend": "egl"},
            "slots": [{"trial": trial, "status": "PENDING"} for trial in trials]}


def auto_fixture():
    rows = [base.Record("/fmu/out/vehicle_status_v1", 1., NS(arming_state=2, nav_state=14), 1.)]
    for step in range(81):
        now = 1 + step * .1
        rows.extend([
            base.Record("/tracking/state", now, NS(state=4, target_uuid=""), now),
            base.Record("/tracking/status", now, NS(lifecycle=4), now),
            base.Record("/tracking/command", now, NS(valid=False), now),
            base.Record("/vehicle/odometry", now, NS(twist=NS(twist=NS(linear=NS(x=0., y=0., z=0.)))), now),
        ])
        if step % 2 == 0:
            snapshot = {"schema_version": 1, "acquisition_s": now, "output_s": now, "projected": False,
                        "tracks": [{"track_id": track, "class_name": "person", "matched": True,
                                    "bbox_xyxy": [track*20., 10., track*20.+10., 30.]} for track in (1, 2)]}
            rows.append(base.Record("/tracking/tracks", now, NS(data=json.dumps(snapshot)), now))
    return rows


class Stage23MatrixTests(unittest.TestCase):
    def test_full_default_matrix_has_exact_coverage_and_unique_paths(self):
        planned = matrix.plan_trials("study_v1", list(range(10)))
        self.assertEqual(len(planned), 66)
        self.assertEqual(len({row["name"] for row in planned}), 66)
        crossing = [row for row in planned if row["stage"] == 2 and row["scenario"] == "crossing"]
        self.assertEqual(len(crossing), 20)
        self.assertEqual({row["seed"] for row in crossing}, set(range(10)))
        self.assertEqual(sum(row["scope"] == "engineering_safety" for row in planned), 6)
        for category in ("person", "car"):
            self.assertEqual({row["scenario"] for row in planned if row["stage"] == 2 and row["target_class"] == category},
                             {"crossing", "parallel", "ambiguity", "auto_unique"})
        for trial in planned:
            self.assertEqual(trial["desired_distance_m"], 9 if trial["target_class"] == "car" else 5)
            if trial["stage"] == 2 and trial["target_mode"] == "locked_target":
                self.assertEqual(trial["initial_select"], "middle")
                self.assertEqual(trial["initial_min_candidates"], 3)

    def test_each_stage3_pair_shares_exact_speed_seed_and_control_contract(self):
        planned = matrix.plan_trials("study", list(range(10)))
        pairs = {}
        for row in planned:
            if row["stage"] == 3:
                pairs.setdefault(row["pair_id"], []).append(row)
        self.assertEqual(len(pairs), 20)
        ignored = {"id", "name", "gimbal_mode"}
        for rows in pairs.values():
            self.assertEqual(len(rows), 2)
            self.assertEqual({row["gimbal_mode"] for row in rows}, {"midpoint", "active"})
            self.assertEqual({k: v for k, v in rows[0].items() if k not in ignored},
                             {k: v for k, v in rows[1].items() if k not in ignored})
            self.assertTrue(.45 <= rows[0]["speed_mps"] <= .55)
            command = matrix.flight_command(rows[1])
            self.assertIn("--occlusions", command)
            self.assertIn("--reselect-after-loss", command)

    def test_safe_terminal_contracts_are_explicit_not_reinterpreted_after_failure(self):
        rows = matrix.plan_trials("study", [0])
        ambiguity = next(row for row in rows if row["scenario"] == "ambiguity")
        auto = next(row for row in rows if row["scenario"] == "auto_unique")
        crossing = next(row for row in rows if row["scenario"] == "crossing")
        command = matrix.evaluation_commands(ambiguity)[0][1]
        self.assertIn("--require-ambiguity", command)
        self.assertEqual(command[command.index("--terminal-expectation")+1], "hover")
        self.assertEqual(ambiguity["duration_s"], 50)
        self.assertEqual(auto["duration_s"], 35)
        self.assertIn("--evaluate-auto-unique", matrix.evaluation_commands(auto)[0][1])
        self.assertIn("--no-follow-duration-s", matrix.flight_command(auto))
        self.assertEqual(crossing["terminal_expectation"], "tracking")
        self.assertFalse(crossing["occlusions"])
        parallel = next(row for row in rows if row["scenario"] == "parallel")
        self.assertIn("--occlusions", matrix.flight_command(parallel))
        self.assertIn("--reselect-after-loss", matrix.flight_command(parallel))
        self.assertIn("--require-occlusions", matrix.evaluation_commands(parallel)[0][1])

    def test_resource_protocol_is_explicit_and_identical_within_each_pair(self):
        trials = matrix.plan_trials("study", [0], real_time_factor=.7, car_image_size=640, car_threads=4)
        for trial in trials:
            self.assertEqual(trial["real_time_factor"], .7)
            self.assertEqual(trial["inference_image_size"], 640 if trial["target_class"] == "car" else 320)
            self.assertEqual(trial["inference_threads"], 4 if trial["target_class"] == "car" else 2)
            command = matrix.flight_command(trial)
            self.assertEqual(command[command.index("--real-time-factor")+1], "0.7")
        for arguments in ({"real_time_factor": 0}, {"real_time_factor": float("nan")},
                          {"car_image_size": 481}, {"car_threads": 0}):
            with self.assertRaises(ValueError):
                matrix.plan_trials("study", [0], **arguments)

    def test_plan_only_saves_all_slots_and_resume_rejects_resource_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "matrix"
            arguments = ["run_stage23_matrix.py", "--prefix", "frozen", "--output", str(output),
                         "--plan-only", "--real-time-factor", ".7", "--car-image-size", "640", "--car-threads", "4"]
            with mock.patch.object(sys, "argv", arguments), redirect_stdout(io.StringIO()):
                self.assertEqual(matrix.main(), 0)
            saved = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(saved["slots"]), 66)
            self.assertTrue(all(slot["status"] == "PENDING" for slot in saved["slots"]))
            self.assertEqual(saved["protocol"]["resources"]["car_inference_image_size"], 640)
            changed = arguments + ["--resume", "--car-image-size", "480"]
            with mock.patch.object(sys, "argv", changed), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                matrix.main()
            self.assertEqual(json.loads((output / "manifest.json").read_text(encoding="utf-8")), saved)

    def test_invalid_prefix_or_duplicate_seed_cannot_collide_trial_directories(self):
        for prefix, seeds in [("../outside", [0]), ("ok", [0, 0]), ("ok", [-1]), ("ok", [])]:
            with self.assertRaises(ValueError):
                matrix.plan_trials(prefix, seeds)

    def fake_runner(self, root, events, *, fail_gimbal=False, flight_code=0, make_bag=True):
        def run(command, **kwargs):
            self.assertFalse(kwargs["check"])
            if command[1].endswith("run_stage1_trial.py"):
                name = command[command.index("--name")+1]
                events.append("flight:"+name)
                directory = root / "results" / name
                directory.mkdir(parents=True)
                if make_bag:
                    (directory / "rosbag").mkdir()
                    (directory / "rosbag/metadata.yaml").write_text(
                        "rosbag2_bagfile_information:\n"
                        "  message_count: 200\n"
                        "  relative_file_paths: [rosbag_0.db3]\n"
                        "  topics_with_message_count:\n"
                        "    - topic_metadata: {name: /clock}\n"
                        "      message_count: 100\n"
                        "    - topic_metadata: {name: /vehicle/odometry}\n"
                        "      message_count: 100\n"
                    )
                    (directory / "rosbag/rosbag_0.db3").touch()
                return NS(returncode=flight_code)
            output = Path(command[command.index("--output")+1])
            kind = "flight_eval" if command[1].endswith("evaluate_stage1_flight.py") else "gimbal_eval"
            events.append(kind)
            report = {"schema_version": 3, "acceptance": {"result": "PASS"}} if kind == "flight_eval" else {"result": "FAIL" if fail_gimbal else "PASS"}
            output.write_text(json.dumps(report))
            return NS(returncode=0)
        return run

    def test_evaluation_completes_before_next_sim_and_resume_only_runs_pending(self):
        trials = [row for row in matrix.plan_trials("study", [0]) if row["stage"] == 3][:2]
        data = manifest(trials)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            events = []
            runner = self.fake_runner(root, events)
            matrix.execute(data, root / "matrix", root=root, runner=runner, stop_after=1)
            self.assertEqual([slot["status"] for slot in data["slots"]], ["PASS", "PENDING"], data["slots"])
            self.assertEqual(events, ["flight:"+trials[0]["name"], "flight_eval", "gimbal_eval"])
            matrix.execute(data, root / "matrix", root=root, runner=runner)
            self.assertEqual([slot["status"] for slot in data["slots"]], ["PASS", "PASS"])
            self.assertEqual(events, ["flight:"+trials[0]["name"], "flight_eval", "gimbal_eval",
                                      "flight:"+trials[1]["name"], "flight_eval", "gimbal_eval"])

    def test_exit_zero_does_not_hide_failed_report_and_failed_slots_never_retry(self):
        trial = next(row for row in matrix.plan_trials("study", [0]) if row["stage"] == 3)
        data = manifest([trial])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            events = []
            runner = self.fake_runner(root, events, fail_gimbal=True)
            matrix.execute(data, root / "matrix", root=root, runner=runner)
            self.assertEqual(data["slots"][0]["status"], "FAIL")
            matrix.execute(data, root / "matrix", root=root, runner=runner)
            self.assertEqual(len(events), 3)
            self.assertFalse(matrix.summarize(data)["all_planned_trials_pass"])

    def test_scenario_filter_executes_only_matching_pending_slots(self):
        planned = matrix.plan_trials("study", [0])
        trials = [next(row for row in planned if row["scenario"] == name) for name in ("crossing", "ambiguity")]
        data = manifest(trials)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            events = []
            matrix.execute(data, root / "matrix", root=root, runner=self.fake_runner(root, events), only_scenario="ambiguity")
            self.assertEqual([slot["status"] for slot in data["slots"]], ["PENDING", "PASS"])
            self.assertEqual(data["plan_sha256"], "test")
            self.assertEqual(events[0], "flight:"+trials[1]["name"])

    def test_missing_bag_and_nonzero_flight_are_saved_as_failure(self):
        trial = next(row for row in matrix.plan_trials("study", [0]) if row["stage"] == 3)
        data = manifest([trial])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            matrix.execute(data, root / "matrix", root=root,
                           runner=self.fake_runner(root, [], flight_code=1, make_bag=False))
            saved = json.loads((root / "matrix/manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["slots"][0]["status"], "FAIL")
            self.assertEqual(saved["slots"][0]["commands"][0]["returncode"], 1)
            self.assertEqual(saved["slots"][0]["evaluations"][0]["result"], "MISSING")

    def test_interrupted_slot_and_preexisting_evidence_are_never_overwritten(self):
        trials = [row for row in matrix.plan_trials("study", [0]) if row["stage"] == 3][:2]
        data = manifest(trials)
        data["slots"][0]["status"] = "RUNNING_EVALUATION"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "results" / trials[1]["name"]
            directory.mkdir(parents=True)
            evidence = directory / "keep.json"
            evidence.write_text("original")
            def forbidden(*args, **kwargs):
                self.fail("must not launch either existing or interrupted slot")
            matrix.execute(data, root / "matrix", root=root, runner=forbidden)
            self.assertEqual([slot["status"] for slot in data["slots"]], ["INTERRUPTED", "FAIL"])
            self.assertEqual(evidence.read_text(), "original")

    def test_stage3_rejects_old_schema_even_with_pass_label(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.json"
            path.write_text(json.dumps({"schema_version": 2, "acceptance": {"result": "PASS"}}))
            self.assertEqual(matrix.report_outcome(path, "flight")[0], "FAIL")


class AutoUniqueSafetyTests(unittest.TestCase):
    def evaluate(self, rows):
        return matrix.evaluate_auto_unique(rows, {"clock_recorded": True, "clock_samples_read": 100}, "person")

    def test_actual_multiple_candidates_ambiguity_hover_and_physics_stop_pass(self):
        report = self.evaluate(auto_fixture())
        self.assertEqual(report["result"], "PASS", report["checks"])

    def test_empty_uuid_without_multiple_boxes_cannot_pass(self):
        rows = [row for row in auto_fixture() if row.topic != "/tracking/tracks"]
        report = self.evaluate(rows)
        self.assertFalse(report["checks"]["fresh_multi_box_evidence_is_persistent"])
        self.assertEqual(report["result"], "FAIL")

    def test_a_single_automatic_switch_or_motion_command_fails(self):
        for topic, field, value, check in [
            ("/tracking/state", "state", 1, "never_automatically_tracks_a_candidate"),
            ("/tracking/command", "valid", True, "all_motion_commands_invalid"),
        ]:
            rows = auto_fixture()
            setattr(next(row.message for row in rows if row.topic == topic), field, value)
            self.assertFalse(self.evaluate(rows)["checks"][check])

    def test_invalid_commands_cannot_conceal_actual_vehicle_motion(self):
        rows = auto_fixture()
        next(row for row in reversed(rows) if row.topic == "/vehicle/odometry").message.twist.twist.linear.x = .5
        self.assertFalse(self.evaluate(rows)["checks"]["actual_final_vehicle_speed_below_threshold"])

    def test_missing_final_stream_segment_is_not_a_sustained_hover(self):
        rows = [row for row in auto_fixture() if not(row.topic == "/tracking/status" and 6 <= row.time_s <= 7)]
        self.assertFalse(self.evaluate(rows)["checks"]["all_final_streams_cover_tail"])

    def test_predicted_or_stale_boxes_cannot_count_as_multi_target_evidence(self):
        rows = auto_fixture()
        for row in rows:
            if row.topic == "/tracking/tracks":
                payload = json.loads(row.message.data)
                payload["projected"] = True
                row.message.data = json.dumps(payload)
        self.assertFalse(self.evaluate(rows)["checks"]["fresh_multi_box_evidence_is_persistent"])

    def test_old_projected_source_during_hover_is_valid_but_not_fresh_evidence(self):
        rows = auto_fixture()
        for now in (7., 8., 9.):
            snapshot = {"schema_version": 1, "acquisition_s": 1., "output_s": now,
                        "projected": True, "tracks": []}
            rows.append(base.Record("/tracking/tracks", now, NS(data=json.dumps(snapshot)), now))
        report = self.evaluate(rows)
        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["result"], "PASS", report["checks"])
        self.assertEqual(report["projected_snapshot_count"], 3)
        self.assertEqual(report["fresh_multi_box_acquisitions"], 41)

    def test_stale_nonprojected_detection_remains_invalid(self):
        rows = auto_fixture()
        row = next(row for row in reversed(rows) if row.topic == "/tracking/tracks")
        payload = json.loads(row.message.data)
        payload["acquisition_s"] = 1.
        row.message.data = json.dumps(payload)
        report = self.evaluate(rows)
        self.assertFalse(report["checks"]["track_snapshot_messages_valid"])
        self.assertEqual(report["result"], "FAIL")
        self.assertIn("stale fresh-detection", report["snapshot_errors"][0]["reason"])

    def test_old_projected_source_still_requires_valid_output_receive_timing(self):
        for acquired, output, received in ((1., 10., 9.), (10., 9., 9.), (1., 9., float("nan"))):
            rows = auto_fixture()
            snapshot = {"schema_version": 1, "acquisition_s": acquired, "output_s": output,
                        "projected": True, "tracks": []}
            rows.append(base.Record("/tracking/tracks", 9., NS(data=json.dumps(snapshot)), received))
            report = self.evaluate(rows)
            self.assertFalse(report["checks"]["track_snapshot_messages_valid"])
            self.assertEqual(report["result"], "FAIL")


if __name__ == "__main__":
    unittest.main()
