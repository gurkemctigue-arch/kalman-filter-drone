"""Real-run command/configuration contracts and honest engineering ledgers."""

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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_extended_engineering as extension


def preregistration():
    return json.loads((ROOT / "planning/online_estimator_preregistration.json").read_text(encoding="utf-8"))


def plan():
    with mock.patch.object(extension, "source_hashes", return_value={"example.py": "frozen"}):
        return extension.frozen_plan("extensiontest", ROOT / "planning/online_estimator_preregistration.json")


def report(trial, *, schema=3, result="PASS"):
    return {"schema_version": schema, "acceptance": {"result": result},
            "configuration": {key: trial[key] for key in ("target_class", "desired_distance_m", "desired_height_m")}}


def healthy_recording(directory, *, missing_topic=None):
    """Small recorder artifacts; tests never open a real bag or launch ROS."""
    bag = directory / "rosbag"
    bag.mkdir(parents=True)
    metadata = {"rosbag2_bagfile_information": {
        "version": 9, "message_count": 180, "relative_file_paths": ["recording.db3.zstd"],
        "topics_with_message_count": [
            {"topic_metadata": {"name": name}, "message_count": 90}
            for name in ("/clock", "/vehicle/odometry") if name != missing_topic]}}
    (bag / "metadata.yaml").write_text(json.dumps(metadata), encoding="utf-8")
    (bag / "recording.db3.zstd").write_bytes(b"fixture; must not be opened as a database")
    (directory / "summary.json").write_text(json.dumps({"max_vehicle_altitude_m": 3.,
        "termination_reason": "follow_duration_reached", "armed_seen": True, "offboard_seen": True}), encoding="utf-8")


class ExtendedEngineeringTests(unittest.TestCase):
    def test_sixteen_slots_preserve_original_preregistration_and_single_repeat_scope(self):
        trials = extension.plan_trials("study", preregistration())
        self.assertEqual(len(trials), 16)
        self.assertEqual(len({row["name"] for row in trials}), 16)
        motion = [row for row in trials if row["coverage"] == "speed_changes"]
        self.assertEqual({(row["target_class"], row["command_mode"]) for row in motion},
                         {(category, mode) for category in ("person", "car") for mode in ("velocity", "position")})
        faults = [row for row in trials if row["coverage"] == "online_fault"]
        self.assertEqual({(row["target_class"], row["condition"]) for row in faults},
                         {(category, fault) for category in ("person", "car") for fault in extension.FAULTS})
        self.assertEqual({(row["target_class"], row["desired_distance_m"]) for row in trials if row["coverage"] == "long_distance"},
                         {("person", 7.), ("car", 12.)})
        self.assertTrue(all(row["estimator_method"] == "adaptive_kf" and row["seed"] == 0
                            and row["independent_repeats_per_condition"] == 1 for row in trials))

    def test_resources_faults_profile_distance_and_reselection_reach_actual_commands(self):
        frozen = plan()
        for trial in frozen["trials"]:
            command = extension.flight_command(trial, frozen)
            setting = frozen["resources"][trial["target_class"]]
            for flag, expected in (("--real-time-factor", frozen["resources"]["real_time_factor"]),
                                   ("--inference-image-size", setting["inference_image_size"]),
                                   ("--inference-threads", setting["inference_threads"]),
                                   ("--condition", trial["condition"]), ("--motion-profile-kind", trial["motion_profile_kind"]),
                                   ("--desired-distance-m", trial["desired_distance_m"])):
                self.assertEqual(command[command.index(flag)+1], str(expected))
            self.assertIn("--occlusions", command)
            self.assertIn("--reselect-after-loss", command)
            evaluation, _ = extension.evaluation_command(trial)
            self.assertEqual(evaluation[evaluation.index("--desired-distance-m")+1], str(trial["desired_distance_m"]))
            self.assertNotIn("--start-s", evaluation)
            self.assertNotIn("--end-s", evaluation)

    def test_invalid_resources_and_changed_motion_scope_reject_before_launch(self):
        for key, value in (("real_time_factor", 0), ("real_time_factor", float("nan"))):
            source = preregistration()
            source["resource_configuration"][key] = value
            with self.assertRaises(ValueError):
                extension.plan_trials("study", source)
        source = preregistration()
        source["motion_extension"]["expected_trials"] = 10
        with self.assertRaises(ValueError):
            extension.plan_trials("study", source)
        with self.assertRaises(ValueError):
            extension.plan_trials("../other", preregistration())

    def test_old_schema_wrong_distance_and_trimmed_evaluation_cannot_pass(self):
        trial = next(row for row in plan()["trials"] if row["coverage"] == "long_distance")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.json"
            wrong_distance, trimmed = report(trial), report(trial)
            wrong_distance["configuration"]["desired_distance_m"] = 5.
            trimmed["configuration"]["start_s"] = 10.
            for data in (report(trial, schema=2), wrong_distance, trimmed):
                path.write_text(json.dumps(data))
                self.assertEqual(extension.report_outcome(path, trial)["result"], "MISSING_OR_INVALID")
            path.write_text(json.dumps(report(trial)))
            self.assertEqual(extension.report_outcome(path, trial)["result"], "PASS")

    def test_frozen_hash_and_slot_bindings_reject_changes(self):
        manifest = extension.manifest_for(plan())
        extension.validate_manifest(manifest)
        changed = copy.deepcopy(manifest)
        changed["plan"]["resources"]["real_time_factor"] = .8
        with self.assertRaises(ValueError):
            extension.validate_manifest(changed)
        changed = copy.deepcopy(manifest)
        changed["slots"][0]["trial"] = {"name": "foreign"}
        with self.assertRaises(ValueError):
            extension.validate_manifest(changed)

    def test_serial_flight_then_evaluation_and_stop_after_retains_sixteen_denominator(self):
        frozen = plan()
        data = extension.manifest_for(frozen)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "matrix"
            calls = []

            def runner(command, **_kwargs):
                if "--name" in command:
                    name = command[command.index("--name")+1]
                    calls.append(("flight", name))
                    healthy_recording(root / "results" / name)
                else:
                    path = Path(command[command.index("--output")+1])
                    calls.append(("eval", path.parent.name))
                    trial = next(row for row in frozen["trials"] if row["name"] == path.parent.name)
                    path.write_text(json.dumps(report(trial)))
                return NS(returncode=0)

            self.assertEqual(extension.execute(data, output, root=root, stop_after=2, runner=runner), 2)
            self.assertEqual([kind for kind, _ in calls], ["flight", "eval", "flight", "eval"])
            self.assertEqual([row["status"] for row in data["slots"][:2]], ["PASS", "PASS"])
            self.assertEqual(extension.summary(data)["status_counts"], {"PASS": 2, "PENDING": 14})
            self.assertFalse(extension.summary(data)["all_planned_trials_pass"])
            self.assertFalse(extension.summary(data)["primary_166_included"])

    def test_failed_launch_partial_bag_is_evaluated_and_not_retried(self):
        frozen = plan()
        data = extension.manifest_for(frozen)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls = []

            def runner(command, **_kwargs):
                calls.append(command)
                directory = root / "results" / frozen["trials"][0]["name"]
                if "--name" in command:
                    healthy_recording(directory)
                    return NS(returncode=9)
                Path(command[command.index("--output")+1]).write_text(json.dumps(report(frozen["trials"][0])))
                return NS(returncode=0)

            extension.execute(data, root / "matrix", root=root, stop_after=1, runner=runner)
            self.assertEqual(len(calls), 2)
            self.assertEqual(data["slots"][0]["status"], "FAIL")
            self.assertEqual(data["slots"][0]["evaluations"][0]["result"], "PASS")
            # Mark remaining slots already failed so resume has no fresh work.
            for slot in data["slots"][1:]:
                slot["status"] = "FAIL"
            extension.execute(data, root / "matrix", root=root, runner=mock.Mock(side_effect=AssertionError("retry")))
            self.assertEqual(data["slots"][0]["commands"][0]["returncode"], 9)

    def test_real_infrastructure_artifacts_stop_after_flight_even_with_zero_launcher_exit(self):
        for failure, expected in (("no_bag", "MISSING_BAG_METADATA"),
                                  ("aborted", "SUPERVISOR_ABORTED"),
                                  ("process_crash", "CORE_PROCESS_CRASH"),
                                  ("no_takeoff", "NO_TAKEOFF")):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                data = extension.manifest_for(plan())
                calls = []

                def runner(command, **_kwargs):
                    self.assertIn("--name", command, "Infrastructure failure must skip the evaluator")
                    calls.append(command)
                    directory = root / "results" / command[command.index("--name")+1]
                    if failure == "no_bag":
                        directory.mkdir(parents=True)
                    else:
                        healthy_recording(directory)
                    if failure == "aborted":
                        (directory / "summary.json").write_text(json.dumps({
                            "termination_reason": "flight_aborted", "max_vehicle_altitude_m": 3.}), encoding="utf-8")
                    elif failure == "process_crash":
                        (directory / "process_exit_codes.json").write_text(json.dumps({"px4": -11}), encoding="utf-8")
                    elif failure == "no_takeoff":
                        (directory / "summary.json").write_text(json.dumps({"max_vehicle_altitude_m": .1}), encoding="utf-8")
                        (directory / "telemetry.jsonl").write_text("".join(json.dumps({
                            "kind": "telemetry", "time_s": timestamp, "position": [0., 0., .1]}) + "\n"
                            for timestamp in (1., 15.)), encoding="utf-8")
                    return NS(returncode=0)

                output = root / "matrix"
                self.assertEqual(extension.execute(data, output, root=root, runner=runner), 1)
                self.assertEqual(len(calls), 1)
                self.assertEqual(extension.summary(data)["status_counts"], {"FAIL": 1, "PENDING": 15})
                stored = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(stored["slots"][0]["status"], "FAIL")
                stops = json.loads((output / "infrastructure_stops.json").read_text(encoding="utf-8"))
                self.assertEqual(len(stops), 1)
                self.assertEqual(stops[0]["phase"], "after_flight")
                self.assertEqual(stops[0]["plan_sha256"], data["plan_sha256"])
                self.assertIn(expected, {row["code"] for row in stops[0]["infrastructure_failure"]["reasons"]})

    def test_evaluator_exposes_unreadable_core_stream_and_stops_remaining_pending(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = extension.manifest_for(plan())
            calls = []

            def runner(command, **_kwargs):
                calls.append(command)
                if "--name" in command:
                    healthy_recording(root / "results" / command[command.index("--name")+1])
                else:
                    path = Path(command[command.index("--output")+1])
                    value = report(data["slots"][0]["trial"])
                    value["inputs"] = {"clock_recorded": True, "clock_samples_read": 90,
                                       "topic_types": {"/clock": "Clock", "/vehicle/odometry": "Odometry"},
                                       "read_errors": {"/vehicle/odometry:DecodeError": 90}}
                    path.write_text(json.dumps(value), encoding="utf-8")
                return NS(returncode=0)

            output = root / "matrix"
            self.assertEqual(extension.execute(data, output, root=root, runner=runner), 1)
            self.assertEqual(len(calls), 2)
            self.assertEqual(extension.summary(data)["status_counts"], {"FAIL": 1, "PENDING": 15})
            slot = data["slots"][0]
            self.assertEqual(slot["evaluations"][0]["result"], "PASS")
            self.assertEqual([row["phase"] for row in slot["infrastructure_checks"]], ["after_flight", "after_evaluation"])
            self.assertFalse(slot["infrastructure_checks"][0]["qualification"]["stop"])
            self.assertTrue(slot["infrastructure_checks"][1]["qualification"]["stop"])
            stops = json.loads((output / "infrastructure_stops.json").read_text(encoding="utf-8"))
            self.assertEqual(stops[0]["phase"], "after_evaluation")
            self.assertIn("CORE_TOPIC_UNREADABLE", {row["code"] for row in stops[0]["infrastructure_failure"]["reasons"]})

    def test_ordinary_tracking_failure_and_nonzero_monitor_continue_to_next_slot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = extension.manifest_for(plan())
            first_name = data["slots"][0]["trial"]["name"]
            calls = []

            def runner(command, **_kwargs):
                calls.append(command)
                if "--name" in command:
                    name = command[command.index("--name")+1]
                    directory = root / "results" / name
                    healthy_recording(directory)
                    if name == first_name:
                        (directory / "summary.json").write_text(json.dumps({
                            "max_vehicle_altitude_m": 3., "termination_reason": "wall_timeout",
                            "basic_flight_passed": False, "monitor_exit_code": 1}), encoding="utf-8")
                        (directory / "process_exit_codes.json").write_text(json.dumps({
                            "monitor": 1, "agent": -2, "ros": -15, "bag": -9}), encoding="utf-8")
                        (directory / "telemetry.jsonl").write_text(json.dumps({
                            "kind": "target_state", "state": "LOST", "reason": "ambiguous association"}) + "\n", encoding="utf-8")
                        return NS(returncode=9)
                else:
                    path = Path(command[command.index("--output")+1])
                    trial = next(row["trial"] for row in data["slots"] if row["trial"]["name"] == path.parent.name)
                    value = report(trial, result="FAIL" if path.parent.name == first_name else "PASS")
                    value["inputs"] = {"clock_recorded": True, "clock_samples_read": 90,
                                       "topic_types": {"/clock": "Clock", "/vehicle/odometry": "Odometry"}}
                    path.write_text(json.dumps(value), encoding="utf-8")
                return NS(returncode=0)

            output = root / "matrix"
            self.assertEqual(extension.execute(data, output, root=root, stop_after=2, runner=runner), 2)
            self.assertEqual(len(calls), 4)
            self.assertEqual(extension.summary(data)["status_counts"], {"FAIL": 1, "PASS": 1, "PENDING": 14})
            self.assertFalse((output / "infrastructure_stops.json").exists())
            self.assertEqual(data["slots"][0]["commands"][0]["returncode"], 9)
            self.assertFalse(data["slots"][0]["infrastructure_failure"]["stop"])

    def test_explicit_resume_appends_stop_history_without_retrying_failed_trial(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = extension.manifest_for(plan())
            names = []

            def runner(command, **_kwargs):
                self.assertIn("--name", command)
                name = command[command.index("--name")+1]
                names.append(name)
                directory = root / "results" / name
                healthy_recording(directory)
                (directory / "process_exit_codes.json").write_text(json.dumps({"gazebo": 139}), encoding="utf-8")
                return NS(returncode=1)

            output = root / "matrix"
            extension.execute(data, output, root=root, runner=runner)
            failed_before = copy.deepcopy(data["slots"][0])
            extension.execute(data, output, root=root, runner=runner)
            self.assertEqual(names, [row["trial"]["name"] for row in data["slots"][:2]])
            self.assertEqual(data["slots"][0], failed_before)
            self.assertEqual(extension.summary(data)["status_counts"], {"FAIL": 2, "PENDING": 14})
            stops = json.loads((output / "infrastructure_stops.json").read_text(encoding="utf-8"))
            self.assertEqual([row["trial_name"] for row in stops], names)
            self.assertEqual(len(stops), 2)

    def test_existing_directory_missing_bag_and_interrupted_slot_keep_failure_history(self):
        data = extension.manifest_for(plan())
        data["slots"][0]["status"] = "RUNNING_EVALUATION"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            existing = root / "results" / data["slots"][1]["trial"]["name"]
            existing.mkdir(parents=True)
            evidence = existing / "old.json"
            evidence.write_text("original")
            runner = mock.Mock(return_value=NS(returncode=0))
            extension.execute(data, root / "matrix", root=root, stop_after=2, runner=runner)
            self.assertEqual([row["status"] for row in data["slots"][:3]], ["INTERRUPTED", "FAIL", "FAIL"])
            self.assertEqual(evidence.read_text(), "original")
            runner.assert_called_once()
            self.assertEqual(data["slots"][2]["evaluations"][0]["result"], "MISSING")

    def test_keyboard_interrupt_is_persisted_without_deleting_the_inflight_evidence(self):
        data = extension.manifest_for(plan())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def runner(command, **_kwargs):
                directory = root / "results" / command[command.index("--name")+1]
                directory.mkdir(parents=True)
                (directory / "evidence.txt").write_text("partial")
                raise KeyboardInterrupt
            with self.assertRaises(KeyboardInterrupt):
                extension.execute(data, root / "matrix", root=root, runner=runner)
            stored = json.loads((root / "matrix/manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["slots"][0]["status"], "INTERRUPTED")
            self.assertEqual(stored["slots"][1]["status"], "PENDING")
            self.assertTrue((root / "results" / data["slots"][0]["trial"]["name"] / "evidence.txt").is_file())

    def test_plan_only_never_starts_flights_and_resume_rejects_resource_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "matrix"
            argv = ["run_extended_engineering.py", "--plan-only", "--prefix", "test", "--output", str(output)]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(extension, "source_hashes", return_value={}), \
                    mock.patch.object(extension, "execute") as runner, redirect_stdout(io.StringIO()):
                self.assertEqual(extension.main(), 0)
                runner.assert_not_called()
            original = (output / "manifest.json").read_bytes()
            altered = plan()
            altered["resources"]["real_time_factor"] = .8
            with mock.patch.object(sys, "argv", argv+["--resume"]), mock.patch.object(extension, "frozen_plan", return_value=altered), \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                extension.main()
            self.assertEqual((output / "manifest.json").read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
